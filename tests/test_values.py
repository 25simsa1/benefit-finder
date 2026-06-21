from __future__ import annotations

import pytest

from benefit_finder.models import Household, Member
from benefit_finder.values import compute_builtin, estimate_value


def test_eitc_mfj_three_kids_45k(ks_family5) -> None:
    est = compute_builtin("eitc", ks_family5)
    # 2025 params, 3 kids MFJ. 8046 - (45000 - 30470) * 0.2106 = 4986
    assert est.high == pytest.approx(4_986, abs=1)
    assert est.low == est.high


def test_eitc_zero_at_high_income(ks_family5) -> None:
    ks_family5.agi = 300_000
    assert compute_builtin("eitc", ks_family5).high == 0


def test_eitc_counts_college_student_under_24() -> None:
    hh = Household(
        state="KS",
        members=[
            Member(age=45, relationship="self", employed=True, income_type="w2"),
            Member(age=20, relationship="child", student="college"),
        ],
        agi=20_000,
    )
    est = compute_builtin("eitc", hh)
    # one qualifying child, hoh, plateau region -> max credit
    assert est.high == pytest.approx(4_328, abs=1)


def test_ctc_three_kids(ks_family5) -> None:
    est = compute_builtin("ctc_actc", ks_family5)
    assert est.high == 3 * 2_200
    # refundable floor, min(6600, 3*1700, 15% of (45000-2500))
    assert est.low == 3 * 1_700


def test_ctc_ignores_17_plus() -> None:
    hh = Household(
        state="KS",
        members=[
            Member(age=45, relationship="self"),
            Member(age=17, relationship="child", student="k12"),
        ],
        agi=30_000,
    )
    assert compute_builtin("ctc_actc", hh).high == 0


def test_savers_credit_tiers(ks_family5) -> None:
    est = compute_builtin("savers_credit", ks_family5)
    # mfj at 45k -> 50% tier, two employed adult contributors
    assert est.high == 0.5 * 2_000 * 2
    assert est.low == 0


def test_savers_credit_zero_over_ceiling(ks_family5) -> None:
    ks_family5.agi = 100_000
    assert compute_builtin("savers_credit", ks_family5).high == 0


def test_snap_estimate_positive_for_sample(ks_family5) -> None:
    est = compute_builtin("snap", ks_family5)
    assert 0 < est.low < est.high
    # cannot exceed the max allotment for a household of 5
    assert est.high <= 1_158 * 12


def test_estimate_value_fixed_monthly(ks_family5) -> None:
    est = estimate_value({"type": "fixed", "amount": 9.25, "period": "month"}, ks_family5)
    assert est is not None
    assert est.high == pytest.approx(111)


def test_estimate_value_per_member(ks_family5) -> None:
    est = estimate_value(
        {"type": "per_member", "amount": 120, "member_filter": {"age_min": 5, "age_max": 17}},
        ks_family5,
    )
    assert est is not None
    assert est.high == 240  # the 16 and 11 year olds


def test_estimate_value_none(ks_family5) -> None:
    assert estimate_value({"type": "none"}, ks_family5) is None


def test_unknown_builtin_raises(ks_family5) -> None:
    with pytest.raises(ValueError):
        compute_builtin("nope", ks_family5)
