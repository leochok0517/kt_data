"""Tests for src.data.load_contact."""

from __future__ import annotations

import numpy as np
import pytest

from kt_data.data.load_contact import (
    AGE_LABELS_15,
    DEFAULT_LAMBDAS,
    SETTINGS,
    get_contact_matrix,
    load_contact_matrices,
)

# 명세상 합 (NIMS 15군)
EXPECTED_SUMS = {
    "C_home": 23.26,
    "C_work": 17.03,
    "C_school": 14.24,
    "C_other": 31.77,
}


@pytest.fixture(scope="module")
def matrices() -> dict:
    return load_contact_matrices()


@pytest.fixture(scope="module")
def matrices_raw() -> dict:
    return load_contact_matrices(transpose_to_model_convention=False)


def test_shapes(matrices: dict) -> None:
    for s in SETTINGS:
        assert matrices[f"C_{s}"].shape == (15, 15)


def test_no_negative(matrices: dict) -> None:
    for s in SETTINGS:
        assert (matrices[f"C_{s}"] >= 0).all()


def test_diagonal_nonnegative_home_other(matrices: dict) -> None:
    """home, other 는 모든 연령에서 자기 연령 만남이 양수.
    work/school은 비통학·비취업 연령에서 0이 정상."""
    for s in ("home", "other"):
        diag = np.diag(matrices[f"C_{s}"])
        assert (diag > 0).all(), (s, diag)


def test_sums_match_spec(matrices: dict) -> None:
    for key, expected in EXPECTED_SUMS.items():
        got = matrices[key].sum()
        assert abs(got - expected) < 0.1, (key, got, expected)


def test_transpose_applied(matrices: dict, matrices_raw: dict) -> None:
    """transpose=True 결과는 raw의 .T 와 같아야."""
    for s in SETTINGS:
        np.testing.assert_array_equal(matrices[f"C_{s}"], matrices_raw[f"C_{s}"].T)


def test_age_labels(matrices: dict) -> None:
    assert matrices["age_labels"] == AGE_LABELS_15
    assert len(matrices["age_starts"]) == 15


def test_weekday_higher_than_weekend(matrices: dict) -> None:
    """평일 학기 (school 1.0) > 주말 (school 0, work 0.2)."""
    C_wd = get_contact_matrix(matrices, "weekday_school")
    C_we = get_contact_matrix(matrices, "weekend")
    assert C_wd.sum() > C_we.sum()


def test_school_vacation_reduces_contacts(matrices: dict) -> None:
    """방학 평일 (school 0.2) < 학기 평일 (school 1.0)."""
    C_school = get_contact_matrix(matrices, "weekday_school")
    C_vac = get_contact_matrix(matrices, "vacation_weekday")
    assert C_school.sum() > C_vac.sum()


def test_custom_lambdas(matrices: dict) -> None:
    custom = {"home": 2.0, "work": 0.0, "school": 0.0, "other": 0.0}
    C = get_contact_matrix(matrices, "anything", lambdas=custom)
    np.testing.assert_array_equal(C, 2.0 * matrices["C_home"])


def test_unknown_daytype_raises(matrices: dict) -> None:
    with pytest.raises(ValueError):
        get_contact_matrix(matrices, "bogus_daytype")


def test_default_lambdas_consistency() -> None:
    for daytype, ld in DEFAULT_LAMBDAS.items():
        assert set(ld.keys()) <= set(SETTINGS), daytype
        for v in ld.values():
            assert v >= 0
