from __future__ import annotations

import pytest

from benefit_finder.models import Household, Member, ProfileError, member_matches


def test_roundtrip_save_load(tmp_path, ks_family5) -> None:
    path = tmp_path / "profile.json"
    ks_family5.save(path)
    loaded = Household.load(path)
    assert loaded == ks_family5


def test_zip_key_alias(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["zip"] = data.pop("zip_code")
    assert Household.from_dict(data).zip_code == "67214"


def test_validation_rejects_bad_student_status(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["student"] = "kindergarten"
    with pytest.raises(ProfileError):
        Household.from_dict(data)


def test_validation_rejects_unknown_flag(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["flags"]["wins_lottery"] = True
    with pytest.raises(ProfileError):
        Household.from_dict(data)


def test_household_size_bases(family_with_college_away) -> None:
    hh = family_with_college_away
    assert hh.household_size("all") == 4
    assert hh.household_size("tax") == 4
    assert hh.household_size("fafsa") == 4
    assert hh.household_size("snap") == 3


def test_snap_size_without_away_flag(family_with_college_away) -> None:
    family_with_college_away.flags["college_student_living_away"] = False
    assert family_with_college_away.household_size("snap") == 4


def test_income_drop_percent(ks_family5, single_adult) -> None:
    assert ks_family5.income_drop_percent() == pytest.approx(27.42, abs=0.01)
    assert single_adult.income_drop_percent() is None


def test_filing_status(ks_family5, single_adult) -> None:
    assert ks_family5.filing_status == "mfj"
    assert single_adult.filing_status == "single"
    hoh = Household(
        state="KS",
        members=[Member(age=40), Member(age=10, relationship="child")],
        agi=30_000,
    )
    assert hoh.filing_status == "hoh"


def test_member_matches_lists_and_ranges() -> None:
    member = Member(age=16, relationship="child", student="k12")
    assert member_matches(member, {"age_min": 5, "age_max": 17})
    assert member_matches(member, {"student": ["k12", "college"]})
    assert not member_matches(member, {"age_max": 15})
    assert not member_matches(member, {"employed": True})
