"""Markdown report generation."""
from __future__ import annotations

from datetime import date

from . import fpl as fpl_mod
from .engine import (
    GROUP_BORDERLINE,
    GROUP_ENROLLED,
    GROUP_LIKELY,
    GROUP_NO,
    GROUP_ORDER,
    Evaluation,
    Verdict,
)
from .models import Household

DISCLAIMER = (
    "This is a screening estimate, not an eligibility determination. Income "
    "limits and benefit amounts change every year and vary with details this "
    "tool does not collect. Verify current limits with each program before "
    "relying on any number here."
)


def total_range(evaluations: list[Evaluation]) -> tuple[float, float]:
    """Combined annual value of yes and likely verdicts."""
    low = high = 0.0
    for ev in evaluations:
        if ev.verdict in (Verdict.YES, Verdict.LIKELY) and ev.value:
            low += ev.value.low
            high += ev.value.high
    return low, high


def _value_cell(ev: Evaluation) -> str:
    if ev.verdict is Verdict.NO or ev.value is None:
        return "-"
    return ev.value.format()


def special_situations(household: Household) -> list[tuple[str, str]]:
    """(title, guidance) pairs triggered by profile flags and income changes."""
    items: list[tuple[str, str]] = []
    drop = household.income_drop_percent()
    if drop is not None and drop >= 25:
        items.append((
            f"Income dropped {drop:.0f}% year over year",
            "A drop this large opens doors that normal screening misses. "
            "If anyone is in or headed to college, ask the school's financial aid "
            "office for a professional judgment review of the aid package based on "
            "current income rather than the FAFSA's prior-prior year. Update your "
            "healthcare.gov application with the new income right away since "
            "subsidies are based on expected current-year income, and a mid-year "
            "income change can qualify you to enroll or adjust outside open "
            "enrollment. Recertify early for any benefit you already receive.",
        ))
    if household.flag("recent_job_loss"):
        items.append((
            "Recent job loss",
            "Apply for unemployment insurance immediately since benefits are not "
            "retroactive to the layoff date in most states. Losing employer health "
            "coverage triggers a 60-day ACA special enrollment period, which is "
            "usually far cheaper than COBRA. When applying for SNAP, ask about "
            "expedited processing, which can issue benefits within about 7 days "
            "for households with very low cash on hand.",
        ))
    if household.flag("pregnant_member"):
        items.append((
            "Pregnancy in the household",
            "WIC serves pregnant and postpartum members directly, and pregnancy "
            "raises the Medicaid income limit substantially in most states. Ask "
            "about presumptive eligibility, which can start Medicaid coverage "
            "while the full application is processed. The unborn child can also "
            "count toward household size for some programs.",
        ))
    if household.flag("veteran"):
        items.append((
            "Veteran in the household",
            "Check VA health care enrollment, VA disability compensation, and the "
            "Veterans Pension for wartime veterans with low income. Many states "
            "add property tax relief for disabled veterans. A County Veterans "
            "Service Officer will help with claims for free.",
        ))
    if household.flag("receives_snap"):
        items.append((
            "Already receiving SNAP",
            "SNAP unlocks categorical eligibility elsewhere. Lifeline phone and "
            "internet discounts need no separate income proof, school meal "
            "applications are approved by direct certification, and summer EBT "
            "benefits for school-age children are usually issued automatically.",
        ))
    if household.flag("college_student_living_away"):
        items.append((
            "College student living away from home",
            "The student may count as their own SNAP household at school and can "
            "qualify through exemptions such as work-study, an EFC or SAI of 0, "
            "or having a young child. File the FAFSA every year even if aid "
            "seemed out of reach before, especially after an income drop.",
        ))
    return items


def _program_section(ev: Evaluation) -> list[str]:
    rule = ev.rule
    lines = [f"### {rule.name}", ""]
    juris = rule.jurisdiction
    if rule.states:
        juris += f" ({', '.join(rule.states)})"
    lines.append(
        f"**Category** {rule.category} | **Jurisdiction** {juris} | **Verdict** {ev.verdict.value}"
    )
    lines.append("")
    lines.append(rule.description.strip())
    lines.append("")
    lines.append("**Why this verdict**")
    lines.append("")
    for reason in ev.reasons:
        lines.append(f"- {reason}")
    lines.append("")
    if ev.value is not None and ev.verdict is not Verdict.NO:
        note = f" {ev.value.note}" if ev.value.note else ""
        lines.append(f"**Estimated annual value** {ev.value.format()}.{note}")
        lines.append("")
    if ev.verdict is not Verdict.NO:
        apply_line = f"**How to apply** {rule.next_step.strip()}"
        if rule.application_url:
            apply_line += f" Apply at <{rule.application_url}>."
        lines.append(apply_line)
        lines.append("")
        if rule.documents:
            lines.append("**Documents to gather**")
            lines.append("")
            for doc in rule.documents:
                lines.append(f"- [ ] {doc}")
            lines.append("")
    source = f"_Source_ <{rule.source_url}> (last verified {rule.last_verified})."
    lines.append(source)
    if rule.notes:
        lines.append("")
        lines.append(f"_Note_ {rule.notes.strip()}")
    lines.append("")
    return lines


def generate_report(
    evaluations: list[Evaluation],
    household: Household,
    today: date | None = None,
) -> str:
    today = today or date.today()
    size = household.household_size("all")
    lines: list[str] = []
    lines.append("# Benefit Finder Report")
    lines.append("")
    lines.append(
        f"_Generated {today.isoformat()} for a household of {size} in "
        f"{household.state} with ${household.agi:,.0f} AGI._"
    )
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    warning = fpl_mod.fpl_year_warning(today)
    if warning:
        lines.append(">")
        lines.append(f"> {warning}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Program | Verdict | Est. annual value | Next step |")
    lines.append("|---|---|---|---|")
    for ev in evaluations:
        step = ev.rule.next_step.strip() if ev.verdict is not Verdict.NO else "Not applicable"
        lines.append(
            f"| {ev.rule.name} | {ev.verdict.value} | {_value_cell(ev)} | {step} |"
        )
    lines.append("")
    low, high = total_range(evaluations)
    if high > 0:
        lines.append(
            f"Programs in the likely group add up to roughly **${low:,.0f} to "
            f"${high:,.0f} per year** if each one comes through."
        )
        lines.append("")

    for group in GROUP_ORDER:
        group_evals = [ev for ev in evaluations if ev.group == group]
        if not group_evals:
            continue
        lines.append(f"## {group}")
        lines.append("")
        for ev in group_evals:
            lines.extend(_program_section(ev))

    situations = special_situations(household)
    if situations:
        lines.append("## Special situations")
        lines.append("")
        for title, body in situations:
            lines.append(f"### {title}")
            lines.append("")
            lines.append(body)
            lines.append("")

    lines.append("## Fine print")
    lines.append("")
    lines.append(
        f"- Income limits were computed against the {fpl_mod.FPL_YEAR} Federal "
        f"Poverty Level guidelines (<{fpl_mod.FPL_SOURCE_URL}>, verified "
        f"{fpl_mod.FPL_LAST_VERIFIED})."
    )
    lines.append(
        "- Every rule in this report carries a source URL and a last-verified "
        "date shown in its section. Thresholds change annually, so treat any "
        "rule older than a year as suspect."
    )
    lines.append(
        "- Verdicts here are screening results. Yes means the math clearly "
        "works, likely means the household passes this screener, borderline "
        "means close enough that applying is worthwhile."
    )
    lines.append("")
    return "\n".join(lines)
