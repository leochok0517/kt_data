"""Tests for src.data.load_population."""

from __future__ import annotations

import polars as pl
import pytest

from src.data.load_population import (
    AGE_LABELS_15,
    AGE_STARTS_15,
    get_population_matrix,
    load_population_15groups,
)


@pytest.fixture(scope="module")
def df() -> pl.DataFrame:
    return load_population_15groups()


def test_15_groups_per_admdong(df: pl.DataFrame) -> None:
    n_admdong = df.select("admdong_cd").n_unique()
    assert df.height == n_admdong * 15, (df.height, n_admdong * 15)


def test_age_idx_range(df: pl.DataFrame) -> None:
    idx_set = set(df.get_column("age_idx").unique().to_list())
    assert idx_set == set(range(15)), idx_set


def test_age_labels_consistent(df: pl.DataFrame) -> None:
    mapping = df.group_by("age_idx").agg(pl.col("age_group").first()).sort("age_idx")
    got = mapping.get_column("age_group").to_list()
    assert got == AGE_LABELS_15, got


def test_sudogwon_total(df: pl.DataFrame) -> None:
    total = int(df["pop"].sum())
    assert 24_000_000 <= total <= 28_000_000, total


def test_all_admdongs_have_15_rows(df: pl.DataFrame) -> None:
    counts = df.group_by("admdong_cd").len()
    assert (counts["len"] == 15).all()


def test_70plus_equals_raw_sum() -> None:
    """'70+' 그룹 = 원본 70,75,80,85,90,95,100 합."""
    raw = pl.read_parquet("data/mapping/mois_population_202301.parquet")
    raw = raw.filter(pl.col("sido_nm").is_in(["서울특별시", "경기도", "인천광역시"]))

    raw_70plus = int(raw.filter(pl.col("age_5_start") >= 70)["pop_5"].sum())
    df = load_population_15groups()
    grouped_70plus = int(df.filter(pl.col("age_group") == "70+")["pop"].sum())
    assert raw_70plus == grouped_70plus, (raw_70plus, grouped_70plus)


def test_matrix_shape_and_sum(df: pl.DataFrame) -> None:
    N, admdongs, labels = get_population_matrix(df)
    assert N.shape == (len(admdongs), 15)
    assert labels == AGE_LABELS_15
    assert N.sum() == int(df["pop"].sum())


def test_age_starts_match() -> None:
    assert len(AGE_STARTS_15) == 15
    assert AGE_STARTS_15[-1] == 70
