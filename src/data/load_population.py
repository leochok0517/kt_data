"""주민등록 인구 → NIMS 15군 매핑.

NIMS 15군: 5세 단위 14개 (0-4, 5-9, ..., 65-69) + 70+ 통합 1개.
원본은 0~100세까지 21개 5세 단위 (마지막 100은 100세+).
70 이상을 모두 합산하여 '70+' 그룹으로 만든다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

AGE_LABELS_15: list[str] = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29",
    "30-34", "35-39", "40-44", "45-49", "50-54", "55-59",
    "60-64", "65-69", "70+",
]
AGE_STARTS_15: list[int] = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]

_SUDOGWON = ("서울특별시", "경기도", "인천광역시")
_DEFAULT_PATH = Path("data/mapping/mois_population_202301.parquet")


def load_population_15groups(
    path: Path = _DEFAULT_PATH,
    only_sudogwon: bool = True,
) -> pl.DataFrame:
    """주민등록 인구를 NIMS 15군으로 매핑.

    Args:
        path: 5세 단위 주민등록 parquet (admdong_cd, admdong_nm, sgg_nm, sido_nm, age_5_start, pop_5)
        only_sudogwon: True면 서울/경기/인천만 (sido_nm 필터)

    Returns:
        columns = [admdong_cd, admdong_nm, sgg_nm, sido_nm, age_group, age_idx, pop]
        — 행정동마다 정확히 15개 행 (없는 그룹은 pop=0).
    """
    df = pl.read_parquet(path)
    if only_sudogwon:
        df = df.filter(pl.col("sido_nm").is_in(_SUDOGWON))

    # age_5_start ≥70 → 70 (모두 '70+' 그룹으로)
    df = df.with_columns(
        pl.when(pl.col("age_5_start") >= 70)
        .then(pl.lit(70, dtype=pl.Int8))
        .otherwise(pl.col("age_5_start"))
        .alias("age_start_15")
    )

    grouped = (
        df.group_by(["admdong_cd", "admdong_nm", "sgg_nm", "sido_nm", "age_start_15"])
        .agg(pl.col("pop_5").sum().alias("pop"))
    )

    # 보장: 행정동마다 15개 그룹 (없는 그룹은 pop=0)
    admdong_keys = grouped.select(["admdong_cd", "admdong_nm", "sgg_nm", "sido_nm"]).unique()
    age_frame = pl.DataFrame(
        {
            "age_start_15": AGE_STARTS_15,
            "age_idx": list(range(15)),
            "age_group": AGE_LABELS_15,
        },
        schema={"age_start_15": pl.Int8, "age_idx": pl.Int64, "age_group": pl.String},
    )
    full = admdong_keys.join(age_frame, how="cross")
    out = (
        full.join(grouped, on=["admdong_cd", "admdong_nm", "sgg_nm", "sido_nm", "age_start_15"], how="left")
        .with_columns(pl.col("pop").fill_null(0).cast(pl.Int64))
        .select(["admdong_cd", "admdong_nm", "sgg_nm", "sido_nm", "age_group", "age_idx", "pop"])
        .sort(["admdong_cd", "age_idx"])
    )
    return out


def get_population_matrix(
    df: pl.DataFrame | None = None,
) -> tuple[np.ndarray, list[str], list[str]]:
    """행정동 × 연령 인구 행렬.

    Returns:
        N: ndarray shape (n_admdong, 15)
        admdong_codes: 길이 n_admdong
        age_labels: 길이 15 (= AGE_LABELS_15)
    """
    if df is None:
        df = load_population_15groups()

    pivoted = (
        df.select(["admdong_cd", "age_idx", "pop"])
        .pivot(on="age_idx", index="admdong_cd", values="pop", aggregate_function="first")
        .sort("admdong_cd")
    )
    admdong_codes = pivoted.get_column("admdong_cd").to_list()
    age_cols = [str(i) for i in range(15)]
    N = pivoted.select(age_cols).to_numpy().astype(np.int64)
    return N, admdong_codes, AGE_LABELS_15


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    df = load_population_15groups()
    print("shape:", df.shape)
    print("admdong 수:", df.select("admdong_cd").n_unique())
    print("age group 수:", df.select("age_group").n_unique())
    print(f"수도권 총 인구: {df['pop'].sum():,}")

    by_age = df.group_by(["age_idx", "age_group"]).agg(pl.col("pop").sum()).sort("age_idx")
    print()
    print("연령별 분포 (15군):")
    for row in by_age.iter_rows(named=True):
        print(f"  [{row['age_idx']:>2}] {row['age_group']:>6}: {row['pop']:>10,}")

    N, admdongs, labels = get_population_matrix(df)
    print(f"\nmatrix shape: {N.shape}")
    print(f"matrix sum:   {N.sum():,}")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(by_age["age_group"].to_list(), by_age["pop"].to_list(), color="steelblue")
    ax.set_xlabel("Age group (NIMS 15)")
    ax.set_ylabel("Population")
    ax.set_title(f"수도권 주민등록 인구 — 2023-01 (sum={df['pop'].sum():,})")
    ax.tick_params(axis="x", rotation=30)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    plt.tight_layout()

    out = Path("outputs/load_population_check.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    print(f"\nsaved {out}")
