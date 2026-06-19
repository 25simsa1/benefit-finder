"""Load and validate program rule YAML files.

Rules ship inside the package under benefit_finder/rules/. Extra rule
directories can be layered on top and override built-ins by rule id.
That layering is the seam a future `benefit-finder refresh` command
would write into after pulling updated limits from official sources.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any, Sequence

import yaml

from .models import KNOWN_FLAGS, SIZE_BASES

VALID_CATEGORIES = (
    "food",
    "health",
    "utilities",
    "communications",
    "tax_credit",
    "education",
    "housing",
    "cash",
)
VALID_JURISDICTIONS = ("federal", "state", "county")
VALID_INCOME_TYPES = ("none", "fpl_percent", "fixed", "fixed_by_size", "fixed_by_filing_status")
VALID_VALUE_TYPES = ("none", "fixed", "range", "per_member", "builtin")
VALID_CONDITION_TYPES = (
    "min_members_matching",
    "flag",
    "housing_status",
    "income_drop_min_pct",
    "builtin_value_positive",
    "any_of",
)
VALID_CONFIDENCE = ("screen", "definitive")
VALID_VERDICT_CAPS = ("likely", "borderline")
BUILTIN_VALUE_NAMES = ("eitc", "ctc_actc", "savers_credit", "snap")
VALID_FILING_STATUSES = ("single", "mfj", "hoh")

REQUIRED_KEYS = (
    "id",
    "name",
    "category",
    "jurisdiction",
    "description",
    "income",
    "value",
    "next_step",
    "application_url",
    "documents",
    "source_url",
    "last_verified",
)


class RuleValidationError(ValueError):
    def __init__(self, path: str | Path, problems: list[str]) -> None:
        self.path = str(path)
        self.problems = problems
        joined = "; ".join(problems)
        super().__init__(f"invalid rule file {path}. {joined}")


@dataclass
class Rule:
    id: str
    name: str
    category: str
    jurisdiction: str
    description: str
    source_url: str
    last_verified: str
    application_url: str = ""
    next_step: str = ""
    documents: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    household_size_basis: str = "all"
    income: dict[str, Any] = field(default_factory=lambda: {"type": "none"})
    conditions: list[dict[str, Any]] = field(default_factory=list)
    conditions_mode: str = "all"
    categorical_flags: list[str] = field(default_factory=list)
    borderline_margin_pct: float = 10.0
    confidence: str = "screen"
    verdict_cap: str | None = None
    skip_if_already_enrolled: str | None = None
    value: dict[str, Any] = field(default_factory=lambda: {"type": "none"})
    notes: str = ""
    source_file: str = ""


_RULE_FIELDS = {f.name for f in dataclasses.fields(Rule)}


_MEMBER_FILTER_KEYS = ("age_min", "age_max", "relationship", "student", "income_type", "disabled", "employed")


def _validate_member_filter(member_filter: Any, problems: list[str], prefix: str) -> None:
    if not isinstance(member_filter, dict):
        problems.append(f"{prefix} member_filter must be a mapping")
        return
    unknown = sorted(set(member_filter) - set(_MEMBER_FILTER_KEYS))
    if unknown:
        problems.append(
            f"{prefix} member_filter has unknown keys {unknown} "
            f"(known keys are {list(_MEMBER_FILTER_KEYS)})"
        )
    for key in ("age_min", "age_max"):
        if key in member_filter:
            val = member_filter[key]
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                problems.append(f"{prefix} member_filter {key} must be numeric")
    for key in ("disabled", "employed"):
        if key in member_filter and not isinstance(member_filter[key], bool):
            problems.append(f"{prefix} member_filter {key} must be true or false")
    for key in ("relationship", "student", "income_type"):
        if key in member_filter:
            vals = member_filter[key]
            if not isinstance(vals, list):
                vals = [vals]
            if not all(isinstance(v, str) for v in vals):
                problems.append(f"{prefix} member_filter {key} must be a string or list of strings")


def _validate_condition(cond: Any, problems: list[str], prefix: str = "condition") -> None:
    if not isinstance(cond, dict):
        problems.append(f"{prefix} must be a mapping")
        return
    ctype = cond.get("type")
    if ctype not in VALID_CONDITION_TYPES:
        problems.append(f"{prefix} has unknown type '{ctype}'")
        return
    if ctype == "min_members_matching":
        count = cond.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            problems.append(f"{prefix} count must be a positive integer")
        _validate_member_filter(cond.get("member_filter", {}), problems, prefix)
    elif ctype == "flag":
        if cond.get("flag") not in KNOWN_FLAGS:
            problems.append(f"{prefix} references unknown flag '{cond.get('flag')}'")
    elif ctype == "housing_status":
        if cond.get("equals") not in ("rent", "own"):
            problems.append(f"{prefix} housing_status equals must be rent or own")
    elif ctype == "income_drop_min_pct":
        if not isinstance(cond.get("pct"), (int, float)):
            problems.append(f"{prefix} income_drop_min_pct needs a numeric pct")
    elif ctype == "builtin_value_positive":
        if cond.get("name") not in BUILTIN_VALUE_NAMES:
            problems.append(f"{prefix} references unknown builtin '{cond.get('name')}'")
    elif ctype == "any_of":
        subs = cond.get("conditions")
        if not isinstance(subs, list) or not subs:
            problems.append(f"{prefix} any_of needs a non-empty conditions list")
        else:
            for i, sub in enumerate(subs):
                if isinstance(sub, dict) and sub.get("type") == "any_of":
                    problems.append(f"{prefix} any_of cannot nest another any_of")
                else:
                    _validate_condition(sub, problems, prefix=f"{prefix}.conditions[{i}]")


def _validate_income(income: Any, problems: list[str]) -> None:
    if not isinstance(income, dict):
        problems.append("income must be a mapping")
        return
    itype = income.get("type")
    if itype not in VALID_INCOME_TYPES:
        problems.append(f"income has unknown type '{itype}'")
        return
    if itype == "fpl_percent":
        if not isinstance(income.get("limit_pct"), (int, float)):
            problems.append("income fpl_percent needs a numeric limit_pct")
        if "min_pct" in income and not isinstance(income["min_pct"], (int, float)):
            problems.append("income min_pct must be numeric")
    elif itype == "fixed":
        if not isinstance(income.get("amount"), (int, float)):
            problems.append("income fixed needs a numeric amount")
    elif itype == "fixed_by_size":
        amounts = income.get("amounts")
        if not isinstance(amounts, dict) or not amounts:
            problems.append("income fixed_by_size needs an amounts mapping keyed by size")
        else:
            if not all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in amounts.values()
            ):
                problems.append("income fixed_by_size amounts must be numeric")
            if not all(
                (isinstance(k, int) and not isinstance(k, bool))
                or (isinstance(k, str) and k.isdigit())
                for k in amounts
            ):
                problems.append("income fixed_by_size amounts keys must be integer household sizes")
        if "per_additional" in income and not isinstance(income["per_additional"], (int, float)):
            problems.append("income per_additional must be numeric")
    elif itype == "fixed_by_filing_status":
        amounts = income.get("amounts")
        if not isinstance(amounts, dict) or not amounts:
            problems.append("income fixed_by_filing_status needs an amounts mapping")
        elif not set(amounts) <= set(VALID_FILING_STATUSES):
            problems.append(
                f"income fixed_by_filing_status keys must be among {', '.join(VALID_FILING_STATUSES)}"
            )


def _validate_value(value: Any, problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append("value must be a mapping")
        return
    vtype = value.get("type")
    if vtype not in VALID_VALUE_TYPES:
        problems.append(f"value has unknown type '{vtype}'")
        return
    period = value.get("period", "year")
    if period not in ("year", "month"):
        problems.append("value period must be year or month")
    if vtype == "fixed" and not isinstance(value.get("amount"), (int, float)):
        problems.append("value fixed needs a numeric amount")
    elif vtype == "range":
        if not isinstance(value.get("min"), (int, float)) or not isinstance(value.get("max"), (int, float)):
            problems.append("value range needs numeric min and max")
        elif value["min"] > value["max"]:
            problems.append("value range min cannot exceed max")
    elif vtype == "per_member":
        if not isinstance(value.get("amount"), (int, float)):
            problems.append("value per_member needs a numeric amount")
        _validate_member_filter(value.get("member_filter", {}), problems, "value per_member")
    elif vtype == "builtin" and value.get("name") not in BUILTIN_VALUE_NAMES:
        problems.append(f"value references unknown builtin '{value.get('name')}'")


def validate_rule_data(data: dict[str, Any], path: str | Path = "<memory>") -> list[str]:
    """Return a list of problems (empty when the rule data is valid)."""
    problems: list[str] = []
    for key in REQUIRED_KEYS:
        if key not in data:
            problems.append(f"missing required key '{key}'")
    unknown = set(data) - _RULE_FIELDS
    if unknown:
        problems.append(f"unknown top-level keys {sorted(unknown)}")
    if problems:
        return problems

    for key in ("id", "name", "category", "jurisdiction", "description",
                "next_step", "application_url", "source_url"):
        if not isinstance(data[key], str) or not data[key].strip():
            problems.append(f"'{key}' must be a non-empty string")
    if "notes" in data and not isinstance(data["notes"], str):
        problems.append("notes must be a string")

    if data["category"] not in VALID_CATEGORIES:
        problems.append(f"unknown category '{data['category']}'")
    if data["jurisdiction"] not in VALID_JURISDICTIONS:
        problems.append(f"unknown jurisdiction '{data['jurisdiction']}'")
    elif data["jurisdiction"] in ("state", "county"):
        states = data.get("states")
        if (
            not isinstance(states, list)
            or not states
            or not all(isinstance(s, str) and len(s.strip()) == 2 for s in states)
        ):
            problems.append(
                "state and county rules must list applicable states as "
                "two-letter codes, e.g. states: [KS]"
            )
    if "states" in data and not isinstance(data["states"], list):
        problems.append("states must be a list of two-letter codes")
    if data.get("household_size_basis", "all") not in SIZE_BASES:
        problems.append(f"unknown household_size_basis '{data.get('household_size_basis')}'")
    if data.get("conditions_mode", "all") not in ("all", "any"):
        problems.append("conditions_mode must be all or any")
    if data.get("confidence", "screen") not in VALID_CONFIDENCE:
        problems.append(f"confidence must be one of {', '.join(VALID_CONFIDENCE)}")
    cap = data.get("verdict_cap")
    if cap is not None and cap not in VALID_VERDICT_CAPS:
        problems.append(f"verdict_cap must be one of {', '.join(VALID_VERDICT_CAPS)}")
    margin = data.get("borderline_margin_pct", 10.0)
    if not isinstance(margin, (int, float)) or margin < 0:
        problems.append("borderline_margin_pct must be a non-negative number")
    categorical = data.get("categorical_flags", [])
    if categorical is None or not isinstance(categorical, list):
        problems.append("categorical_flags must be a list of flag names")
    else:
        for flag in categorical:
            if flag not in KNOWN_FLAGS:
                problems.append(f"categorical_flags references unknown flag '{flag}'")
    enrolled = data.get("skip_if_already_enrolled")
    if enrolled is not None and enrolled not in KNOWN_FLAGS:
        problems.append(f"skip_if_already_enrolled references unknown flag '{enrolled}'")
    documents = data.get("documents")
    if (
        not isinstance(documents, list)
        or not documents
        or not all(isinstance(d, str) and d.strip() for d in documents)
    ):
        problems.append("documents must be a non-empty list of strings")
    if not str(data.get("source_url", "")).startswith("http"):
        problems.append("source_url must be an http(s) URL")
    try:
        date.fromisoformat(str(data["last_verified"]))
    except (ValueError, TypeError):
        problems.append("last_verified must be an ISO date (YYYY-MM-DD)")

    _validate_income(data["income"], problems)
    _validate_value(data["value"], problems)
    conditions = data.get("conditions", [])
    if not isinstance(conditions, list):
        problems.append("conditions must be a list")
    else:
        for i, cond in enumerate(conditions):
            _validate_condition(cond, problems, prefix=f"conditions[{i}]")
    return problems


def load_rule_file(path: str | Path) -> Rule:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuleValidationError(path, [f"not valid YAML ({exc})"]) from exc
    if not isinstance(raw, dict):
        raise RuleValidationError(path, ["file is not a YAML mapping"])
    problems = validate_rule_data(raw, path)
    if problems:
        raise RuleValidationError(path, problems)
    raw = dict(raw)
    raw["id"] = str(raw["id"])
    raw["last_verified"] = str(raw["last_verified"])
    raw["states"] = [str(s).upper() for s in raw.get("states", [])]
    kwargs = {k: v for k, v in raw.items() if k in _RULE_FIELDS}
    return Rule(**{**kwargs, "source_file": str(path)})


def builtin_rules_dir() -> Path:
    return Path(str(files("benefit_finder") / "rules"))


def load_rules(
    state: str | None = None,
    extra_dirs: Sequence[str | Path] = (),
) -> list[Rule]:
    """Load all applicable rules for a state.

    Federal rules always apply. State and county rules apply when the
    profile's state is in the rule's states list. Later directories in
    extra_dirs override built-in rules that share an id.
    """
    extras = [Path(d) for d in extra_dirs]
    for directory in extras:
        if not directory.is_dir():
            raise ValueError(f"rules directory not found or not a directory, {directory}")
    directories = [builtin_rules_dir(), *extras]
    by_id: dict[str, Rule] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.yaml")):
            rule = load_rule_file(path)
            by_id[rule.id] = rule
    applicable = []
    for rule in by_id.values():
        if rule.jurisdiction == "federal":
            applicable.append(rule)
        elif state and state.strip().upper() in rule.states:
            applicable.append(rule)
    return sorted(applicable, key=lambda r: r.id)
