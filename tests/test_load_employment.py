"""Unit tests for kt_data.data.load_employment."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kt_data.data.load_employment import (
    ADMDONG_PREFIX_TO_SIDO,
    AGE_LABEL_TO_NIMS_IDX,
    SIDO_NORM_MAP,
    build_rho_matrix,
    get_sido_array,
    get_sido_from_admdong,
    load_employment_rate,
)


# ---------- load_employment_rate ----------

def test_load_basic_columns_and_shape() -> None:
    df = load_employment_rate()
    assert {
        "sido_nm", "age_label", "age_idx",
        "population_15plus", "employed", "employment_rate",
    }.issubset(set(df.columns))
    # 17 시도 × 12 연령 (15-19 ~ 70+)
    assert df.height == 17 * 12


def test_load_sido_normalized() -> None:
    df = load_employment_rate()
    sido_set = set(df.get_column("sido_nm").unique().to_list())
    # 약칭으로 정규화
    assert "서울" in sido_set
    assert "경기" in sido_set
    assert "인천" in sido_set
    # 원본 풀네임은 없음
    assert "서울특별시" not in sido_set


def test_load_only_specified_sex() -> None:
    df_total = load_employment_rate(sex="계")
    df_male = load_employment_rate(sex="남자")
    df_female = load_employment_rate(sex="여자")
    # 합산은 (남+여 ≈ 계) — 인구 기준
    pop_t = df_total["population_15plus"].sum()
    pop_m = df_male["population_15plus"].sum()
    pop_f = df_female["population_15plus"].sum()
    assert abs(pop_t - (pop_m + pop_f)) <= 10   # 반올림 허용


def test_load_invalid_sex_raises() -> None:
    with pytest.raises(ValueError):
        load_employment_rate(sex="기타")


def test_load_age_idx_range() -> None:
    df = load_employment_rate()
    ages = df.get_column("age_idx").unique().to_list()
    assert min(ages) == 3
    assert max(ages) == 14
    assert len(ages) == 12   # 3..14


def test_load_employment_rate_in_unit_interval() -> None:
    df = load_employment_rate()
    rates = df.get_column("employment_rate").to_numpy()
    assert (rates >= 0).all()
    assert (rates <= 1).all()


def test_load_sudogwon_present() -> None:
    df = load_employment_rate()
    seoul = df.filter(pl.col("sido_nm") == "서울")
    gyeonggi = df.filter(pl.col("sido_nm") == "경기")
    incheon = df.filter(pl.col("sido_nm") == "인천")
    assert seoul.height == 12
    assert gyeonggi.height == 12
    assert incheon.height == 12


def test_load_30s_higher_than_70plus() -> None:
    """경제활동 정점(30대) > 노인(70+) 검증."""
    df = load_employment_rate().filter(pl.col("sido_nm") == "서울")
    rate_30_34 = df.filter(pl.col("age_idx") == 6).get_column("employment_rate")[0]
    rate_70 = df.filter(pl.col("age_idx") == 14).get_column("employment_rate")[0]
    assert rate_30_34 > rate_70


# ---------- get_sido_from_admdong ----------

def test_get_sido_from_admdong_known_prefixes() -> None:
    assert get_sido_from_admdong("1101053") == "서울"
    assert get_sido_from_admdong("2826000") == "인천"
    assert get_sido_from_admdong("4111000") == "경기"


def test_get_sido_from_admdong_unknown() -> None:
    assert get_sido_from_admdong("4400000") == "unknown"
    assert get_sido_from_admdong("") == "unknown"


def test_get_sido_array() -> None:
    codes = ["1101000", "4100000", "2800000", "9999999"]
    out = get_sido_array(codes)
    assert out == ["서울", "경기", "인천", "unknown"]


# ---------- build_rho_matrix ----------

def test_build_rho_shape() -> None:
    codes = ["1100000", "4100000", "2800000"]
    rho = build_rho_matrix(codes)
    assert rho.shape == (3, 15)


def test_build_rho_under_15_zero() -> None:
    codes = ["1100000"] * 5
    rho = build_rho_matrix(codes)
    np.testing.assert_array_equal(rho[:, 0:3], 0.0)


def test_build_rho_sudogwon_matches_employment_df() -> None:
    """ρ[i, a] 가 employment_df 값과 일치 (수도권)."""
    df = load_employment_rate()
    codes = ["1100000", "4100000", "2800000"]
    rho = build_rho_matrix(codes, employment_df=df)
    rate_seoul_25_29 = df.filter(
        (pl.col("sido_nm") == "서울") & (pl.col("age_idx") == 5)
    ).get_column("employment_rate")[0]
    assert rho[0, 5] == pytest.approx(rate_seoul_25_29)


def test_build_rho_unknown_sido_filled_default() -> None:
    rho = build_rho_matrix(
        ["9900000"], fill_unknown_sido=0.42,
    )
    # 15+ 만 fill_unknown_sido 로 채워짐, 0-14 는 fill_under_15(=0)
    np.testing.assert_array_equal(rho[0, 0:3], 0.0)
    np.testing.assert_array_equal(rho[0, 3:], 0.42)


def test_build_rho_custom_sido_array() -> None:
    """직접 시도 지정 시 admdong 코드 prefix 무시."""
    codes = ["9999999"]   # unknown prefix
    rho = build_rho_matrix(codes, sido_nm_per_admdong=["서울"])
    # 서울 25-29 고용률이 채워졌어야 함 (> 0)
    assert rho[0, 5] > 0


def test_build_rho_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        build_rho_matrix(["1100000", "4100000"], sido_nm_per_admdong=["서울"])


# ---------- 상수 일관성 ----------

def test_age_map_length_12() -> None:
    assert len(AGE_LABEL_TO_NIMS_IDX) == 12


def test_sido_map_covers_17_provinces() -> None:
    # 17 시도 + 강원/전북 별칭 → 약칭 set 크기 17
    abbrs = set(SIDO_NORM_MAP.values())
    assert len(abbrs) == 17


def test_admdong_prefix_map() -> None:
    assert ADMDONG_PREFIX_TO_SIDO == {"11": "서울", "28": "인천", "41": "경기"}
