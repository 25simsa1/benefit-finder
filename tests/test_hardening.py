"""Regression tests for the review findings, bad input never tracebacks."""
from __future__ import annotations

import pytest

from benefit_finder.cli import main
from benefit_finder.models import Household, Member, ProfileError
from benefit_finder.rules_loader import RuleValidationError, load_rule_file, load_rules
from benefit_finder.values import compute_builtin


def test_unknown_profile_key_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["aig"] = data.pop("agi")  # classic typo
    with pytest.raises(ProfileError, match="unknown profile keys"):
        Household.from_dict(data)


def test_unknown_member_key_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["aeg"] = 38
    with pytest.raises(ProfileError, match="unknown keys"):
        Household.from_dict(data)


def test_flags_as_list_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["flags"] = ["veteran"]
    with pytest.raises(ProfileError, match="flags must be"):
        Household.from_dict(data)


def test_profile_root_not_object_rejected() -> None:
    with pytest.raises(ProfileError, match="JSON object"):
        Household.from_dict(["not", "a", "profile"])  # type: ignore[arg-type]


def test_member_string_age_coerced(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["age"] = "38"
    assert Household.from_dict(data).members[0].age == 38


def test_member_nonnumeric_age_rejected(ks_family5) -> None:
    data = ks_family5.to_dict()
    data["members"][0]["age"] = "thirty-eight"
    with pytest.raises(ProfileError, match="malformed profile"):
        Household.from_dict(data)


def test_malformed_yaml_rule_raises_validation_error(tmp_path) -> None:
    bad = tmp_path / "broken.yaml"
    bad.write_text("id: broken\nname: [unclosed\n", encoding="utf-8")
    with pytest.raises(RuleValidationError, match="not valid YAML"):
        load_rule_file(bad)


def test_missing_rules_dir_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="rules directory not found"):
        load_rules(state="KS", extra_dirs=[tmp_path / "nope"])


def test_eitc_childless_age_gate() -> None:
    too_young = Household(
        state="KS",
        members=[Member(age=22, relationship="self", employed=True, income_type="w2")],
        agi=12_000,
    )
    assert compute_builtin("eitc", too_young).high == 0
    old_enough = Household(
        state="KS",
        members=[Member(age=30, relationship="self", employed=True, income_type="w2")],
        agi=8_000,
    )
    assert compute_builtin("eitc", old_enough).high > 0


def test_snap_estimate_notes_alaska() -> None:
    hh = Household(
        state="AK",
        members=[Member(age=30, relationship="self", employed=True, income_type="w2")],
        agi=15_000,
    )
    assert "Alaska" in compute_builtin("snap", hh).note


def test_cli_missing_profile_is_friendly(capsys) -> None:
    code = main(["screen", "--profile", "/nonexistent/profile.json"])
    captured = capsys.readouterr()
    assert code == 2
    assert "benefit-finder init" in captured.err
    assert "Traceback" not in captured.err


def test_cli_missing_rules_dir_is_friendly(tmp_path, capsys, ks_family5) -> None:
    profile = tmp_path / "profile.json"
    ks_family5.save(profile)
    code = main(["screen", "--profile", str(profile), "--rules-dir", str(tmp_path / "nope")])
    captured = capsys.readouterr()
    assert code == 2
    assert "rules directory" in captured.err


def test_cli_unwritable_report_out_is_friendly(tmp_path, capsys, ks_family5) -> None:
    profile = tmp_path / "profile.json"
    ks_family5.save(profile)
    code = main(
        ["report", "--profile", str(profile), "--out", str(tmp_path / "missing" / "r.md")]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "File error" in captured.err


def test_cli_typoed_profile_key_is_friendly(tmp_path, capsys, ks_family5) -> None:
    data = ks_family5.to_dict()
    data["aig"] = data.pop("agi")
    import json

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(data), encoding="utf-8")
    code = main(["screen", "--profile", str(profile)])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown profile keys" in captured.err
