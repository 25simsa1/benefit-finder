"""Regression tests for the round-2 review findings."""
from __future__ import annotations

import pytest

from benefit_finder.engine import Verdict, evaluate
from benefit_finder.models import Household, Member, ProfileError
from benefit_finder.rules_loader import load_rules, validate_rule_data
from benefit_finder.values import compute_builtin


def _base_rule_data(**overrides) -> dict:
    data = {
        "id": "t",
        "name": "T",
        "category": "food",
        "jurisdiction": "federal",
        "description": "Test.",
        "income": {"type": "none"},
        "value": {"type": "none"},
        "next_step": "Apply.",
        "application_url": "https://example.gov",
        "documents": ["ID"],
        "source_url": "https://example.gov",
        "last_verified": "2025-01-01",
    }
    data.update(overrides)
    return data


# ---- rule validator gaps ----

def test_null_next_step_rejected() -> None:
    problems = validate_rule_data(_base_rule_data(next_step=None))
    assert any("next_step" in p for p in problems)


def test_non_string_name_rejected() -> None:
    problems = validate_rule_data(_base_rule_data(name=2026))
    assert any("'name'" in p for p in problems)


def test_scalar_states_rejected() -> None:
    problems = validate_rule_data(
        _base_rule_data(jurisdiction="state", states="KS")
    )
    assert any("two-letter" in p for p in problems)


def test_member_filter_typo_key_rejected() -> None:
    problems = validate_rule_data(
        _base_rule_data(
            conditions=[
                {
                    "type": "min_members_matching",
                    "count": 1,
                    "member_filter": {"relationship": "child", "max_age": 1},
                }
            ]
        )
    )
    assert any("unknown keys" in p and "max_age" in p for p in problems)


def test_null_categorical_flags_rejected() -> None:
    problems = validate_rule_data(_base_rule_data(categorical_flags=None))
    assert any("categorical_flags" in p for p in problems)


def test_non_numeric_count_and_ages_rejected() -> None:
    problems = validate_rule_data(
        _base_rule_data(
            conditions=[
                {
                    "type": "min_members_matching",
                    "count": "two",
                    "member_filter": {"age_min": "five"},
                }
            ]
        )
    )
    assert any("count must be" in p for p in problems)
    assert any("age_min must be numeric" in p for p in problems)


def test_fixed_by_size_bad_keys_rejected() -> None:
    problems = validate_rule_data(
        _base_rule_data(income={"type": "fixed_by_size", "amounts": {"1-2": 20000}})
    )
    assert any("integer household sizes" in p for p in problems)


# ---- profile strictness ----

def test_string_no_flag_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["flags"] = {"receives_snap": "no"}
    with pytest.raises(ProfileError, match="true or false"):
        Household.from_dict(data)


def test_string_false_member_bool_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["disabled"] = "false"
    with pytest.raises(ProfileError, match="true or false"):
        Household.from_dict(data)


def test_zero_one_flags_accepted(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["flags"] = {"veteran": 1, "receives_snap": 0}
    hh = Household.from_dict(data)
    assert hh.flag("veteran") is True
    assert hh.flag("receives_snap") is False


def test_infinite_agi_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["agi"] = float("inf")
    with pytest.raises(ProfileError, match="finite"):
        Household.from_dict(data)


def test_nan_agi_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["agi"] = float("nan")
    with pytest.raises(ProfileError, match="finite"):
        Household.from_dict(data)


# ---- verdict contract fixes ----

def _rich_parent(agi: float) -> Household:
    return Household(
        state="KS",
        members=[
            Member(age=45, relationship="self", employed=True, income_type="w2"),
            Member(age=10, relationship="child", student="k12"),
        ],
        agi=agi,
    )


def test_ctc_phased_out_is_no() -> None:
    rules = {r.id: r for r in load_rules(state="KS")}
    ev = evaluate(rules["ctc_actc"], _rich_parent(500_000))
    assert ev.verdict is Verdict.NO
    ev_ok = evaluate(rules["ctc_actc"], _rich_parent(45_000))
    assert ev_ok.verdict is Verdict.YES


def test_savers_credit_cliff_is_no_not_borderline() -> None:
    rules = {r.id: r for r in load_rules(state="KS")}
    over_cliff = Household(
        state="KS",
        members=[Member(age=40, relationship="self", employed=True, income_type="w2")],
        agi=40_000,  # single limit is 39,500
    )
    assert evaluate(rules["savers_credit"], over_cliff).verdict is Verdict.NO


def test_pregnant_medicaid_pathway_screens() -> None:
    rules = {r.id: r for r in load_rules(state="KS")}
    pregnant = Household(
        state="KS",
        members=[Member(age=25, relationship="self", employed=True, income_type="w2")],
        agi=20_000,  # 128% FPL for a household of 1, under the 171% limit
        flags={"pregnant_member": True},
    )
    assert evaluate(rules["ks_medicaid_pregnant"], pregnant).verdict is Verdict.LIKELY
    not_pregnant = Household(
        state="KS",
        members=[Member(age=25, relationship="self", employed=True, income_type="w2")],
        agi=20_000,
    )
    assert evaluate(rules["ks_medicaid_pregnant"], not_pregnant).verdict is Verdict.NO


def test_snap_minimum_allotment_small_household() -> None:
    hh = Household(
        state="KS",
        members=[Member(age=30, relationship="self", employed=True, income_type="w2")],
        agi=18_000,  # high enough that the formula alone would round to ~0
    )
    est = compute_builtin("snap", hh)
    assert est.low >= 23 * 12 * 0.7 - 1


def test_malformed_rule_in_extra_dir_is_error_not_crash(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: bad
name: Bad
category: food
jurisdiction: federal
description: Bad rule.
income: {type: none}
value: {type: none}
next_step:
application_url: https://example.gov
documents: [ID]
source_url: https://example.gov
last_verified: 2025-01-01
categorical_flags:
""",
        encoding="utf-8",
    )
    from benefit_finder.rules_loader import RuleValidationError

    with pytest.raises(RuleValidationError):
        load_rules(state="KS", extra_dirs=[tmp_path])
