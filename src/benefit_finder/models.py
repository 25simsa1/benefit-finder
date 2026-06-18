"""Household profile schema, (de)serialization, and household-size math."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STUDENT_STATUSES = ("k12", "college", "none")
INCOME_TYPES = ("w2", "1099", "none")
HOUSING_STATUSES = ("rent", "own")
RELATIONSHIPS = ("self", "spouse", "child", "grandchild", "foster_child", "parent", "other")
CHILD_RELATIONSHIPS = ("child", "grandchild", "foster_child")

KNOWN_FLAGS = (
    "pregnant_member",
    "veteran",
    "recent_job_loss",
    "college_student_living_away",
    "receives_snap",
    "receives_medicaid",
)

# Which members count toward "household size" differs by program family.
# See Household.household_size for the semantics of each basis.
SIZE_BASES = ("all", "snap", "tax", "fafsa")


class ProfileError(ValueError):
    """Raised when a profile fails validation."""


def _as_bool(value: Any, where: str) -> bool:
    """Strict bool parsing. Coercing bool('no') to True would silently
    invert a hand-edited profile answer, so anything but a real boolean
    (or a clean 0/1) is an error."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    raise ProfileError(f"{where} must be true or false, got {value!r}")


@dataclass
class Member:
    age: int
    relationship: str = "self"
    student: str = "none"
    disabled: bool = False
    employed: bool = False
    income_type: str = "none"

    def validate(self) -> None:
        if not 0 <= self.age <= 130:
            raise ProfileError(f"member age {self.age} is out of range")
        if self.relationship not in RELATIONSHIPS:
            raise ProfileError(
                f"unknown relationship '{self.relationship}' (expected one of {', '.join(RELATIONSHIPS)})"
            )
        if self.student not in STUDENT_STATUSES:
            raise ProfileError(
                f"unknown student status '{self.student}' (expected one of {', '.join(STUDENT_STATUSES)})"
            )
        if self.income_type not in INCOME_TYPES:
            raise ProfileError(
                f"unknown income_type '{self.income_type}' (expected one of {', '.join(INCOME_TYPES)})"
            )


def member_matches(member: Member, member_filter: dict[str, Any]) -> bool:
    """True when a member satisfies every key in the filter.

    Scalar values must match exactly; a list means membership in the list.
    Supported keys are age_min, age_max, relationship, student, income_type,
    disabled, and employed.
    """
    if "age_min" in member_filter and member.age < int(member_filter["age_min"]):
        return False
    if "age_max" in member_filter and member.age > int(member_filter["age_max"]):
        return False
    for key in ("relationship", "student", "income_type"):
        if key in member_filter:
            allowed = member_filter[key]
            if not isinstance(allowed, list):
                allowed = [allowed]
            if getattr(member, key) not in allowed:
                return False
    for key in ("disabled", "employed"):
        if key in member_filter and getattr(member, key) != bool(member_filter[key]):
            return False
    return True


@dataclass
class Household:
    state: str
    county: str = ""
    zip_code: str = ""
    members: list[Member] = field(default_factory=list)
    agi: float = 0.0
    prior_year_agi: float | None = None
    housing_status: str = "rent"
    monthly_housing_cost: float | None = None
    flags: dict[str, bool] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.state or len(self.state.strip()) != 2:
            raise ProfileError("state must be a two-letter code such as KS")
        if not self.members:
            raise ProfileError("household needs at least one member")
        if self.housing_status not in HOUSING_STATUSES:
            raise ProfileError(
                f"housing_status must be one of {', '.join(HOUSING_STATUSES)}"
            )
        if not math.isfinite(self.agi):
            raise ProfileError("agi must be a finite number")
        if self.agi < 0:
            raise ProfileError("agi cannot be negative")
        if self.prior_year_agi is not None and not math.isfinite(self.prior_year_agi):
            raise ProfileError("prior_year_agi must be a finite number")
        if self.monthly_housing_cost is not None and not math.isfinite(self.monthly_housing_cost):
            raise ProfileError("monthly_housing_cost must be a finite number")
        for member in self.members:
            member.validate()
        for flag in self.flags:
            if flag not in KNOWN_FLAGS:
                raise ProfileError(
                    f"unknown flag '{flag}' (known flags are {', '.join(KNOWN_FLAGS)})"
                )

    def flag(self, name: str) -> bool:
        return bool(self.flags.get(name, False))

    def count_members(self, member_filter: dict[str, Any]) -> int:
        return sum(1 for m in self.members if member_matches(m, member_filter))

    def household_size(self, basis: str = "all") -> int:
        """Household size under a program family's counting rules.

        College students living away from home are the main divergence.
        SNAP treats a student who lives away and buys and prepares food
        separately as their own SNAP household, so the "snap" basis
        excludes college students when the college_student_living_away
        flag is set. Tax dependency and FAFSA counting usually keep a
        supported student in the household, so "tax" and "fafsa" (and
        "all") count everyone. This is a screening simplification and
        real cases have edge conditions.
        """
        if basis not in SIZE_BASES:
            raise ProfileError(f"unknown household size basis '{basis}'")
        size = len(self.members)
        if basis == "snap" and self.flag("college_student_living_away"):
            away = sum(1 for m in self.members if m.student == "college")
            size = max(1, size - away)
        return size

    @property
    def filing_status(self) -> str:
        """Rough federal filing status inferred from member relationships."""
        if any(m.relationship == "spouse" for m in self.members):
            return "mfj"
        if any(m.relationship in CHILD_RELATIONSHIPS for m in self.members):
            return "hoh"
        return "single"

    def income_drop_percent(self) -> float | None:
        """Percent drop from prior-year AGI to current AGI, or None."""
        if self.prior_year_agi is None or self.prior_year_agi <= 0:
            return None
        return (self.prior_year_agi - self.agi) / self.prior_year_agi * 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Household":
        if not isinstance(data, dict):
            raise ProfileError("profile must be a JSON object")
        known_keys = {
            "state", "county", "zip", "zip_code", "members", "agi",
            "prior_year_agi", "housing_status", "monthly_housing_cost", "flags",
        }
        unknown = sorted(set(data) - known_keys)
        if unknown:
            raise ProfileError(
                f"unknown profile keys {unknown} (known keys are "
                f"{sorted(known_keys - {'zip'})})"
            )
        members_raw = data.get("members", [])
        if not isinstance(members_raw, list):
            raise ProfileError("members must be a list")
        flags_raw = data.get("flags") or {}
        if not isinstance(flags_raw, dict):
            raise ProfileError("flags must be an object mapping flag names to true/false")
        member_keys = {"age", "relationship", "student", "disabled", "employed", "income_type"}
        try:
            members = []
            for i, m in enumerate(members_raw):
                if not isinstance(m, dict):
                    raise ProfileError(f"members[{i}] must be an object")
                unknown_member = sorted(set(m) - member_keys)
                if unknown_member:
                    raise ProfileError(
                        f"members[{i}] has unknown keys {unknown_member} "
                        f"(known keys are {sorted(member_keys)})"
                    )
                members.append(
                    Member(
                        age=int(m.get("age", -1)),
                        relationship=str(m.get("relationship", "self")),
                        student=str(m.get("student", "none")),
                        disabled=_as_bool(m.get("disabled", False), f"members[{i}].disabled"),
                        employed=_as_bool(m.get("employed", False), f"members[{i}].employed"),
                        income_type=str(m.get("income_type", "none")),
                    )
                )
            prior = data.get("prior_year_agi")
            monthly = data.get("monthly_housing_cost")
            household = cls(
                state=str(data.get("state", "")).upper(),
                county=str(data.get("county", "")),
                zip_code=str(data.get("zip_code", data.get("zip", ""))),
                members=members,
                agi=float(data.get("agi", 0)),
                prior_year_agi=float(prior) if prior is not None else None,
                housing_status=str(data.get("housing_status", "rent")),
                monthly_housing_cost=float(monthly) if monthly is not None else None,
                flags={str(k): _as_bool(v, f"flags.{k}") for k, v in flags_raw.items()},
            )
        except ProfileError:
            raise
        except (TypeError, ValueError, AttributeError) as exc:
            raise ProfileError(f"malformed profile ({exc})") from exc
        household.validate()
        return household

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Household":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path} is not valid JSON ({exc})") from exc
        return cls.from_dict(raw)


def sample_household() -> Household:
    """Demo profile, a family of five in Kansas at about $45k AGI whose
    income dropped from $62k the prior year."""
    return Household(
        state="KS",
        county="Sedgwick",
        zip_code="67214",
        members=[
            Member(age=38, relationship="self", employed=True, income_type="w2"),
            Member(age=36, relationship="spouse", employed=True, income_type="w2"),
            Member(age=16, relationship="child", student="k12"),
            Member(age=11, relationship="child", student="k12"),
            Member(age=4, relationship="child"),
        ],
        agi=45_000,
        prior_year_agi=62_000,
        housing_status="rent",
        monthly_housing_cost=1_150,
        flags={},
    )
