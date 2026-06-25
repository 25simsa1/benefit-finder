"""Acceptance test. A family of 5 in Kansas at $45k AGI, screened against
every shipped rule. This pins the expected verdict for each seeded program."""
from __future__ import annotations

import pytest

from benefit_finder.engine import Verdict, evaluate_all
from benefit_finder.report import generate_report
from benefit_finder.rules_loader import load_rules

EXPECTED_VERDICTS = {
    "snap": Verdict.LIKELY,                     # 119.5% FPL vs 130% gross limit
    "wic": Verdict.LIKELY,                      # child age 4, under 185%
    "nslp": Verdict.LIKELY,                     # two K-12 kids, under 185%
    "lifeline": Verdict.LIKELY,                 # under 135%
    "aca_subsidy": Verdict.LIKELY,              # inside the 100 to 400% window
    "eitc": Verdict.YES,                        # computed credit is positive
    "ctc_actc": Verdict.YES,                    # three kids under 17
    "savers_credit": Verdict.BORDERLINE,        # capped, needs contributions
    "aotc": Verdict.NO,                         # no college student
    "lifetime_learning_credit": Verdict.NO,     # no college student
    "pell_grant": Verdict.NO,                   # no college student
    "summer_ebt": Verdict.LIKELY,               # school-age kids, under 185%
    "ks_lieap": Verdict.LIKELY,                 # under 150%
    "ks_medicaid_chip_children": Verdict.LIKELY,
    "ks_medicaid_pregnant": Verdict.NO,         # nobody pregnant in the sample
    "ks_food_sales_tax_credit": Verdict.NO,     # income above the fixed limit
    "ks_homestead_refund": Verdict.NO,          # renters not eligible
}


@pytest.fixture(scope="module")
def evaluations(request):
    from benefit_finder.models import sample_household

    household = sample_household()
    rules = load_rules(state=household.state)
    return household, evaluate_all(rules, household)


def test_all_expected_programs_screened(evaluations) -> None:
    _, evals = evaluations
    ids = {e.rule.id for e in evals}
    missing = set(EXPECTED_VERDICTS) - ids
    assert not missing, f"programs missing from the screen {sorted(missing)}"


@pytest.mark.parametrize("rule_id", sorted(EXPECTED_VERDICTS))
def test_expected_verdict(evaluations, rule_id: str) -> None:
    _, evals = evaluations
    ev = next(e for e in evals if e.rule.id == rule_id)
    assert ev.verdict is EXPECTED_VERDICTS[rule_id], (
        f"{rule_id} expected {EXPECTED_VERDICTS[rule_id].value} but got "
        f"{ev.verdict.value}. Reasons {ev.reasons}"
    )


def test_eitc_value_estimate(evaluations) -> None:
    _, evals = evaluations
    eitc = next(e for e in evals if e.rule.id == "eitc")
    assert eitc.value is not None
    assert eitc.value.high == pytest.approx(4_986, abs=1)


def test_ctc_value_estimate(evaluations) -> None:
    _, evals = evaluations
    ctc = next(e for e in evals if e.rule.id == "ctc_actc")
    assert ctc.value is not None
    assert ctc.value.high == 6_600
    assert ctc.value.low == 5_100


def test_results_sorted_by_value(evaluations) -> None:
    _, evals = evaluations
    values = [e.sort_value for e in evals]
    assert values == sorted(values, reverse=True)


def test_report_generation(evaluations) -> None:
    household, evals = evaluations
    report = generate_report(evals, household)
    assert "## Summary" in report
    assert "## Special situations" in report
    assert "Income dropped 27%" in report          # 62k -> 45k
    assert "- [ ]" in report                       # documents checklists
    assert "Likely eligible" in report
    assert "Not eligible" in report
    assert "Verify current limits" in report or "verify" in report.lower()
    # every screened program appears
    for ev in evals:
        assert ev.rule.name in report
