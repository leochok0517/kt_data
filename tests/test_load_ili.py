"""Tests for src.data.load_ili."""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from src.data.load_ili import (
    N_SLOTS,
    SEASON_WEEKS,
    get_ili_timeseries,
    get_season_length,
    load_ili_seasons,
    week_in_season_to_iso_week,
)


@pytest.fixture(scope="module")
def df() -> pl.DataFrame:
    return load_ili_seasons()


# ---- 기존 ----

def test_row_count(df: pl.DataFrame) -> None:
    assert df.height == 5 * N_SLOTS == 270


def test_seasons(df: pl.DataFrame) -> None:
    expected = {"2018-2019", "2019-2020", "2020-2021", "2021-2022", "2022-2023"}
    got = set(df.select("season").unique().get_column("season").to_list())
    assert got == expected


def test_week_in_season_range(df: pl.DataFrame) -> None:
    wks = df.get_column("week_in_season").unique().to_list()
    assert sorted(wks) == list(range(N_SLOTS))


def test_covid_seasons_below_normal(df: pl.DataFrame) -> None:
    """코로나 시즌 평균이 정상 시즌보다 낮아야 (is_valid_week 만)."""
    df_v = df.filter(pl.col("is_valid_week"))
    normal = [
        float(df_v.filter(pl.col("season") == s)["ili_rate"].drop_nans().mean())
        for s in ("2018-2019", "2022-2023")
    ]
    baseline = min(normal)
    for s in ("2020-2021", "2021-2022"):
        m = float(df_v.filter(pl.col("season") == s)["ili_rate"].drop_nans().mean())
        assert m < baseline, (s, m, baseline)
    m_2020 = float(df_v.filter(pl.col("season") == "2020-2021")["ili_rate"].drop_nans().mean())
    assert m_2020 < 2.0, m_2020


def test_normal_seasons_high_max(df: pl.DataFrame) -> None:
    df_v = df.filter(pl.col("is_valid_week"))
    for s in ("2018-2019", "2022-2023"):
        mx = float(df_v.filter(pl.col("season") == s)["ili_rate"].drop_nans().max())
        assert mx > 5.0, (s, mx)


def test_nan_present(df: pl.DataFrame) -> None:
    """4개 시즌이 week 17 결측 → valid 영역 내 NaN 보유."""
    valid_only = df.filter(pl.col("is_valid_week"))
    counts = (
        valid_only.group_by("season")
        .agg(pl.col("ili_rate").is_nan().sum().alias("nan"))
        .sort("season")
    )
    n_with_nan = int((counts["nan"] > 0).sum())
    assert n_with_nan >= 4


def test_get_timeseries_length(df: pl.DataFrame) -> None:
    ts = get_ili_timeseries("2022-2023", df=df)
    assert ts.shape == (SEASON_WEEKS["2022-2023"],)


def test_get_timeseries_full_slots(df: pl.DataFrame) -> None:
    ts = get_ili_timeseries("2022-2023", valid_only=False, df=df)
    assert ts.shape == (N_SLOTS,)


def test_get_timeseries_unknown_season(df: pl.DataFrame) -> None:
    with pytest.raises(ValueError):
        get_ili_timeseries("9999-0000", df=df)


def test_season_start_year_consistent(df: pl.DataFrame) -> None:
    for row in df.iter_rows(named=True):
        assert int(row["season"].split("-")[0]) == row["season_start_year"]


# ---- 새 테스트 ----

def test_season_weeks_dict_unified() -> None:
    """모든 시즌 52주로 통일."""
    assert all(v == 52 for v in SEASON_WEEKS.values())
    assert set(SEASON_WEEKS.keys()) == {
        "2018-2019", "2019-2020", "2020-2021", "2021-2022", "2022-2023"
    }


def test_get_season_length_unified() -> None:
    for s in SEASON_WEEKS:
        assert get_season_length(s) == 52


def test_iso_week_mapping_uniform() -> None:
    """모든 시즌 동일 매핑: w 0..16 → start year 36..52, w 17..51 → next year 1..35."""
    for season, start in (("2018-2019", 2018), ("2020-2021", 2020), ("2022-2023", 2022)):
        assert week_in_season_to_iso_week(season, 0) == (start, 36)
        assert week_in_season_to_iso_week(season, 16) == (start, 52)
        assert week_in_season_to_iso_week(season, 17) == (start + 1, 1)
        assert week_in_season_to_iso_week(season, 51) == (start + 1, 35)


def test_iso_week_mapping_out_of_range() -> None:
    """0..51만 valid — 모든 시즌 동일."""
    for season in ("2018-2019", "2020-2021"):
        with pytest.raises(ValueError):
            week_in_season_to_iso_week(season, 52)
        with pytest.raises(ValueError):
            week_in_season_to_iso_week(season, -1)


def test_is_valid_week_matches_season_length(df: pl.DataFrame) -> None:
    for season, length in SEASON_WEEKS.items():
        sub = df.filter(pl.col("season") == season)
        valid = sub.filter(pl.col("is_valid_week"))
        assert valid.height == length, (season, valid.height, length)


def test_invalid_weeks_have_nan(df: pl.DataFrame) -> None:
    invalid = df.filter(~pl.col("is_valid_week"))
    assert invalid.height > 0
    assert invalid["ili_rate"].is_nan().all()


def test_iso_week_in_valid_range(df: pl.DataFrame) -> None:
    valid = df.filter(pl.col("is_valid_week"))
    iso = set(valid["iso_week"].unique().to_list())
    # 36..52(or 53) ∪ 1..35
    expected_max = max(iso)
    expected_min = min(iso)
    assert expected_min >= 1 and expected_max <= 53
