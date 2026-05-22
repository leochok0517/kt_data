"""2020년 시도 × 성별 × 연령 고용률 (KOSIS, CP949 CSV) 로더.

원본 파일 (`external/labor/employment_korea_2020.csv`):
- 헤더 2행 (행정구역별, 성별, 연령별 + 측정 항목명)
- 데이터 819행 = 21 region × 3 sex × 13 age
- 연령: 합계 / 15-19세 / 20-24세 / ... / 65-69세 / 70세 이상
- 측정값: 15세 이상 인구, 일하였음-계, 주로/틈틈이/일시휴직/일하지않음

NIMS 15군 매핑:
    15-19세  → age_idx 3
    20-24세  → age_idx 4
    ...
    65-69세  → age_idx 13
    70세 이상→ age_idx 14
0-14세 (age_idx 0, 1, 2) 는 데이터 없음 — `build_rho_matrix` 가 0 처리.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from kt_data.data import DATA_ROOT

SIDO_NORM_MAP: dict[str, str] = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}

AGE_LABEL_TO_NIMS_IDX: dict[str, int] = {
    "15-19세": 3,
    "20-24세": 4,
    "25-29세": 5,
    "30-34세": 6,
    "35-39세": 7,
    "40-44세": 8,
    "45-49세": 9,
    "50-54세": 10,
    "55-59세": 11,
    "60-64세": 12,
    "65-69세": 13,
    "70세 이상": 14,
}

ADMDONG_PREFIX_TO_SIDO: dict[str, str] = {
    "11": "서울",
    "28": "인천",
    "41": "경기",
}

VALID_SEX: tuple[str, ...] = ("계", "남자", "여자")


def load_employment_rate(
    path: Path | None = None,
    sex: str = "계",
) -> pl.DataFrame:
    """시도 × NIMS 연령 (15+) 고용률 long DataFrame.

    Args:
        path: CSV path (default: external/labor/employment_korea_2020.csv).
        sex: '계' (전체) | '남자' | '여자'.

    Returns:
        columns = [sido_nm, age_label, age_idx, population_15plus, employed, employment_rate]
        sido_nm 은 약칭 ('서울', '경기', ...). age_idx 3~14, employment_rate in [0, 1].
    """
    if sex not in VALID_SEX:
        raise ValueError(f"sex must be in {VALID_SEX}, got {sex!r}")
    if path is None:
        path = DATA_ROOT / "external" / "labor" / "employment_korea_2020.csv"
    if not path.exists():
        raise FileNotFoundError(path)

    raw = pl.read_csv(
        path,
        encoding="cp949",
        has_header=False,
        skip_rows=2,
        new_columns=[
            "region_raw",
            "sex",
            "age_label",
            "population_15plus",
            "worked_total",
            "worked_mainly",
            "worked_occasionally",
            "on_leave",
            "did_not_work",
        ],
    )

    df = (
        raw.filter(pl.col("sex") == sex)
        .filter(pl.col("age_label") != "합계")
        .filter(pl.col("region_raw").is_in(list(SIDO_NORM_MAP.keys())))
        .with_columns(
            pl.col("region_raw").replace_strict(SIDO_NORM_MAP).alias("sido_nm"),
            pl.col("age_label")
            .replace_strict(AGE_LABEL_TO_NIMS_IDX, return_dtype=pl.Int32)
            .alias("age_idx"),
        )
        .with_columns(
            (pl.col("worked_total") / pl.col("population_15plus"))
            .cast(pl.Float64)
            .alias("employment_rate"),
        )
        .rename({"worked_total": "employed"})
        .select(
            "sido_nm",
            "age_label",
            "age_idx",
            "population_15plus",
            "employed",
            "employment_rate",
        )
        .sort(["sido_nm", "age_idx"])
    )
    return df


def get_sido_from_admdong(admdong_cd: str) -> str:
    """행정동 코드(10자리) → 시도 약칭. 알 수 없으면 'unknown'."""
    return ADMDONG_PREFIX_TO_SIDO.get(str(admdong_cd)[:2], "unknown")


def get_sido_array(admdong_codes: list[str]) -> list[str]:
    return [get_sido_from_admdong(c) for c in admdong_codes]


def build_rho_matrix(
    admdong_codes: list[str],
    sido_nm_per_admdong: list[str] | None = None,
    employment_df: pl.DataFrame | None = None,
    fill_under_15: float = 0.0,
    fill_unknown_sido: float = 0.0,
) -> np.ndarray:
    """행정동 × NIMS 15군 ρ (고용률) 행렬.

    ρ[i, a] = sido(i) 의 a 연령 고용률.
    a ∈ {0, 1, 2} (0-14세) 는 데이터 없음 → fill_under_15.
    시도 매핑 실패시 fill_unknown_sido.

    Returns:
        (n_admdong, 15) float64.
    """
    if employment_df is None:
        employment_df = load_employment_rate()
    if sido_nm_per_admdong is None:
        sido_nm_per_admdong = get_sido_array(admdong_codes)
    if len(sido_nm_per_admdong) != len(admdong_codes):
        raise ValueError("len(sido_nm_per_admdong) != len(admdong_codes)")

    rate_by_sido_age: dict[tuple[str, int], float] = {}
    for row in employment_df.iter_rows(named=True):
        rate_by_sido_age[(row["sido_nm"], int(row["age_idx"]))] = float(
            row["employment_rate"]
        )

    n_adm = len(admdong_codes)
    rho = np.zeros((n_adm, 15), dtype=np.float64)
    for i, sido in enumerate(sido_nm_per_admdong):
        for a in range(15):
            if a < 3:
                rho[i, a] = fill_under_15
            elif sido == "unknown":
                rho[i, a] = fill_unknown_sido
            else:
                rho[i, a] = rate_by_sido_age.get((sido, a), fill_unknown_sido)
    return rho


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from kt_data.data.load_population import load_population_15groups

    df = load_employment_rate()
    print("=== 고용률 데이터 ===")
    print(f"총 행:    {df.height}")
    print(f"시도 수:  {df.get_column('sido_nm').n_unique()}")
    print(f"연령 수:  {df.get_column('age_idx').n_unique()}")

    sudogwon = df.filter(pl.col("sido_nm").is_in(["서울", "경기", "인천"]))
    print("\n=== 수도권 시도 × 연령 고용률 (%) ===")
    pivot = (
        sudogwon.select("age_label", "sido_nm", "employment_rate")
        .with_columns((pl.col("employment_rate") * 100).round(1).alias("rate_pct"))
        .pivot(values="rate_pct", index="age_label", on="sido_nm")
    )
    print(pivot)

    df_pop = load_population_15groups()
    codes = (
        df_pop.select("admdong_cd").unique().sort("admdong_cd").get_column("admdong_cd").to_list()
    )
    rho = build_rho_matrix(codes)
    print("\n=== ρ 매트릭스 ===")
    print(f"shape: {rho.shape}")
    print(f"평균 (전체):  {rho.mean():.3f}")
    AGE_LABELS = [
        "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
        "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70+",
    ]
    print("연령별 평균:")
    for a, lab in enumerate(AGE_LABELS):
        print(f"  [{a:>2}] {lab:>5}: {rho[:, a].mean():.3f}")
