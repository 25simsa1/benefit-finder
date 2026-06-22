from __future__ import annotations

from typing import Any

import pytest

from benefit_finder.models import Household, Member, sample_household
from benefit_finder.rules_loader import Rule


def make_rule(**overrides: Any) -> Rule:
    """A minimal valid Rule for engine tests, overridable per test."""
    base: dict[str, Any] = dict(
        id="test_rule",
        name="Test Program",
        category="food",
        jurisdiction="federal",
        description="A test program.",
        source_url="https://example.gov/test",
        last_verified="2025-10-01",
        application_url="https://example.gov/apply",
        next_step="Apply online.",
        documents=["Photo ID"],
    )
    base.update(overrides)
    return Rule(**base)


@pytest.fixture
def ks_family5() -> Household:
    return sample_household()


@pytest.fixture
def single_adult() -> Household:
    return Household(
        state="KS",
        members=[Member(age=30, relationship="self", employed=True, income_type="w2")],
        agi=20_000,
    )


@pytest.fixture
def family_with_college_away() -> Household:
    return Household(
        state="KS",
        members=[
            Member(age=50, relationship="self", employed=True, income_type="w2"),
            Member(age=49, relationship="spouse"),
            Member(age=19, relationship="child", student="college"),
            Member(age=15, relationship="child", student="k12"),
        ],
        agi=40_000,
        flags={"college_student_living_away": True},
    )
