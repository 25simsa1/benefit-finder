from __future__ import annotations

from datetime import date

import pytest

from benefit_finder import fpl


def test_first_person_value() -> None:
    assert fpl.fpl(1) == 15_650


def test_family_of_five() -> None:
    assert fpl.fpl(5) == 15_650 + 4 * 5_500


def test_alaska_and_hawaii_are_higher() -> None:
    assert fpl.fpl(3, "AK") > fpl.fpl(3, "HI") > fpl.fpl(3, "KS")


def test_state_name_variants() -> None:
    assert fpl.fpl(2, "alaska") == fpl.fpl(2, "AK")
    assert fpl.fpl(2, "") == fpl.fpl(2, "KS")


def test_zero_size_rejected() -> None:
    with pytest.raises(ValueError):
        fpl.fpl(0)


def test_fpl_limit_percent() -> None:
    assert fpl.fpl_limit(5, 130) == pytest.approx(37_650 * 1.30)


def test_income_as_percent() -> None:
    assert fpl.income_as_percent_of_fpl(37_650, 5) == pytest.approx(100.0)


def test_warning_when_stale() -> None:
    warning = fpl.fpl_year_warning(today=date(fpl.FPL_YEAR + 1, 1, 15))
    assert warning is not None
    assert str(fpl.FPL_YEAR) in warning


def test_no_warning_when_current() -> None:
    assert fpl.fpl_year_warning(today=date(fpl.FPL_YEAR, 6, 1)) is None
