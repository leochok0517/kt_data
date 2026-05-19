"""Tests for src.data.load_calendar."""

from __future__ import annotations

import pytest

from src.data.load_calendar import (
    DAYTYPES,
    HOLIDAYS_2018_2023,
    classify_date,
    get_daytype_for_range,
    is_holiday,
    is_school_in_session,
)


def test_2023_new_year_is_holiday() -> None:
    # 2023-01-01 일요일 + 신정 → holiday 우선
    assert classify_date(20230101) == "holiday"


def test_2023_jan2_vacation_weekday() -> None:
    # 2023-01-02 월 + 겨울방학
    assert classify_date(20230102) == "vacation_weekday"


def test_2023_mar13_weekday_school() -> None:
    # 2023-03-13 월 + 1학기 (3/1 이후)
    assert classify_date(20230313) == "weekday_school"


def test_2023_mar11_weekend() -> None:
    # 2023-03-11 토
    assert classify_date(20230311) == "weekend"


def test_2023_815_holiday() -> None:
    # 2023-08-15 화 + 광복절
    assert classify_date(20230815) == "holiday"


def test_no_fall_break_2023() -> None:
    """가을(9월~12월 20일)에 방학(vacation_weekday)이 없어야."""
    df = get_daytype_for_range(20230820, 20231220)
    assert (df.filter(df["daytype"] == "vacation_weekday").height) == 0


def test_new_year_each_year_is_holiday() -> None:
    for y in range(2018, 2024):
        assert classify_date(y * 10000 + 101) == "holiday", y


def test_range_covers_full_year_2023() -> None:
    df = get_daytype_for_range(20230101, 20231231)
    assert df.height == 365


def test_leap_year_2020_feb29() -> None:
    # 2020-02-29 토 + 방학기간 → weekend 우선
    assert classify_date(20200229) == "weekend"
    df = get_daytype_for_range(20200101, 20201231)
    assert df.height == 366


def test_school_session_boundaries() -> None:
    assert is_school_in_session(20230301)  # 학기 시작
    assert is_school_in_session(20230720)  # 학기 마지막
    assert not is_school_in_session(20230721)  # 여름방학 시작
    assert not is_school_in_session(20230819)  # 여름방학 마지막
    assert is_school_in_session(20230820)  # 2학기 시작
    assert is_school_in_session(20231220)  # 2학기 마지막
    assert not is_school_in_session(20231221)  # 겨울방학 시작


def test_daytype_universe(df_2023: object = None) -> None:
    df = get_daytype_for_range(20230101, 20231231)
    got = set(df["daytype"].unique().to_list())
    assert got <= set(DAYTYPES)


def test_holidays_set_nonempty() -> None:
    assert len(HOLIDAYS_2018_2023) > 80  # ~100여 개


def test_is_holiday_consistency() -> None:
    # 한 샘플 케이스
    assert is_holiday(20230815)
    assert not is_holiday(20230816)
