"""Eligibility rules engine.

Evaluates each Rule against a Household and produces an Evaluation with
a verdict (yes, likely, borderline, no, or already enrolled), reason
strings that show the income math, and an estimated annual value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from . import fpl as fpl_mod
from .models import Household
from .rules_loader import Rule
from .values import ValueEstimate, compute_builtin, estimate_value


class Verdict(Enum):
    YES = "yes"
    LIKELY = "likely"
    BORDERLINE = "borderline"
    NO = "no"
    ENROLLED = "enrolled"


GROUP_LIKELY = "Likely eligible"
GROUP_BORDERLINE = "Borderline (worth applying)"
GROUP_NO = "Not eligible"
GROUP_ENROLLED = "Already enrolled"

_GROUPS = {
    Verdict.YES: GROUP_LIKELY,
    Verdict.LIKELY: GROUP_LIKELY,
    Verdict.BORDERLINE: GROUP_BORDERLINE,
    Verdict.NO: GROUP_NO,
    Verdict.ENROLLED: GROUP_ENROLLED,
}

GROUP_ORDER = (GROUP_LIKELY, GROUP_BORDERLINE, GROUP_NO, GROUP_ENROLLED)


def group_for(verdict: Verdict) -> str:
    return _GROUPS[verdict]


@dataclass
class Evaluation:
    rule: Rule
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    value: ValueEstimate | None = None
    income_percent_of_fpl: float | None = None
    income_limit_dollars: float | None = None
    household_size_used: int | None = None

    @property
    def group(self) -> str:
        return group_for(self.verdict)

    @property
    def sort_value(self) -> float:
        return self.value.high if self.value else 0.0


@dataclass
class _IncomeCheck:
    status: str  # pass | borderline | fail | not_tested
    reason: str
    percent_of_fpl: float | None = None
    limit_dollars: float | None = None
    size_used: int | None = None


def _describe_filter(member_filter: dict[str, Any]) -> str:
    if not member_filter:
        return "any member"
    parts = []
    if "age_min" in member_filter and "age_max" in member_filter:
        parts.append(f"age {member_filter['age_min']} to {member_filter['age_max']}")
    elif "age_min" in member_filter:
        parts.append(f"age {member_filter['age_min']} or older")
    elif "age_max" in member_filter:
        parts.append(f"age {member_filter['age_max']} or younger")
    for key in ("relationship", "student", "income_type"):
        if key in member_filter:
            val = member_filter[key]
            val = "/".join(val) if isinstance(val, list) else val
            parts.append(f"{key} {val}")
    for key in ("disabled", "employed"):
        if key in member_filter:
            parts.append(key if member_filter[key] else f"not {key}")
    return "member with " + ", ".join(parts)


def _eval_condition(cond: dict[str, Any], household: Household) -> tuple[bool, str]:
    ctype = cond["type"]
    describe = cond.get("describe")
    if ctype == "min_members_matching":
        need = int(cond.get("count", 1))
        member_filter = cond.get("member_filter", {})
        have = household.count_members(member_filter)
        text = describe or f"needs {need} {_describe_filter(member_filter)}"
        return have >= need, f"{text} (found {have})"
    if ctype == "flag":
        want = bool(cond.get("equals", True))
        actual = household.flag(cond["flag"])
        text = describe or f"profile flag '{cond['flag']}' must be {'set' if want else 'unset'}"
        return actual == want, text
    if ctype == "housing_status":
        want = cond["equals"]
        text = describe or f"household must {want} their home"
        return household.housing_status == want, text
    if ctype == "income_drop_min_pct":
        need = float(cond["pct"])
        drop = household.income_drop_percent()
        text = describe or f"income must have dropped at least {need:.0f}% vs the prior year"
        if drop is None:
            return False, text + " (no prior-year AGI on file)"
        return drop >= need, f"{text} (dropped {drop:.0f}%)"
    if ctype == "builtin_value_positive":
        est = compute_builtin(cond["name"], household)
        text = describe or f"estimated credit must be above $0 at this income"
        return est.high > 0, f"{text} (estimated {est.format()})"
    if ctype == "any_of":
        results = [_eval_condition(sub, household) for sub in cond["conditions"]]
        passed = [t for ok, t in results if ok]
        if passed:
            return True, passed[0]
        return False, "needs any of the following. " + "; ".join(t for _, t in results)
    raise ValueError(f"unknown condition type '{ctype}'")  # unreachable after validation


def _check_income(rule: Rule, household: Household) -> _IncomeCheck:
    income = rule.income
    itype = income.get("type", "none")
    if itype == "none":
        return _IncomeCheck("not_tested", "This program has no income test in this screener.")

    for flag_name in rule.categorical_flags:
        if household.flag(flag_name):
            program = flag_name.replace("receives_", "").upper()
            return _IncomeCheck(
                "pass",
                f"Categorically eligible because the household already receives {program}, "
                f"so the income test is bypassed.",
            )

    size = household.household_size(rule.household_size_basis)
    margin = rule.borderline_margin_pct

    if itype == "fpl_percent":
        limit_pct = float(income["limit_pct"])
        limit_dollars = fpl_mod.fpl_limit(size, limit_pct, household.state)
        pct = fpl_mod.income_as_percent_of_fpl(household.agi, size, household.state)
        base = (
            f"Household income ${household.agi:,.0f} is {pct:.0f}% of the {fpl_mod.FPL_YEAR} "
            f"FPL for a household of {size} ({rule.household_size_basis} counting). "
            f"The limit is {limit_pct:.0f}% of FPL (${limit_dollars:,.0f})."
        )
        min_pct = income.get("min_pct")
        if min_pct is not None and pct < float(min_pct):
            return _IncomeCheck(
                "fail",
                base + f" Income is below the {float(min_pct):.0f}% FPL floor for this program.",
                pct, limit_dollars, size,
            )
        if pct <= limit_pct:
            return _IncomeCheck("pass", base, pct, limit_dollars, size)
        if pct <= limit_pct * (1 + margin / 100):
            return _IncomeCheck(
                "borderline",
                base + " Income is slightly over the limit. Deductions and program "
                "specifics could change the outcome, so applying may still be worthwhile.",
                pct, limit_dollars, size,
            )
        return _IncomeCheck("fail", base + " Income is over the limit.", pct, limit_dollars, size)

    if itype in ("fixed", "fixed_by_size", "fixed_by_filing_status"):
        if itype == "fixed":
            limit = float(income["amount"])
            label = f"${limit:,.0f}"
        elif itype == "fixed_by_size":
            amounts = {int(k): float(v) for k, v in income["amounts"].items()}
            largest = max(amounts)
            if size <= largest:
                limit = amounts.get(size, amounts[min(k for k in amounts if k >= size)])
            else:
                limit = amounts[largest] + float(income.get("per_additional", 0)) * (size - largest)
            label = f"${limit:,.0f} for a household of {size}"
        else:
            amounts = income["amounts"]
            status = household.filing_status
            limit = float(amounts.get(status, amounts.get("single", 0)))
            label = f"${limit:,.0f} for filing status {status}"
        base = f"Household income ${household.agi:,.0f} vs a limit of {label}."
        if household.agi <= limit:
            return _IncomeCheck("pass", base, None, limit, size)
        if household.agi <= limit * (1 + margin / 100):
            return _IncomeCheck(
                "borderline",
                base + " Income is slightly over the limit, so applying may still be worthwhile.",
                None, limit, size,
            )
        return _IncomeCheck("fail", base + " Income is over the limit.", None, limit, size)

    raise ValueError(f"unknown income type '{itype}'")  # unreachable after validation


def evaluate(rule: Rule, household: Household) -> Evaluation:
    if rule.skip_if_already_enrolled and household.flag(rule.skip_if_already_enrolled):
        return Evaluation(
            rule,
            Verdict.ENROLLED,
            ["The profile says the household already receives this benefit. "
             "It is listed for cross-reference, not as new money."],
            estimate_value(rule.value, household),
        )

    reasons: list[str] = []
    condition_results = [(_eval_condition(c, household)) for c in rule.conditions]

    if rule.conditions_mode == "any" and rule.conditions:
        if not any(ok for ok, _ in condition_results):
            reasons.append("Meets none of the qualifying conditions.")
            reasons.extend(f"Not met ({text})" for _, text in condition_results)
            return Evaluation(rule, Verdict.NO, reasons)
        first_pass = next(text for ok, text in condition_results if ok)
        reasons.append(f"Qualifying condition met ({first_pass})")
    else:
        failed = [text for ok, text in condition_results if not ok]
        for ok, text in condition_results:
            reasons.append(f"Condition met ({text})" if ok else f"Condition not met ({text})")
        if failed:
            return Evaluation(rule, Verdict.NO, reasons)

    income_check = _check_income(rule, household)
    reasons.append(income_check.reason)

    if income_check.status == "fail":
        verdict = Verdict.NO
    elif income_check.status == "borderline":
        verdict = Verdict.BORDERLINE
    else:
        verdict = Verdict.YES if rule.confidence == "definitive" else Verdict.LIKELY

    if rule.verdict_cap == "borderline" and verdict in (Verdict.YES, Verdict.LIKELY):
        verdict = Verdict.BORDERLINE
    elif rule.verdict_cap == "likely" and verdict is Verdict.YES:
        verdict = Verdict.LIKELY

    value = estimate_value(rule.value, household) if verdict is not Verdict.NO else None
    return Evaluation(
        rule,
        verdict,
        reasons,
        value,
        income_percent_of_fpl=income_check.percent_of_fpl,
        income_limit_dollars=income_check.limit_dollars,
        household_size_used=income_check.size_used,
    )


def evaluate_all(rules: list[Rule], household: Household) -> list[Evaluation]:
    """Evaluate every rule, sorted by estimated annual value, highest first.

    Evaluations without a value (not-eligible programs) sort last,
    alphabetically by program name.
    """
    evaluations = [evaluate(rule, household) for rule in rules]
    evaluations.sort(key=lambda e: (-e.sort_value, e.rule.name.lower()))
    return evaluations
