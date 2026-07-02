"""Pydantic request/response models and mappers for the web API.

The request model mirrors the profile.json schema so a profile is
interchangeable between the CLI and the web app. Domain validation
still runs through Household.from_dict, so the two interfaces reject the
same bad input. Response models expose exactly what the dashboard and
report views need, derived from the engine's Evaluation objects.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .. import fpl as fpl_mod
from ..engine import GROUP_ORDER, Evaluation, Verdict
from ..models import (
    HOUSING_STATUSES,
    INCOME_TYPES,
    RELATIONSHIPS,
    STUDENT_STATUSES,
    Household,
)
from ..report import DISCLAIMER, special_situations, total_range

# Human-readable labels the frontend renders in selects and checkboxes.
FLAG_LABELS: dict[str, str] = {
    "pregnant_member": "Someone in the household is pregnant",
    "veteran": "A household member is a veteran",
    "recent_job_loss": "Someone recently lost a job",
    "college_student_living_away": "A college student is living away from home",
    "receives_snap": "Already receiving SNAP",
    "receives_medicaid": "Already receiving Medicaid",
}
RELATIONSHIP_LABELS = {
    "self": "Self (you)",
    "spouse": "Spouse",
    "child": "Child",
    "grandchild": "Grandchild",
    "foster_child": "Foster child",
    "parent": "Parent",
    "other": "Other",
}
STUDENT_LABELS = {"none": "Not a student", "k12": "K-12 student", "college": "College student"}
INCOME_TYPE_LABELS = {"none": "No earned income", "w2": "W-2 employee", "1099": "1099 / self-employed"}
HOUSING_LABELS = {"rent": "Rent", "own": "Own"}

_BASIS_LABEL = {"snap": "SNAP", "tax": "tax", "fafsa": "FAFSA", "all": "standard"}


# ------------------------------------------------------------ requests ----

class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: int
    relationship: str = "self"
    student: str = "none"
    disabled: bool = False
    employed: bool = False
    income_type: str = "none"


class ProfileIn(BaseModel):
    """Same shape as profile.json. `zip` is accepted as an alias for
    `zip_code` so files written by either interface load here."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    state: str
    county: str = ""
    zip_code: str = Field(default="", alias="zip")
    members: list[MemberIn] = Field(default_factory=list)
    agi: float = 0.0
    prior_year_agi: float | None = None
    housing_status: str = "rent"
    monthly_housing_cost: float | None = None
    flags: dict[str, bool] = Field(default_factory=dict)

    def to_household(self) -> Household:
        """Convert to a validated Household. Raises ProfileError (a
        ValueError) on any domain problem, which the API turns into 422."""
        data = self.model_dump(by_alias=False)
        return Household.from_dict(data)


# ----------------------------------------------------------- responses ----

class ValueOut(BaseModel):
    low: float
    high: float
    note: str
    formatted: str


class EvaluationOut(BaseModel):
    id: str
    program: str
    category: str
    jurisdiction: str
    states: list[str]
    verdict: str
    group: str
    reasons: list[str]
    description: str
    notes: str
    estimated_value: ValueOut | None
    income_percent_of_fpl: float | None
    income_limit_dollars: float | None
    household_size_used: int | None
    household_size_basis: str
    size_basis_explanation: str | None
    next_step: str
    application_url: str
    documents: list[str]
    source_url: str
    last_verified: str


class SpecialSituationOut(BaseModel):
    title: str
    guidance: str


class ScreenResponse(BaseModel):
    state: str
    household_size: int
    agi: float
    income_percent_of_fpl: float
    fpl_year: int
    fpl_source_url: str
    fpl_warning: str | None
    disclaimer: str
    total_low: float
    total_high: float
    group_order: list[str]
    evaluations: list[EvaluationOut]
    special_situations: list[SpecialSituationOut]


class MetaResponse(BaseModel):
    fpl_year: int
    fpl_source_url: str
    fpl_warning: str | None
    disclaimer: str
    relationships: list[dict[str, str]]
    student_statuses: list[dict[str, str]]
    income_types: list[dict[str, str]]
    housing_statuses: list[dict[str, str]]
    flags: list[dict[str, str]]


# ------------------------------------------------------------- mappers ----

def _size_basis_explanation(ev: Evaluation, household: Household) -> str | None:
    """Surface the household-size nuance in the expanded card when a
    program counts the household differently than the raw member total."""
    basis = ev.rule.household_size_basis
    if basis == "all" or ev.household_size_used is None:
        return None
    all_size = household.household_size("all")
    used = ev.household_size_used
    label = _BASIS_LABEL.get(basis, basis)
    if used != all_size:
        return (
            f"This program applies {label} household-size rules. A college "
            f"student living away is treated as a separate SNAP household, so "
            f"the size used here is {used} rather than the {all_size}-person "
            f"total, which shifts the income limit."
        )
    return (
        f"This program sizes the household under {label} rules. Here that is "
        f"{used}, the same as the {all_size}-person total, so it does not "
        f"change the result."
    )


def to_evaluation_out(ev: Evaluation, household: Household) -> EvaluationOut:
    value = None
    if ev.value is not None and ev.verdict is not Verdict.NO:
        value = ValueOut(
            low=ev.value.low,
            high=ev.value.high,
            note=ev.value.note,
            formatted=ev.value.format(),
        )
    return EvaluationOut(
        id=ev.rule.id,
        program=ev.rule.name,
        category=ev.rule.category,
        jurisdiction=ev.rule.jurisdiction,
        states=ev.rule.states,
        verdict=ev.verdict.value,
        group=ev.group,
        reasons=ev.reasons,
        description=ev.rule.description.strip(),
        notes=ev.rule.notes.strip(),
        estimated_value=value,
        income_percent_of_fpl=ev.income_percent_of_fpl,
        income_limit_dollars=ev.income_limit_dollars,
        household_size_used=ev.household_size_used,
        household_size_basis=ev.rule.household_size_basis,
        size_basis_explanation=_size_basis_explanation(ev, household),
        next_step=ev.rule.next_step.strip(),
        application_url=ev.rule.application_url,
        documents=ev.rule.documents,
        source_url=ev.rule.source_url,
        last_verified=ev.rule.last_verified,
    )


def build_screen_response(
    evaluations: list[Evaluation], household: Household
) -> ScreenResponse:
    low, high = total_range(evaluations)
    size = household.household_size("all")
    return ScreenResponse(
        state=household.state,
        household_size=size,
        agi=household.agi,
        income_percent_of_fpl=fpl_mod.income_as_percent_of_fpl(
            household.agi, size, household.state
        ),
        fpl_year=fpl_mod.FPL_YEAR,
        fpl_source_url=fpl_mod.FPL_SOURCE_URL,
        fpl_warning=fpl_mod.fpl_year_warning(),
        disclaimer=DISCLAIMER,
        total_low=low,
        total_high=high,
        group_order=list(GROUP_ORDER),
        evaluations=[to_evaluation_out(ev, household) for ev in evaluations],
        special_situations=[
            SpecialSituationOut(title=title, guidance=body)
            for title, body in special_situations(household)
        ],
    )


def _labeled(values: tuple[str, ...], labels: dict[str, str]) -> list[dict[str, str]]:
    return [{"value": v, "label": labels.get(v, v)} for v in values]


def build_meta() -> MetaResponse:
    return MetaResponse(
        fpl_year=fpl_mod.FPL_YEAR,
        fpl_source_url=fpl_mod.FPL_SOURCE_URL,
        fpl_warning=fpl_mod.fpl_year_warning(),
        disclaimer=DISCLAIMER,
        relationships=_labeled(RELATIONSHIPS, RELATIONSHIP_LABELS),
        student_statuses=_labeled(STUDENT_STATUSES, STUDENT_LABELS),
        income_types=_labeled(INCOME_TYPES, INCOME_TYPE_LABELS),
        housing_statuses=_labeled(HOUSING_STATUSES, HOUSING_LABELS),
        flags=[{"name": name, "label": label} for name, label in FLAG_LABELS.items()],
    )
