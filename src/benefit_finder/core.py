"""Shared screening service.

The engine (fpl, models, rules_loader, values, engine, report) was
already independent of the CLI. This module is the one place that
orchestrates "load the rules for a household's state and evaluate them",
so the CLI and the web API run the exact same code path and can never
drift. Neither the engine nor this module imports the CLI or the web
layer.
"""
from __future__ import annotations

from typing import Sequence

from .engine import Evaluation, evaluate_all
from .models import Household
from .rules_loader import Rule, load_rules


def rules_for(household: Household, extra_dirs: Sequence[str] = ()) -> list[Rule]:
    """Every rule that applies to this household's state, built-ins plus
    any overlay directories layered on top by rule id."""
    return load_rules(state=household.state, extra_dirs=extra_dirs)


def screen_household(
    household: Household, extra_dirs: Sequence[str] = ()
) -> list[Evaluation]:
    """Run the rules engine over a household and return the evaluations
    sorted by estimated annual value, highest first."""
    return evaluate_all(rules_for(household, extra_dirs), household)
