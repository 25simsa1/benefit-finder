"""Validation of every shipped rule YAML file."""
from __future__ import annotations

from datetime import date

import pytest

from benefit_finder.rules_loader import (
    Rule,
    RuleValidationError,
    builtin_rules_dir,
    load_rule_file,
    load_rules,
)

EXPECTED_FEDERAL_IDS = {
    "snap",
    "wic",
    "nslp",
    "lifeline",
    "aca_subsidy",
    "eitc",
    "ctc_actc",
    "savers_credit",
    "aotc",
    "lifetime_learning_credit",
    "pell_grant",
    "summer_ebt",
}
EXPECTED_KS_IDS = {
    "ks_lieap",
    "ks_medicaid_chip_children",
    "ks_medicaid_pregnant",
    "ks_food_sales_tax_credit",
    "ks_homestead_refund",
}


def _all_rule_files() -> list:
    return sorted(builtin_rules_dir().rglob("*.yaml"))


def test_rules_directory_is_not_empty() -> None:
    assert _all_rule_files(), "no rule files shipped with the package"


@pytest.mark.parametrize("path", _all_rule_files(), ids=lambda p: p.stem)
def test_every_shipped_rule_is_valid(path) -> None:
    rule = load_rule_file(path)
    assert isinstance(rule, Rule)
    assert rule.source_url.startswith("http")
    assert rule.documents
    verified = date.fromisoformat(rule.last_verified)
    assert verified <= date.today()


def test_expected_federal_rules_present() -> None:
    ids = {r.id for r in load_rules(state=None)}
    missing = EXPECTED_FEDERAL_IDS - ids
    assert not missing, f"missing federal rules {sorted(missing)}"


def test_expected_kansas_rules_present() -> None:
    ids = {r.id for r in load_rules(state="KS")}
    missing = (EXPECTED_FEDERAL_IDS | EXPECTED_KS_IDS) - ids
    assert not missing, f"missing rules for KS {sorted(missing)}"


def test_state_rules_not_loaded_for_other_states() -> None:
    ids = {r.id for r in load_rules(state="MO")}
    assert not (EXPECTED_KS_IDS & ids)


def test_extra_dir_overrides_builtin(tmp_path) -> None:
    override = tmp_path / "snap.yaml"
    override.write_text(
        """
id: snap
name: SNAP Override
category: food
jurisdiction: federal
description: Overridden for testing.
income: {type: none}
value: {type: none}
next_step: n/a
application_url: https://example.gov
documents: [ID]
source_url: https://example.gov
last_verified: 2025-01-01
""",
        encoding="utf-8",
    )
    rules = load_rules(state="KS", extra_dirs=[tmp_path])
    snap = next(r for r in rules if r.id == "snap")
    assert snap.name == "SNAP Override"


def test_invalid_rule_reports_problems(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
id: bad
name: Bad
category: nonsense
jurisdiction: federal
description: Bad rule.
income: {type: wat}
value: {type: none}
next_step: n/a
application_url: https://example.gov
documents: []
source_url: notaurl
last_verified: whenever
unknown_key: true
""",
        encoding="utf-8",
    )
    with pytest.raises(RuleValidationError) as excinfo:
        load_rule_file(bad)
    message = str(excinfo.value)
    for fragment in ("unknown top-level keys",):
        assert fragment in message
