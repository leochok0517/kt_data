"""Tests for kt_data.data.load_hira."""

from __future__ import annotations

import datetime as _dt

import polars as pl
import pytest

from kt_data.data.load_hira import (
    HIRA_AGE_GROUPS,
    HIRA_SIDO_CODES,
    SUDOGWON_SIDO_CODES,
    _AGE_LABEL_MAP,
    _HIRA_XLSX_NAME,
    _SEX_MAP,
    _get_xlsx_path,
    _read_episode_sheet,
    aggregate_hira_weekly,
    extract_hira_season,
    load_hira_episodes,
)
from kt_data.data import DATA_ROOT

# Skip live-data tests if xlsx is missing
_XLSX_PATH = DATA_ROOT / "external" / "hira" / _HIRA_XLSX_NAME
_HAS_FILE = _XLSX_PATH.exists()
requires_file = pytest.mark.skipif(
    not _HAS_FILE, reason=f"HIRA xlsx not at {_XLSX_PATH}"
)


# ---------- pure constants ----------

def test_age_groups_constants() -> None:
    assert HIRA_AGE_GROUPS == ["0-5", "6-11", "12-17", "18-44", "45-64", "65+"]
    assert len(HIRA_AGE_GROUPS) == 6


def test_age_label_map_covers_all_raw_prefixes() -> None:
    """raw 라벨 6개 모두 정규화 매핑됨."""
    assert len(_AGE_LABEL_MAP) == 6
    assert set(_AGE_LABEL_MAP.values()) == set(HIRA_AGE_GROUPS)


def test_sido_codes_constants() -> None:
    assert SUDOGWON_SIDO_CODES == [11, 28, 41]
    assert HIRA_SIDO_CODES[11] == "서울특별시"
    assert HIRA_SIDO_CODES[28] == "인천광역시"
    assert HIRA_SIDO_CODES[41] == "경기도"


def test_sido_codes_18_entries() -> None:
    """catalog 는 18개 (기존 + 자치도 신코드 51/52 병행)."""
    assert len(HIRA_SIDO_CODES) == 18


def test_sex_map() -> None:
    assert _SEX_MAP == {"남자": "M", "여자": "F"}


# ---------- file presence ----------

@requires_file
def test_xlsx_path_resolves() -> None:
    path = _get_xlsx_path()
    assert path.exists()
    assert path.name == _HIRA_XLSX_NAME


def test_missing_file_raises_helpful_error(tmp_path, monkeypatch) -> None:
    """파일 없으면 명확한 FileNotFoundError."""
    import kt_data.data.load_hira as mod
    fake_root = tmp_path / "data"
    monkeypatch.setattr(mod, "DATA_ROOT", fake_root)
    # lru_cache 무효화
    mod._read_episode_sheet.cache_clear()
    with pytest.raises(FileNotFoundError, match="HIRA xlsx not found"):
        mod._get_xlsx_path()


# ---------- schema / dtype ----------

@requires_file
def test_outpatient_schema() -> None:
    df = _read_episode_sheet("outpatient_inpatient")
    assert df.columns == ["date", "sido_code", "sex", "age_group", "episodes"]
    assert df.schema["date"] == pl.Date
    assert df.schema["sido_code"] == pl.Int64
    assert df.schema["sex"] == pl.String
    assert df.schema["age_group"] == pl.String
    assert df.schema["episodes"] == pl.Int64


@requires_file
def test_age_groups_all_present_in_data() -> None:
    df = load_hira_episodes(setting="outpatient_inpatient")
    got = set(df["age_group"].unique().to_list())
    assert got == set(HIRA_AGE_GROUPS)


@requires_file
def test_sex_normalized_to_M_F() -> None:
    df = load_hira_episodes(setting="outpatient_inpatient")
    assert set(df["sex"].unique().to_list()) == {"M", "F"}


@requires_file
def test_date_range_covers_2006_2024() -> None:
    df = load_hira_episodes(setting="outpatient_inpatient")
    assert df["date"].min() == _dt.date(2006, 1, 1)
    assert df["date"].max() == _dt.date(2024, 12, 31)


# ---------- known sums (★ 본 데이터 회귀 방지 fixture) ----------

@requires_file
def test_outpatient_inpatient_total_sum() -> None:
    df = load_hira_episodes(setting="outpatient_inpatient")
    assert int(df["episodes"].sum()) == 25_895_613


@requires_file
def test_inpatient_only_total_sum() -> None:
    df = load_hira_episodes(setting="inpatient_only")
    assert int(df["episodes"].sum()) == 1_849_881


@requires_file
def test_sudogwon_outpatient_inpatient_sum() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES,
    )
    assert int(df["episodes"].sum()) == 11_718_844


@requires_file
def test_sudogwon_2019_2020_season_sum() -> None:
    """수도권 2019-2020 시즌 (2019-09-01 ~ 2020-08-31, 외래입원)."""
    df = load_hira_episodes(
        setting="outpatient_inpatient",
        sido_codes=SUDOGWON_SIDO_CODES,
        date_range=("2019-09-01", "2020-08-31"),
    )
    assert int(df["episodes"].sum()) == 817_914


# ---------- filter behavior ----------

@requires_file
def test_sido_filter_returns_only_requested() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=[11, 41]
    )
    assert set(df["sido_code"].unique().to_list()) == {11, 41}


@requires_file
def test_age_group_filter_returns_only_requested() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", age_groups=["0-5", "65+"]
    )
    assert set(df["age_group"].unique().to_list()) == {"0-5", "65+"}


@requires_file
def test_sex_filter_M() -> None:
    df = load_hira_episodes(setting="outpatient_inpatient", sex="M")
    assert set(df["sex"].unique().to_list()) == {"M"}


@requires_file
def test_date_range_filter_inclusive() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", date_range=("2020-01-01", "2020-01-07")
    )
    assert df["date"].min() == _dt.date(2020, 1, 1)
    assert df["date"].max() == _dt.date(2020, 1, 7)


@requires_file
def test_invalid_age_group_raises() -> None:
    with pytest.raises(ValueError, match="unknown age_groups"):
        load_hira_episodes(setting="outpatient_inpatient", age_groups=["100+"])


@requires_file
def test_invalid_sex_raises() -> None:
    with pytest.raises(ValueError, match="sex must"):
        load_hira_episodes(setting="outpatient_inpatient", sex="other")  # type: ignore[arg-type]


def test_invalid_setting_raises() -> None:
    with pytest.raises(ValueError, match="setting must"):
        load_hira_episodes(setting="invalid")  # type: ignore[arg-type]


# ---------- aggregate_hira_weekly ----------

@requires_file
def test_aggregate_weekly_preserves_sum() -> None:
    """daily → weekly 합산 시 episodes 총합 보존."""
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES
    )
    weekly = aggregate_hira_weekly(df, sum_over=("sido_code", "sex"))
    assert int(weekly["episodes"].sum()) == int(df["episodes"].sum())


@requires_file
def test_aggregate_weekly_schema_default_sum_over() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES,
    )
    weekly = aggregate_hira_weekly(df)
    assert weekly.columns == [
        "week_start_date", "iso_year", "iso_week", "age_group", "episodes"
    ]


@requires_file
def test_aggregate_weekly_keeps_sido_when_not_summed() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES,
    )
    weekly = aggregate_hira_weekly(df, sum_over=("sex",))
    assert "sido_code" in weekly.columns
    assert set(weekly["sido_code"].unique().to_list()) == set(SUDOGWON_SIDO_CODES)


@requires_file
def test_aggregate_weekly_week_start_is_monday() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient",
        sido_codes=SUDOGWON_SIDO_CODES,
        date_range=("2020-01-01", "2020-01-31"),
    )
    weekly = aggregate_hira_weekly(df)
    for d in weekly["week_start_date"].to_list():
        assert d.weekday() == 0, f"{d} is not Monday"


def test_aggregate_weekly_rejects_missing_columns() -> None:
    bad = pl.DataFrame({"date": [_dt.date(2020, 1, 1)], "episodes": [1]})
    with pytest.raises(ValueError, match="df missing columns"):
        aggregate_hira_weekly(bad)


def test_aggregate_weekly_rejects_invalid_sum_over() -> None:
    df = pl.DataFrame({
        "date": [_dt.date(2020, 1, 1)],
        "sido_code": [11], "sex": ["M"], "age_group": ["0-5"], "episodes": [1],
    })
    with pytest.raises(ValueError, match="sum_over must subset"):
        aggregate_hira_weekly(df, sum_over=("age_group",))


# ---------- extract_hira_season ----------

@requires_file
def test_extract_season_default_52_weeks() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES,
    )
    weekly = aggregate_hira_weekly(df)
    season = extract_hira_season(weekly, season_start_year=2019)
    # 6 age groups × 52 weeks (각 그룹이 시즌 내 항상 데이터 있다고 가정)
    assert season["week_in_season"].n_unique() == 52
    assert season["week_in_season"].min() == 0
    assert season["week_in_season"].max() == 51


@requires_file
def test_extract_season_week_in_season_monotonic() -> None:
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES,
    )
    weekly = aggregate_hira_weekly(df)
    season = extract_hira_season(weekly, season_start_year=2019)
    dates_sorted = (
        season.select("week_start_date").unique().sort("week_start_date")
        ["week_start_date"].to_list()
    )
    assert len(dates_sorted) == 52
    for i in range(1, len(dates_sorted)):
        delta = (dates_sorted[i] - dates_sorted[i - 1]).days
        assert delta == 7


@requires_file
def test_extract_season_starts_iso_36() -> None:
    """ISO 36 Monday of 2019 = 2019-09-02."""
    df = load_hira_episodes(
        setting="outpatient_inpatient", sido_codes=SUDOGWON_SIDO_CODES,
    )
    weekly = aggregate_hira_weekly(df)
    season = extract_hira_season(weekly, season_start_year=2019)
    first_monday = season["week_start_date"].min()
    assert first_monday == _dt.date(2019, 9, 2)


def test_extract_season_requires_week_start_date() -> None:
    bad = pl.DataFrame({"date": [_dt.date(2020, 1, 1)], "episodes": [1]})
    with pytest.raises(ValueError, match="week_start_date"):
        extract_hira_season(bad, 2019)
