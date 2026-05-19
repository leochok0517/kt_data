"""Tests for src.data.load_mobility."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from src.data.load_mobility import (
    AGE_GROUPS_USED,
    HOLIDAYS,
    N_AGES,
    N_HOURS,
    aggregate_daytype,
    get_admdong_index_map,
    load_mobility,
)


@pytest.fixture(scope="module")
def weekday() -> dict:
    return load_mobility("202301", daytype="weekday")


@pytest.fixture(scope="module")
def weekend() -> dict:
    return load_mobility("202301", daytype="weekend")


def test_shape(weekday: dict) -> None:
    n = len(weekday["admdong_codes"])
    assert weekday["pi"].shape == (n, n, N_AGES, N_HOURS)


def test_no_negative(weekday: dict) -> None:
    assert (weekday["pi"] >= 0).all()


def test_no_nan(weekday: dict) -> None:
    assert not np.isnan(weekday["pi"]).any()


def test_age_groups(weekday: dict) -> None:
    assert weekday["age_groups_used"] == AGE_GROUPS_USED
    assert len(AGE_GROUPS_USED) == 7


def test_hour_variation(weekday: dict) -> None:
    hourly = weekday["pi"].sum(axis=(0, 1, 2))
    assert hourly.std() > 0  # 시간대에 따라 변동 있어야


def test_weekday_higher_than_weekend(weekday: dict, weekend: dict) -> None:
    """평일 1일 평균 이동량이 주말보다 커야 (통근/통학 효과)."""
    assert weekday["pi"].sum() > weekend["pi"].sum()


def test_daytype_classification() -> None:
    assert aggregate_daytype(20230101, HOLIDAYS) == "weekend"  # 일요일+신정
    assert aggregate_daytype(20230102, HOLIDAYS) == "weekday"  # 월
    assert aggregate_daytype(20230107, HOLIDAYS) == "weekend"  # 토
    assert aggregate_daytype(20230108, HOLIDAYS) == "weekend"  # 일
    assert aggregate_daytype(20230121, HOLIDAYS) == "weekend"  # 설날
    assert aggregate_daytype(20230301, HOLIDAYS) == "weekend"  # 삼일절 (수요일이지만 휴일)


def test_index_map_consistent() -> None:
    codes, code_to_idx = get_admdong_index_map()
    assert len(codes) == len(code_to_idx)
    for i, c in enumerate(codes):
        assert code_to_idx[c] == i


def test_n_days_matches(weekday: dict) -> None:
    """1월에 평일 수는 약 18~22일 사이여야."""
    assert 17 <= weekday["n_days"] <= 23, weekday["n_days"]


def test_no_zero_dimensional_collapse(weekday: dict) -> None:
    """전체가 0 텐서가 아니어야."""
    assert weekday["pi"].sum() > 0
