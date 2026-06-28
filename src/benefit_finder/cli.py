"""Command line interface for benefit-finder."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from . import __version__
from . import fpl as fpl_mod
from .core import screen_household
from .engine import Evaluation, Verdict
from .models import (
    HOUSING_STATUSES,
    INCOME_TYPES,
    KNOWN_FLAGS,
    RELATIONSHIPS,
    STUDENT_STATUSES,
    Household,
    Member,
    ProfileError,
    sample_household,
)
from .report import DISCLAIMER, generate_report, total_range

DEFAULT_PROFILE = "profile.json"
DEFAULT_REPORT = "report.md"


# ------------------------------------------------------------ prompts ----

def _ask(
    prompt: str,
    default: str | None = None,
    choices: Sequence[str] | None = None,
    cast: Callable[[str], Any] = str,
    allow_blank: bool = False,
) -> Any:
    suffix = f" [{default}]" if default is not None else ""
    if choices:
        prompt = f"{prompt} ({'/'.join(choices)})"
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            if default is not None:
                raw = default
            elif allow_blank:
                return None
            else:
                print("  A value is required.")
                continue
        if choices and raw.lower() not in choices:
            print(f"  Please answer one of {', '.join(choices)}.")
            continue
        try:
            return cast(raw.lower() if choices else raw)
        except ValueError:
            print("  Could not parse that, try again.")


def _ask_bool(prompt: str, default: bool = False) -> bool:
    answer = _ask(prompt, default="y" if default else "n", choices=("y", "n"))
    return answer == "y"


def _interactive_profile() -> Household:
    print("Let's build your household profile. Press Enter to accept defaults.\n")
    state = _ask("Two-letter state code", cast=lambda s: s.strip().upper())
    county = _ask("County", default="", allow_blank=True) or ""
    zip_code = _ask("ZIP code", default="", allow_blank=True) or ""

    members: list[Member] = []
    count = _ask("How many people in the household", cast=int)
    for i in range(1, count + 1):
        print(f"\nMember {i}")
        age = _ask("  Age", cast=int)
        default_rel = "self" if i == 1 else ("spouse" if i == 2 else "child")
        relationship = _ask("  Relationship", default=default_rel, choices=RELATIONSHIPS)
        student = _ask("  Student status", default="none", choices=STUDENT_STATUSES)
        disabled = _ask_bool("  Disabled")
        employed = _ask_bool("  Employed")
        income_type = _ask("  Income type", default="none", choices=INCOME_TYPES)
        members.append(
            Member(
                age=age,
                relationship=relationship,
                student=student,
                disabled=disabled,
                employed=employed,
                income_type=income_type,
            )
        )

    print()
    agi = _ask("Annual household AGI in dollars", cast=float)
    prior = _ask(
        "Prior-year AGI in dollars (blank to skip)", cast=float, allow_blank=True
    )
    housing = _ask("Housing status", default="rent", choices=HOUSING_STATUSES)
    monthly = _ask(
        "Monthly housing cost in dollars (blank to skip)", cast=float, allow_blank=True
    )

    print("\nA few yes/no flags that unlock specific programs.")
    flag_prompts = {
        "pregnant_member": "Is anyone in the household pregnant",
        "veteran": "Is anyone a veteran",
        "recent_job_loss": "Has anyone lost a job recently",
        "college_student_living_away": "Is a college student living away from home",
        "receives_snap": "Does the household already receive SNAP",
        "receives_medicaid": "Does anyone already have Medicaid",
    }
    flags = {name: _ask_bool(text) for name, text in flag_prompts.items()}

    household = Household(
        state=state,
        county=county,
        zip_code=zip_code,
        members=members,
        agi=agi,
        prior_year_agi=prior,
        housing_status=housing,
        monthly_housing_cost=monthly,
        flags=flags,
    )
    household.validate()
    return household


# ------------------------------------------------------------ commands ----

def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.profile)
    if path.exists() and not args.force:
        print(f"{path} already exists. Re-run with --force to overwrite.", file=sys.stderr)
        return 2
    if args.sample:
        household = sample_household()
        print(f"Writing the built-in sample profile (family of 5 in KS, $45k AGI) to {path}.")
    else:
        try:
            household = _interactive_profile()
        except (EOFError, KeyboardInterrupt):
            print(
                "\nNo interactive input available. Use `benefit-finder init --sample` "
                "for a demo profile, or run in a terminal.",
                file=sys.stderr,
            )
            return 2
        except ProfileError as exc:
            print(f"Profile problem. {exc}", file=sys.stderr)
            return 2
    household.save(path)
    print(f"Saved {path}. Next, run `benefit-finder screen`.")
    return 0


def _load_inputs(args: argparse.Namespace) -> tuple[Household, list[Evaluation]]:
    try:
        household = Household.load(args.profile)
    except FileNotFoundError:
        raise ProfileError(
            f"no profile found at {args.profile}. Run `benefit-finder init` "
            f"first or point at one with --profile."
        ) from None
    return household, screen_household(household, extra_dirs=args.rules_dir)


def _print_screen(household: Household, evaluations: list[Evaluation]) -> None:
    size = household.household_size("all")
    print(
        f"\nBenefit screen for a household of {size} in {household.state} "
        f"(AGI ${household.agi:,.0f})"
    )
    warning = fpl_mod.fpl_year_warning()
    if warning:
        print(f"\n{warning}")
    print()

    headers = ("Program", "Verdict", "Est. value/yr", "Next step")
    rows = []
    for ev in evaluations:
        value = "-" if (ev.verdict is Verdict.NO or ev.value is None) else ev.value.format()
        step = ev.rule.next_step.strip() if ev.verdict is not Verdict.NO else "-"
        if len(step) > 46:
            step = step[:43] + "..."
        name = ev.rule.name
        if len(name) > 42:
            name = name[:39] + "..."
        rows.append((name, ev.verdict.value, value, step))
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    low, high = total_range(evaluations)
    if high > 0:
        print(
            f"\nLikely-eligible programs could be worth roughly ${low:,.0f} to "
            f"${high:,.0f} per year combined."
        )
    print(f"\n{DISCLAIMER}")


def cmd_screen(args: argparse.Namespace) -> int:
    household, evaluations = _load_inputs(args)
    _print_screen(household, evaluations)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    household, evaluations = _load_inputs(args)
    markdown = generate_report(evaluations, household)
    Path(args.out).write_text(markdown, encoding="utf-8")
    print(f"Wrote {args.out} ({len(evaluations)} programs screened).")
    warning = fpl_mod.fpl_year_warning()
    if warning:
        print(warning)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    print(
        "Not implemented yet. Rules are static YAML files bundled with the "
        "package. Every rule carries a source_url, so a future refresh can "
        "fetch official pages and rewrite an overlay rules directory, then "
        "pass it with --rules-dir. For now, edit the YAML files directly."
    )
    return 0


# ---------------------------------------------------------------- main ----

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benefit-finder",
        description=(
            "Screen a US household for public benefits, assistance programs, "
            "and tax credits, then generate an organized report."
        ),
    )
    parser.add_argument("--version", action="version", version=f"benefit-finder {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="interactively create profile.json")
    p_init.add_argument("--profile", default=DEFAULT_PROFILE, help="where to save the profile")
    p_init.add_argument("--sample", action="store_true", help="write a demo profile instead of prompting")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing profile")
    p_init.set_defaults(func=cmd_init)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default=DEFAULT_PROFILE, help="path to profile.json")
    common.add_argument(
        "--rules-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="extra rules directory layered over the built-in rules (repeatable)",
    )

    p_screen = sub.add_parser("screen", parents=[common], help="print a summary eligibility table")
    p_screen.set_defaults(func=cmd_screen)

    p_report = sub.add_parser("report", parents=[common], help="write a full markdown report")
    p_report.add_argument("--out", default=DEFAULT_REPORT, help="output markdown path")
    p_report.set_defaults(func=cmd_report)

    p_refresh = sub.add_parser("refresh", help="(future) update rules from official sources")
    p_refresh.set_defaults(func=cmd_refresh)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        # ProfileError, RuleValidationError, and bad --rules-dir all land here
        print(f"Error. {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"File error. {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
