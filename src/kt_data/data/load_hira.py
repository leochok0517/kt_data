"""HIRA 인플루엔자 진료에피소드 로더 (xlsx).

데이터 출처:
    국민건강보험공단_감염성질환(인플루엔자) 의료이용정보_20241231.xlsx

파일 위치:
    ``DATA_ROOT / "external" / "hira" / <위 파일명>``

원본 시트:
    - ``외래입원주부상병``: 외래 + 입원 진료에피소드
    - ``입원주부상병``:    입원만
    - ``시도코드``:        시도 코드 ↔ 이름 매핑 (18 entries)

단위 / 정의:
    - "진료에피소드 건수": J09 + J10 + J11 (인플루엔자) 상병코드 기준
      **28일 청구건 묶음 / 중복제거 후** 카운트.
    - 따라서 한 환자의 동일 시즌 재발은 28일 이내면 1 건, 28일 초과면 2 건.

기간: 2006-01-01 ~ 2024-12-31 (일별).

한계점:
    1. ILI (인구 1000명당 외래환자 분율) 와 달리 **분모가 인구** 로 정리되어
       있어 reporting fraction 으로 직접 해석 가능 — 단 0.15-0.30 정도가
       문헌·1차 계산 기반 추정치.
    2. 시즌 분리는 호출측 calibration 단계에서 결정 (raw 는 일별).
    3. 시도 18 개 — 기존 (예: 45 전라북도) 와 신 자치도 코드 (52 전북특별자치도)
       가 병존. 사용자가 통합/분리 정책 선택 필요.
    4. 성별: raw 는 "남자"/"여자". 본 모듈은 "M"/"F" 로 정규화.
    5. 연령군: raw 는 ``"1. 0-5세"`` 식 prefix 포함. 본 모듈은 prefix 제거.
"""

from __future__ import annotations

from datetime import date as _date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import polars as pl

from kt_data.data import DATA_ROOT

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

#: 6 개 HIRA 연령 그룹 (prefix 정리된 형태).
HIRA_AGE_GROUPS: list[str] = ["0-5", "6-11", "12-17", "18-44", "45-64", "65+"]

#: 시도 코드 ↔ 이름 (18 entries — 기존 코드 + 신 자치도 코드 병행).
HIRA_SIDO_CODES: dict[int, str] = {
    11: "서울특별시",
    26: "부산광역시",
    27: "대구광역시",
    28: "인천광역시",
    29: "광주광역시",
    30: "대전광역시",
    31: "울산광역시",
    36: "세종특별자치시",
    41: "경기도",
    43: "충청북도",
    44: "충청남도",
    45: "전라북도",
    46: "전라남도",
    47: "경상북도",
    48: "경상남도",
    50: "제주특별자치도",
    51: "강원특별자치도",
    52: "전북특별자치도",
}

#: 수도권 3 시도 코드 (서울, 인천, 경기).
SUDOGWON_SIDO_CODES: list[int] = [11, 28, 41]

#: 실제 xlsx 파일명 (DATA_ROOT/external/hira/ 아래에 존재해야 함).
_HIRA_XLSX_NAME: str = (
    "국민건강보험공단_감염성질환(인플루엔자) 의료이용정보_20241231.xlsx"
)

# 시트 이름
_SHEET_OUTPATIENT: str = "외래입원주부상병"
_SHEET_INPATIENT: str = "입원주부상병"
_SHEET_SIDO: str = "시도코드"

# raw → 정규화 매핑
_AGE_LABEL_MAP: dict[str, str] = {
    "1. 0-5세": "0-5",
    "2. 6-11세": "6-11",
    "3. 12-17세": "12-17",
    "4. 18-44세": "18-44",
    "5. 45-64세": "45-64",
    "6. 65세 이상": "65+",
}

_SEX_MAP: dict[str, str] = {"남자": "M", "여자": "F"}

# raw 컬럼명 → 정규화된 영문 snake_case
_RAW_COL_MAP: dict[str, str] = {
    "요양개시일자": "date",
    "주소(시도)": "sido_code",
    "성별": "sex_raw",
    "연령군": "age_group_raw",
    "진료에피소드 건수": "episodes",
}

Setting = Literal["outpatient_inpatient", "inpatient_only"]
Sex = Literal["M", "F", "all"]


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _get_xlsx_path() -> Path:
    """xlsx 경로 (존재 확인 포함)."""
    path = DATA_ROOT / "external" / "hira" / _HIRA_XLSX_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"HIRA xlsx not found at {path!s}. "
            f"Place the file at data/external/hira/ before loading."
        )
    return path


def _sheet_name_for_setting(setting: Setting) -> str:
    if setting == "outpatient_inpatient":
        return _SHEET_OUTPATIENT
    if setting == "inpatient_only":
        return _SHEET_INPATIENT
    raise ValueError(
        f"setting must be 'outpatient_inpatient' or 'inpatient_only', "
        f"got {setting!r}"
    )


@lru_cache(maxsize=4)
def _read_episode_sheet(setting: Setting) -> pl.DataFrame:
    """raw xlsx 시트를 polars DF 로 읽고 정규화.

    Returns:
        Long-form DF: ``date`` (Date), ``sido_code`` (Int64),
        ``sex`` ("M"/"F"), ``age_group`` (정규화), ``episodes`` (Int64).
    """
    path = _get_xlsx_path()
    sheet = _sheet_name_for_setting(setting)
    raw = pl.read_excel(
        source=path,
        sheet_name=sheet,
        engine="openpyxl",
    )

    # raw 컬럼명 검증
    missing = set(_RAW_COL_MAP) - set(raw.columns)
    if missing:
        raise RuntimeError(
            f"Expected columns missing in sheet {sheet!r}: {sorted(missing)}. "
            f"Got: {raw.columns}"
        )

    df = raw.rename(_RAW_COL_MAP)

    # date 파싱 — 원본은 'YYYY-MM-DD' string
    df = df.with_columns(
        pl.col("date").str.to_date("%Y-%m-%d"),
        pl.col("sido_code").cast(pl.Int64),
        pl.col("episodes").cast(pl.Int64),
        pl.col("sex_raw").replace_strict(_SEX_MAP, return_dtype=pl.String).alias("sex"),
        pl.col("age_group_raw").replace_strict(_AGE_LABEL_MAP, return_dtype=pl.String).alias("age_group"),
    ).select(["date", "sido_code", "sex", "age_group", "episodes"])

    return df


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def load_hira_episodes(
    setting: Setting = "outpatient_inpatient",
    sido_codes: list[int] | None = None,
    age_groups: list[str] | None = None,
    sex: Sex = "all",
    date_range: tuple[str, str] | None = None,
) -> pl.DataFrame:
    """일별 long-form 진료에피소드 DataFrame.

    Args:
        setting: ``"outpatient_inpatient"`` (외래+입원 시트) 또는 ``"inpatient_only"``.
        sido_codes: 시도 코드 필터 (예: ``SUDOGWON_SIDO_CODES``). None 이면 전체.
        age_groups: 연령 그룹 필터 (``HIRA_AGE_GROUPS`` 의 부분집합). None 이면 전체.
        sex: ``"M"`` / ``"F"`` / ``"all"``.
        date_range: ``("YYYY-MM-DD", "YYYY-MM-DD")`` 포함 범위. None 이면 전체.

    Returns:
        Long-form polars DF — 컬럼: ``date``, ``sido_code``, ``sex``,
        ``age_group``, ``episodes``.
    """
    df = _read_episode_sheet(setting)

    if sido_codes is not None:
        df = df.filter(pl.col("sido_code").is_in(list(sido_codes)))
    if age_groups is not None:
        unknown = set(age_groups) - set(HIRA_AGE_GROUPS)
        if unknown:
            raise ValueError(
                f"unknown age_groups {sorted(unknown)}; "
                f"expected subset of {HIRA_AGE_GROUPS}"
            )
        df = df.filter(pl.col("age_group").is_in(list(age_groups)))
    if sex != "all":
        if sex not in ("M", "F"):
            raise ValueError(f"sex must be 'M' / 'F' / 'all', got {sex!r}")
        df = df.filter(pl.col("sex") == sex)
    if date_range is not None:
        start_s, end_s = date_range
        start = _date.fromisoformat(start_s)
        end = _date.fromisoformat(end_s)
        df = df.filter(
            (pl.col("date") >= start) & (pl.col("date") <= end)
        )

    return df


def aggregate_hira_weekly(
    df: pl.DataFrame,
    sum_over: list[str] | tuple[str, ...] = ("sido_code", "sex"),
) -> pl.DataFrame:
    """ISO week (월요일 시작) 단위 합산.

    Args:
        df: ``load_hira_episodes`` 결과 (또는 동일 schema).
        sum_over: 합산해서 없앨 차원. default ``("sido_code", "sex")``.
            ``age_group`` 은 합산 후보가 아님 (그룹별 시계열 유지가 목적).

    Returns:
        Long-form DF — 컬럼: ``week_start_date`` (Date, ISO week Monday),
        ``iso_year``, ``iso_week``, ``age_group`` (sum_over 에 없으면), 그리고
        ``sum_over`` 에 포함 안 된 dimension + ``episodes``.

        sum_over 가 ``("sido_code", "sex")`` 면 결과 schema:
            ``week_start_date``, ``iso_year``, ``iso_week``, ``age_group``,
            ``episodes``.
    """
    expected = {"date", "sido_code", "sex", "age_group", "episodes"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(
            f"df missing columns {sorted(missing)}; expected {sorted(expected)}"
        )
    sum_over_set = set(sum_over)
    invalid = sum_over_set - {"sido_code", "sex"}
    if invalid:
        raise ValueError(
            f"sum_over must subset of ('sido_code', 'sex'), got extras {sorted(invalid)}"
        )

    # week_start_date = ISO week 의 월요일.
    # polars: date.dt.truncate("1w") → 그 주의 월요일.
    with_week = df.with_columns(
        pl.col("date").dt.truncate("1w").alias("week_start_date"),
        pl.col("date").dt.iso_year().alias("iso_year"),
        pl.col("date").dt.week().alias("iso_week"),
    )

    group_cols: list[str] = ["week_start_date", "iso_year", "iso_week", "age_group"]
    # sum_over 에 없는 dimension 은 group 유지
    if "sido_code" not in sum_over_set:
        group_cols.append("sido_code")
    if "sex" not in sum_over_set:
        group_cols.append("sex")

    out = (
        with_week.group_by(group_cols)
        .agg(pl.col("episodes").sum().cast(pl.Int64))
        .sort(group_cols)
    )
    return out


def extract_hira_season(
    df_weekly: pl.DataFrame,
    season_start_year: int,
    season_start_week: int = 36,
    season_length_weeks: int = 52,
) -> pl.DataFrame:
    """주별 DF 에서 한 시즌 (default ISO 36 ~ 다음해 ISO 35, 52 주) 잘라내기.

    Args:
        df_weekly: ``aggregate_hira_weekly`` 결과 (``week_start_date`` 컬럼 필수).
        season_start_year: 시즌 시작 연도 (예: 2019 → 2019-2020 시즌).
        season_start_week: ISO week. default 36 (질병청 ILI 시즌 정의와 일치).
        season_length_weeks: default 52 (모든 시즌 통일).

    Returns:
        부분 DF + ``week_in_season`` (0..N-1) 컬럼 추가.
    """
    if "week_start_date" not in df_weekly.columns:
        raise ValueError(
            "df_weekly must have 'week_start_date' column "
            "(call aggregate_hira_weekly first)"
        )

    start_date = _date.fromisocalendar(season_start_year, season_start_week, 1)
    # season 끝: start + season_length_weeks - 1 주의 월요일 (그 주 일요일까지 포함)
    # week_start_date 가 그 월요일 이전이면 포함.
    end_week_date = _date.fromordinal(
        start_date.toordinal() + (season_length_weeks - 1) * 7
    )

    sub = (
        df_weekly.filter(
            (pl.col("week_start_date") >= start_date)
            & (pl.col("week_start_date") <= end_week_date)
        )
        .with_columns(
            (
                (pl.col("week_start_date") - pl.lit(start_date)).dt.total_days() // 7
            ).cast(pl.Int32).alias("week_in_season")
        )
        .sort(["week_start_date"])
    )
    return sub


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== HIRA xlsx ===")
    p = _get_xlsx_path()
    print(f"path: {p}")
    print(f"size: {p.stat().st_size / 1e6:.1f} MB")

    df_out = load_hira_episodes(setting="outpatient_inpatient")
    print(f"\n외래입원: {df_out.height:,} rows, "
          f"episodes sum = {df_out['episodes'].sum():,}")
    df_in = load_hira_episodes(setting="inpatient_only")
    print(f"입원:     {df_in.height:,} rows, "
          f"episodes sum = {df_in['episodes'].sum():,}")

    print("\n--- 수도권 외래입원 ---")
    df_sg = load_hira_episodes(
        setting="outpatient_inpatient",
        sido_codes=SUDOGWON_SIDO_CODES,
    )
    print(f"rows = {df_sg.height:,}, episodes sum = {df_sg['episodes'].sum():,}")

    print("\n--- 2019-2020 시즌 (수도권, 외래입원, 9/1-8/31) ---")
    df_19 = load_hira_episodes(
        setting="outpatient_inpatient",
        sido_codes=SUDOGWON_SIDO_CODES,
        date_range=("2019-09-01", "2020-08-31"),
    )
    print(f"episodes sum = {df_19['episodes'].sum():,}")

    print("\n--- 주별 집계 (수도권 전체 합산 후 연령별) ---")
    weekly = aggregate_hira_weekly(df_sg, sum_over=("sido_code", "sex"))
    print(weekly.head(8))
    print(f"weekly rows: {weekly.height:,}")
    print(f"sum check (weekly == daily): "
          f"{weekly['episodes'].sum() == df_sg['episodes'].sum()}")

    print("\n--- 시즌 추출 (2019-2020) ---")
    season = extract_hira_season(weekly, season_start_year=2019)
    print(f"season rows: {season.height:,}")
    print(f"week_in_season range: {season['week_in_season'].min()} ~ "
          f"{season['week_in_season'].max()}")
