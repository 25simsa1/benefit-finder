"""Estimate annual dollar values for programs.

Estimates are deliberately rough screening numbers, not determinations.
The tax credit builtins use TAX_PARAMS_YEAR parameters and state their
assumptions in the returned note. Update the constants annually.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fpl import region_for_state
from .models import CHILD_RELATIONSHIPS, Household

TAX_PARAMS_YEAR = 2025


@dataclass
class ValueEstimate:
    low: float
    high: float
    note: str = ""

    def format(self) -> str:
        if self.high <= 0:
            return "$0"
        if abs(self.high - self.low) < 1:
            return f"${self.high:,.0f}"
        return f"${self.low:,.0f} to ${self.high:,.0f}"


# ---------------------------------------------------------------- EITC ----
# Tax year 2025 parameters (Rev. Proc. 2024-40).
# kids: (max credit, phase-in rate, phase-out rate,
#        phase-out start MFJ, phase-out start other)
_EITC_2025: dict[int, tuple[float, float, float, float, float]] = {
    0: (649, 0.0765, 0.0765, 17_730, 10_620),
    1: (4_328, 0.34, 0.1598, 30_470, 23_350),
    2: (7_152, 0.40, 0.2106, 30_470, 23_350),
    3: (8_046, 0.45, 0.2106, 30_470, 23_350),
}


def _eitc_qualifying_children(household: Household) -> int:
    count = 0
    for m in household.members:
        if m.relationship not in CHILD_RELATIONSHIPS:
            continue
        if m.age <= 18 or (m.age <= 23 and m.student == "college") or m.disabled:
            count += 1
    return count


def _estimate_eitc(household: Household) -> ValueEstimate:
    kids = min(3, _eitc_qualifying_children(household))
    if kids == 0 and not any(
        m.relationship in ("self", "spouse") and 25 <= m.age <= 64
        for m in household.members
    ):
        return ValueEstimate(
            0, 0, "Workers without a qualifying child must be 25 to 64 to claim the EITC."
        )
    max_credit, phase_in, phase_out, po_mfj, po_other = _EITC_2025[kids]
    po_start = po_mfj if household.filing_status == "mfj" else po_other
    earned = household.agi  # screening assumption, all AGI is earned income
    credit = min(max_credit, earned * phase_in)
    credit -= max(0.0, (household.agi - po_start) * phase_out)
    credit = max(0.0, round(credit))
    note = (
        f"Estimate uses tax year {TAX_PARAMS_YEAR} EITC parameters with "
        f"{kids} qualifying child(ren) and assumes all AGI is earned income. "
        f"Investment income over the annual cap disqualifies the credit."
    )
    return ValueEstimate(credit, credit, note)


# ------------------------------------------------------------ CTC/ACTC ----
_CTC_PER_CHILD_2025 = 2_200
_ACTC_REFUNDABLE_CAP_2025 = 1_700
_CTC_PHASEOUT_START = {"mfj": 400_000, "hoh": 200_000, "single": 200_000}


def _estimate_ctc(household: Household) -> ValueEstimate:
    kids = sum(
        1
        for m in household.members
        if m.relationship in CHILD_RELATIONSHIPS and m.age <= 16
    )
    total = float(_CTC_PER_CHILD_2025 * kids)
    excess = max(0.0, household.agi - _CTC_PHASEOUT_START[household.filing_status])
    if excess:
        total = max(0.0, total - (excess // 1_000 + (1 if excess % 1_000 else 0)) * 50)
    refundable = min(
        total,
        _ACTC_REFUNDABLE_CAP_2025 * kids,
        0.15 * max(0.0, household.agi - 2_500),
    )
    note = (
        f"Tax year {TAX_PARAMS_YEAR} credit is ${_CTC_PER_CHILD_2025:,} per child "
        f"under 17 with a valid SSN. Up to ${_ACTC_REFUNDABLE_CAP_2025:,} per child "
        f"is refundable, so the low end is what a household with little tax "
        f"liability could still receive."
    )
    return ValueEstimate(round(refundable), round(total), note)


# -------------------------------------------------------- Saver's Credit ----
# Tax year 2025 AGI tiers, (ceiling, credit rate).
_SAVERS_2025: dict[str, list[tuple[float, float]]] = {
    "mfj": [(47_500, 0.5), (51_000, 0.2), (79_000, 0.1)],
    "hoh": [(35_625, 0.5), (38_250, 0.2), (59_250, 0.1)],
    "single": [(23_750, 0.5), (25_500, 0.2), (39_500, 0.1)],
}
_SAVERS_MAX_CONTRIBUTION = 2_000  # per person


def _estimate_savers(household: Household) -> ValueEstimate:
    rate = 0.0
    for ceiling, tier_rate in _SAVERS_2025[household.filing_status]:
        if household.agi <= ceiling:
            rate = tier_rate
            break
    contributors = sum(
        1
        for m in household.members
        if m.age >= 18 and m.employed and m.student != "college"
    )
    high = rate * _SAVERS_MAX_CONTRIBUTION * min(contributors, 2)
    note = (
        f"Tax year {TAX_PARAMS_YEAR} rates. Requires actually contributing to a "
        f"retirement account (up to ${_SAVERS_MAX_CONTRIBUTION:,} counts per "
        f"person). Nonrefundable, so the value is capped by tax owed. "
        f"Full-time students and dependents are ineligible."
    )
    return ValueEstimate(0.0, round(high), note)


# ---------------------------------------------------------------- SNAP ----
# FY2025 maximum monthly allotments, 48 contiguous states (USDA FNS).
_SNAP_MAX_MONTHLY_FY2025 = {1: 292, 2: 536, 3: 768, 4: 975, 5: 1_158, 6: 1_390, 7: 1_536, 8: 1_756}
_SNAP_EACH_ADDITIONAL = 220
# FY2025 standard deduction by household size (48 states).
_SNAP_STD_DEDUCTION = {1: 204, 2: 204, 3: 204, 4: 217, 5: 254, 6: 291}
# FY2025 minimum monthly benefit for eligible 1-2 person households.
_SNAP_MIN_MONTHLY = 23


def _estimate_snap(household: Household) -> ValueEstimate:
    size = household.household_size("snap")
    if size <= 8:
        max_monthly: float = _SNAP_MAX_MONTHLY_FY2025[size]
    else:
        max_monthly = _SNAP_MAX_MONTHLY_FY2025[8] + _SNAP_EACH_ADDITIONAL * (size - 8)
    std = _SNAP_STD_DEDUCTION[min(size, 6)]
    # 20 percent earned income deduction plus the standard deduction; the
    # excess shelter deduction is ignored, which makes this conservative.
    net_monthly = max(0.0, household.agi / 12 * 0.8 - std)
    est_monthly = max(0.0, max_monthly - 0.3 * net_monthly)
    if size <= 2:
        est_monthly = max(est_monthly, _SNAP_MIN_MONTHLY)
    if est_monthly <= 0:
        return ValueEstimate(0, 0, "Estimated benefit is $0 at this net income.")
    low = round(est_monthly * 0.7 * 12)
    high = round(min(est_monthly * 1.3, max_monthly) * 12)
    note = (
        "Estimate uses FY2025 maximum allotments and the 20 percent earned "
        "income and standard deductions only. Households with high housing "
        "costs often qualify for more via the excess shelter deduction."
    )
    if region_for_state(household.state) != "contiguous":
        note += (
            " Alaska and Hawaii maximum allotments are higher than the "
            "48-state figures used here, so the real benefit is likely larger."
        )
    return ValueEstimate(low, high, note)


_BUILTINS = {
    "eitc": _estimate_eitc,
    "ctc_actc": _estimate_ctc,
    "savers_credit": _estimate_savers,
    "snap": _estimate_snap,
}


def compute_builtin(name: str, household: Household) -> ValueEstimate:
    try:
        return _BUILTINS[name](household)
    except KeyError:
        raise ValueError(f"unknown builtin value estimator '{name}'") from None


def estimate_value(value_spec: dict, household: Household) -> ValueEstimate | None:
    """Estimate annual value from a rule's value block."""
    vtype = value_spec.get("type", "none")
    if vtype == "none":
        return None
    multiplier = 12 if value_spec.get("period", "year") == "month" else 1
    note = str(value_spec.get("note", ""))
    if vtype == "fixed":
        amount = float(value_spec["amount"]) * multiplier
        return ValueEstimate(amount, amount, note)
    if vtype == "range":
        return ValueEstimate(
            float(value_spec["min"]) * multiplier,
            float(value_spec["max"]) * multiplier,
            note,
        )
    if vtype == "per_member":
        count = household.count_members(value_spec.get("member_filter", {}))
        amount = float(value_spec["amount"]) * multiplier * count
        if count == 0:
            note = (note + " No matching members, so the estimate is $0.").strip()
        return ValueEstimate(amount, amount, note)
    if vtype == "builtin":
        est = compute_builtin(str(value_spec["name"]), household)
        if note:
            est.note = (est.note + " " + note).strip()
        return est
    raise ValueError(f"unknown value type '{vtype}'")
