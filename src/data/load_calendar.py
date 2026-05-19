"""달력 분류: yyyymmdd → daytype ('weekday_school', 'vacation_weekday', 'weekend', 'holiday').

우선순위: holiday > weekend > weekday_school / vacation_weekday

학사 캘린더(단순화):
- 학기:   3/1 ~ 7/20  AND  8/20 ~ 12/20
- 방학:   1/1 ~ 2/28(29) AND  7/21 ~ 8/19  AND  12/21 ~ 12/31
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta

import polars as pl

DAYTYPES = ("weekday_school", "vacation_weekday", "weekend", "holiday")

HOLIDAYS_2018_2023: set[int] = {
    # 2018
    20180101,
    20180215, 20180216, 20180217,
    20180301,
    20180505, 20180507,
    20180522,
    20180606,
    20180813, 20180815,
    20180923, 20180924, 20180925, 20180926,
    20181003, 20181009, 20181225,
    # 2019
    20190101,
    20190204, 20190205, 20190206,
    20190301,
    20190505, 20190506, 20190512,
    20190606,
    20190815,
    20190912, 20190913, 20190914,
    20191003, 20191009, 20191225,
    # 2020
    20200101,
    20200124, 20200125, 20200126, 20200127,
    20200301,
    20200430, 20200505, 20200606,
    20200815, 20200817,
    20200930, 20201001, 20201002, 20201003,
    20201009, 20201225,
    # 2021
    20210101,
    20210211, 20210212, 20210213,
    20210301,
    20210505, 20210519,
    20210606,
    20210815, 20210816,
    20210920, 20210921, 20210922,
    20211003, 20211004,
    20211009, 20211011, 20211225,
    # 2022
    20220101,
    20220131, 20220201, 20220202,
    20220301, 20220309,
    20220505, 20220508, 20220601, 20220606,
    20220815,
    20220909, 20220910, 20220911, 20220912,
    20221003, 20221009, 20221010, 20221225,
    # 2023
    20230101,
    20230121, 20230122, 20230123, 20230124,
    20230301,
    20230505, 20230527, 20230529,
    20230606,
    20230815,
    20230928, 20230929, 20230930, 20231002, 20231003,
    20231009, 20231225,
}


def _to_date(yyyymmdd: int) -> date_cls:
    return date_cls(yyyymmdd // 10000, (yyyymmdd // 100) % 100, yyyymmdd % 100)


def is_holiday(yyyymmdd: int) -> bool:
    return yyyymmdd in HOLIDAYS_2018_2023


def is_school_in_session(yyyymmdd: int) -> bool:
    """학기: 3/1 ~ 7/20 또는 8/20 ~ 12/20 (월/일만으로 판정, 연도 무관)."""
    md = yyyymmdd % 10000  # mmdd
    return (301 <= md <= 720) or (820 <= md <= 1220)


def classify_date(yyyymmdd: int) -> str:
    if is_holiday(yyyymmdd):
        return "holiday"
    if _to_date(yyyymmdd).weekday() >= 5:
        return "weekend"
    return "weekday_school" if is_school_in_session(yyyymmdd) else "vacation_weekday"


def get_daytype_for_range(
    start_yyyymmdd: int,
    end_yyyymmdd: int,
) -> pl.DataFrame:
    """[start, end] 닫힌 구간의 date / weekday / daytype DataFrame."""
    start = _to_date(start_yyyymmdd)
    end = _to_date(end_yyyymmdd)
    if start > end:
        raise ValueError(f"start {start_yyyymmdd} > end {end_yyyymmdd}")

    rows = []
    cur = start
    while cur <= end:
        ymd = cur.year * 10000 + cur.month * 100 + cur.day
        rows.append((ymd, cur.weekday(), classify_date(ymd)))
        cur += timedelta(days=1)

    return pl.DataFrame(
        rows,
        schema=[("date", pl.Int32), ("weekday", pl.Int8), ("daytype", pl.String)],
        orient="row",
    )


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    test_cases = [
        (20230101, "holiday"),
        (20230102, "vacation_weekday"),
        (20230307, "weekday_school"),
        (20230311, "weekend"),
        (20230725, "vacation_weekday"),
        (20230905, "weekday_school"),
        (20231225, "holiday"),
        (20180215, "holiday"),
    ]
    print("=== classify_date spot tests ===")
    for ymd, expected in test_cases:
        actual = classify_date(ymd)
        status = "PASS" if actual == expected else "FAIL"
        print(f"  [{status}] {ymd}: got={actual!r:<22} expected={expected!r}")

    df = get_daytype_for_range(20230101, 20231231)
    print(f"\n2023 row count: {df.height} (expected 365)")
    print("\ndaytype 분포 (2023):")
    counts = df.group_by("daytype").agg(pl.len().alias("n")).sort("daytype")
    print(counts)
    print(f"  total = {counts['n'].sum()}")

    color_map = {
        "weekday_school": "C0",
        "vacation_weekday": "C1",
        "weekend": "C2",
        "holiday": "C3",
    }
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = counts["daytype"].to_list()
    ax.bar(labels, counts["n"].to_list(), color=[color_map[d] for d in labels])
    for i, n in enumerate(counts["n"].to_list()):
        ax.text(i, n + 2, str(n), ha="center")
    ax.set_ylabel("Days")
    ax.set_title("2023 daytype distribution")
    plt.tight_layout()
    from pathlib import Path

    out = Path("outputs/load_calendar_check.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"\nsaved {out}")
