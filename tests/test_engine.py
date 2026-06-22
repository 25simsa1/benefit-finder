"""Every verdict path through the rules engine."""
from __future__ import annotations

from benefit_finder.engine import Verdict, evaluate, evaluate_all
from benefit_finder.models import Household, Member

from conftest import make_rule


def _household(agi: float, **kwargs) -> Household:
    members = kwargs.pop(
        "members",
        [
            Member(age=35, relationship="self", employed=True, income_type="w2"),
            Member(age=34, relationship="spouse"),
            Member(age=8, relationship="child", student="k12"),
        ],
    )
    return Household(state="KS", members=members, agi=agi, **kwargs)


# FPL for a household of 3 is 26,650. 130% is 34,645.
FPL3_130 = 34_645


def test_yes_path_definitive_under_limit() -> None:
    rule = make_rule(
        income={"type": "fpl_percent", "limit_pct": 130},
        confidence="definitive",
    )
    ev = evaluate(rule, _household(agi=20_000))
    assert ev.verdict is Verdict.YES
    assert any("%" in r for r in ev.reasons)


def test_likely_path_screen_under_limit() -> None:
    rule = make_rule(income={"type": "fpl_percent", "limit_pct": 130})
    ev = evaluate(rule, _household(agi=20_000))
    assert ev.verdict is Verdict.LIKELY


def test_borderline_path_within_margin() -> None:
    rule = make_rule(
        income={"type": "fpl_percent", "limit_pct": 130},
        borderline_margin_pct=10,
    )
    # 135% of FPL3, over the 130% limit but under 143%
    ev = evaluate(rule, _household(agi=26_650 * 1.35))
    assert ev.verdict is Verdict.BORDERLINE
    assert any("slightly over" in r for r in ev.reasons)


def test_no_path_income_over_limit() -> None:
    rule = make_rule(income={"type": "fpl_percent", "limit_pct": 130})
    ev = evaluate(rule, _household(agi=90_000))
    assert ev.verdict is Verdict.NO
    assert ev.value is None
    assert any("over the limit" in r for r in ev.reasons)


def test_no_path_condition_fails() -> None:
    rule = make_rule(
        income={"type": "none"},
        conditions=[
            {
                "type": "min_members_matching",
                "count": 1,
                "member_filter": {"age_max": 4},
                "describe": "at least one child under 5",
            }
        ],
    )
    ev = evaluate(rule, _household(agi=10_000))
    assert ev.verdict is Verdict.NO
    assert any("Condition not met" in r for r in ev.reasons)


def test_conditions_any_mode_passes_on_one() -> None:
    rule = make_rule(
        income={"type": "none"},
        conditions_mode="any",
        conditions=[
            {"type": "min_members_matching", "count": 1, "member_filter": {"age_max": 4}},
            {"type": "flag", "flag": "pregnant_member", "equals": True},
        ],
    )
    hh = _household(agi=10_000, flags={"pregnant_member": True})
    ev = evaluate(rule, hh)
    assert ev.verdict is Verdict.LIKELY

    hh_neither = _household(agi=10_000)
    assert evaluate(rule, hh_neither).verdict is Verdict.NO


def test_any_of_condition() -> None:
    rule = make_rule(
        income={"type": "none"},
        conditions=[
            {
                "type": "any_of",
                "conditions": [
                    {"type": "min_members_matching", "count": 1, "member_filter": {"age_min": 55}},
                    {"type": "min_members_matching", "count": 1, "member_filter": {"disabled": True}},
                ],
            }
        ],
    )
    assert evaluate(rule, _household(agi=10_000)).verdict is Verdict.NO
    senior = _household(
        agi=10_000,
        members=[Member(age=60, relationship="self")],
    )
    assert evaluate(rule, senior).verdict is Verdict.LIKELY


def test_categorical_flag_bypasses_income() -> None:
    rule = make_rule(
        income={"type": "fpl_percent", "limit_pct": 130},
        categorical_flags=["receives_snap"],
    )
    hh = _household(agi=90_000, flags={"receives_snap": True})
    ev = evaluate(rule, hh)
    assert ev.verdict is Verdict.LIKELY
    assert any("Categorically eligible" in r for r in ev.reasons)


def test_enrolled_skip() -> None:
    rule = make_rule(skip_if_already_enrolled="receives_snap")
    hh = _household(agi=20_000, flags={"receives_snap": True})
    ev = evaluate(rule, hh)
    assert ev.verdict is Verdict.ENROLLED


def test_min_pct_floor_fails_below_window() -> None:
    rule = make_rule(income={"type": "fpl_percent", "limit_pct": 400, "min_pct": 100})
    ev = evaluate(rule, _household(agi=15_000))  # ~56% FPL3
    assert ev.verdict is Verdict.NO
    assert any("floor" in r for r in ev.reasons)


def test_fixed_income_limit() -> None:
    rule = make_rule(income={"type": "fixed", "amount": 30_615})
    assert evaluate(rule, _household(agi=25_000)).verdict is Verdict.LIKELY
    assert evaluate(rule, _household(agi=45_000)).verdict is Verdict.NO


def test_fixed_by_size_with_per_additional() -> None:
    rule = make_rule(
        income={
            "type": "fixed_by_size",
            "amounts": {1: 20_000, 2: 27_000},
            "per_additional": 7_000,
        }
    )
    # household of 3 -> 27,000 + 7,000 = 34,000
    assert evaluate(rule, _household(agi=33_000)).verdict is Verdict.LIKELY
    assert evaluate(rule, _household(agi=40_000)).verdict is Verdict.NO


def test_fixed_by_filing_status_uses_mfj() -> None:
    rule = make_rule(
        income={
            "type": "fixed_by_filing_status",
            "amounts": {"mfj": 79_000, "hoh": 59_250, "single": 39_500},
        }
    )
    ev = evaluate(rule, _household(agi=60_000))  # mfj household
    assert ev.verdict is Verdict.LIKELY
    assert any("mfj" in r for r in ev.reasons)


def test_snap_basis_shrinks_household_and_limit(family_with_college_away) -> None:
    rule_snap = make_rule(
        income={"type": "fpl_percent", "limit_pct": 130},
        household_size_basis="snap",
    )
    rule_all = make_rule(
        income={"type": "fpl_percent", "limit_pct": 130},
        household_size_basis="all",
    )
    ev_snap = evaluate(rule_snap, family_with_college_away)
    ev_all = evaluate(rule_all, family_with_college_away)
    assert ev_snap.household_size_used == 3
    assert ev_all.household_size_used == 4
    assert ev_snap.income_limit_dollars < ev_all.income_limit_dollars


def test_verdict_cap_borderline() -> None:
    rule = make_rule(
        income={"type": "fpl_percent", "limit_pct": 400},
        verdict_cap="borderline",
    )
    ev = evaluate(rule, _household(agi=20_000))
    assert ev.verdict is Verdict.BORDERLINE


def test_verdict_cap_likely_downgrades_yes() -> None:
    rule = make_rule(
        income={"type": "fpl_percent", "limit_pct": 400},
        confidence="definitive",
        verdict_cap="likely",
    )
    ev = evaluate(rule, _household(agi=20_000))
    assert ev.verdict is Verdict.LIKELY


def test_builtin_value_positive_condition_gates_verdict() -> None:
    rule = make_rule(
        income={"type": "none"},
        conditions=[{"type": "builtin_value_positive", "name": "eitc"}],
        confidence="definitive",
        value={"type": "builtin", "name": "eitc"},
    )
    low = _household(agi=30_000)
    assert evaluate(rule, low).verdict is Verdict.YES
    rich = _household(agi=300_000)
    assert evaluate(rule, rich).verdict is Verdict.NO


def test_evaluate_all_sorts_by_value_desc() -> None:
    big = make_rule(id="big", name="Big", value={"type": "fixed", "amount": 5_000})
    small = make_rule(id="small", name="Small", value={"type": "fixed", "amount": 100})
    fails = make_rule(
        id="fails",
        name="Fails",
        income={"type": "fixed", "amount": 1},
    )
    evs = evaluate_all([small, fails, big], _household(agi=20_000))
    assert [e.rule.id for e in evs] == ["big", "small", "fails"]
