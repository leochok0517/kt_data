"""KT Movement parquet → mobility tensor (n_admdong × n_admdong × 7 ages × 24 hours).

연령 처리:
- age_10=0  (0-9세)   → 사용 안 함 (정적 모델)
- age_10=10           → 10-19
- age_10=20..60       → 그대로
- age_10=70, 80       → '70+'로 합산 (마지막 인덱스 6)

결과 7 그룹: [10, 20, 30, 40, 50, 60, 70] — 인덱스 0..6

날짜 처리:
- 공휴일은 'weekend'로 분류
- pi[o, d, a, h] = 해당 daytype의 일 평균 이동량
"""

from __future__ import annotations

import time
from datetime import date as date_cls
from pathlib import Path

import numpy as np
import polars as pl

from src.data.load_population import load_population_15groups

_MOVEMENT_DIR = Path("data/raw/movement")

AGE_GROUPS_USED: list[int] = [10, 20, 30, 40, 50, 60, 70]  # 70은 70+
N_AGES: int = 7
N_HOURS: int = 24

# 한국 공휴일 2018-2023 (yyyymmdd) — 신정/설/삼일절/어린이날(+대체)/부처님오신날/현충일/광복절/추석(+대체)/개천절/한글날/성탄절 + 임시공휴일·선거일
HOLIDAYS: set[int] = {
    # 2018
    20180101, 20180215, 20180216, 20180217, 20180301,
    20180505, 20180507, 20180522, 20180606, 20180613,
    20180815, 20180923, 20180924, 20180925, 20180926,
    20181003, 20181009, 20181225,
    # 2019
    20190101, 20190204, 20190205, 20190206, 20190301,
    20190505, 20190506, 20190512, 20190606,
    20190815, 20190912, 20190913, 20190914,
    20191003, 20191009, 20191225,
    # 2020
    20200101, 20200124, 20200125, 20200126, 20200127, 20200301,
    20200415, 20200430, 20200505, 20200606,
    20200815, 20200817, 20200930, 20201001, 20201002, 20201003,
    20201009, 20201225,
    # 2021
    20210101, 20210211, 20210212, 20210213, 20210301,
    20210505, 20210519, 20210606,
    20210815, 20210816, 20210920, 20210921, 20210922,
    20211003, 20211004, 20211009, 20211011, 20211225,
    # 2022
    20220101, 20220131, 20220201, 20220202, 20220301, 20220309,
    20220505, 20220508, 20220601, 20220606,
    20220815, 20220909, 20220910, 20220911, 20220912,
    20221003, 20221009, 20221010, 20221225,
    # 2023
    20230101, 20230121, 20230122, 20230123, 20230124, 20230301,
    20230505, 20230527, 20230529, 20230606,
    20230815, 20230928, 20230929, 20230930, 20231002, 20231003,
    20231009, 20231225,
}


def aggregate_daytype(yyyymmdd: int, holidays: set[int]) -> str:
    """yyyymmdd → 'weekday' or 'weekend' (공휴일은 weekend)."""
    if yyyymmdd in holidays:
        return "weekend"
    y, m, d = yyyymmdd // 10000, (yyyymmdd // 100) % 100, yyyymmdd % 100
    return "weekend" if date_cls(y, m, d).weekday() >= 5 else "weekday"


def get_admdong_index_map(
    population_df: pl.DataFrame | None = None,
) -> tuple[list[str], dict[str, int]]:
    """행정동 코드 → 인덱스. MOIS(주민등록) 행정동 목록을 sort 한 순서."""
    if population_df is None:
        population_df = load_population_15groups()
    codes = (
        population_df.select("admdong_cd")
        .unique()
        .sort("admdong_cd")
        .get_column("admdong_cd")
        .to_list()
    )
    return codes, {c: i for i, c in enumerate(codes)}


def load_mobility(
    yyyymm: str,
    daytype: str = "weekday",
    holidays: set[int] | None = None,
) -> dict:
    if daytype not in ("weekday", "weekend", "all"):
        raise ValueError(f"daytype must be weekday/weekend/all, got {daytype!r}")
    if holidays is None:
        holidays = HOLIDAYS

    t0 = time.perf_counter()
    path = _MOVEMENT_DIR / f"movement_sudogwon_{yyyymm}.parquet"
    if not path.exists():
        raise FileNotFoundError(path)

    admdong_codes, code_to_idx = get_admdong_index_map()
    n_adm = len(admdong_codes)

    lf = pl.scan_parquet(path).filter(
        pl.col("age_10").is_in([10, 20, 30, 40, 50, 60, 70, 80])
    )

    dates = (
        lf.select("date").unique().collect().get_column("date").to_list()
    )
    if daytype == "all":
        target_dates = [int(d) for d in dates]
    else:
        target_dates = [int(d) for d in dates if aggregate_daytype(int(d), holidays) == daytype]
    n_days = len(target_dates)
    if n_days == 0:
        raise ValueError(f"No {daytype} dates in {yyyymm}")

    lf = lf.filter(pl.col("date").is_in(target_dates)).with_columns(
        pl.when(pl.col("age_10") == 80)
        .then(pl.lit(70, dtype=pl.Int8))
        .otherwise(pl.col("age_10"))
        .alias("age_7")
    )
    grouped = (
        lf.group_by(["o_admdong_cd", "d_admdong_cd", "age_7", "hour"])
        .agg(pl.col("total").sum().alias("total_sum"))
        .collect(engine="streaming")
    )

    # ---- numpy tensor 채우기 ----
    pi = np.zeros((n_adm, n_adm, N_AGES, N_HOURS), dtype=np.float32)

    o_codes = grouped.get_column("o_admdong_cd").to_list()
    d_codes = grouped.get_column("d_admdong_cd").to_list()
    age_arr = grouped.get_column("age_7").to_numpy()
    hour_arr = grouped.get_column("hour").to_numpy()
    vals = (grouped.get_column("total_sum").to_numpy() / n_days).astype(np.float32)

    get = code_to_idx.get
    o_idx = np.fromiter((get(c, -1) for c in o_codes), dtype=np.int64, count=len(o_codes))
    d_idx = np.fromiter((get(c, -1) for c in d_codes), dtype=np.int64, count=len(d_codes))
    valid = (o_idx >= 0) & (d_idx >= 0)

    o_idx = o_idx[valid]
    d_idx = d_idx[valid]
    a_idx = (age_arr[valid] // 10 - 1).astype(np.int64)  # 10→0, 20→1, ..., 70→6
    h_idx = hour_arr[valid].astype(np.int64)
    pi[o_idx, d_idx, a_idx, h_idx] = vals[valid]

    elapsed = time.perf_counter() - t0
    return {
        "pi": pi,
        "admdong_codes": admdong_codes,
        "age_groups_used": AGE_GROUPS_USED,
        "daytype": daytype,
        "n_days": n_days,
        "metadata": {
            "yyyymm": yyyymm,
            "elapsed_sec": elapsed,
            "n_admdong": n_adm,
            "n_rows_groupby": grouped.height,
            "n_rows_unmapped": int((~valid).sum()),
            "source": str(path),
        },
    }


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    result = load_mobility("202301", daytype="weekday")
    pi = result["pi"]
    print(f"pi shape:       {pi.shape}")
    print(f"admdong count:  {len(result['admdong_codes'])}")
    print(f"age groups:     {result['age_groups_used']}")
    print(f"n_days:         {result['n_days']}")
    print(f"elapsed:        {result['metadata']['elapsed_sec']:.1f}s")
    print(f"unmapped rows:  {result['metadata']['n_rows_unmapped']:,}")
    print()
    print(f"Total mobility (per-day avg sum): {pi.sum():,.0f}")
    out_per_admdong = pi.sum(axis=(1, 2, 3))
    print(f"Out per admdong: mean={out_per_admdong.mean():,.0f}, max={out_per_admdong.max():,.0f}")
    print()
    age_sum = pi.sum(axis=(0, 1, 3))
    print("Age group sums:")
    for i, age in enumerate(result["age_groups_used"]):
        label = "70+" if age == 70 else f"{age}-{age+9}"
        print(f"  [{i}] {label:>5}: {age_sum[i]:,.0f}")

    hourly = pi.sum(axis=(0, 1, 2))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(24), hourly, color="steelblue")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Total mobility (per-day avg)")
    ax.set_title(f"Hourly mobility 2023-01 weekday (n_days={result['n_days']})")
    ax.set_xticks(range(0, 24, 2))
    plt.tight_layout()
    out = Path("outputs/load_mobility_check.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"\nsaved {out}")
