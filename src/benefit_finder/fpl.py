"""Federal Poverty Level (FPL) tables and helpers.

HHS publishes new poverty guidelines each January. To update, bump
FPL_YEAR, refresh the numbers in _TABLES, and update FPL_LAST_VERIFIED.
Everything else in the package derives limits from these values.
"""
from __future__ import annotations

from datetime import date

FPL_YEAR = 2025
FPL_SOURCE_URL = "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
FPL_LAST_VERIFIED = "2025-10-01"

# (first person, each additional person), annual dollars, per the HHS
# poverty guidelines for FPL_YEAR. Alaska and Hawaii have their own tables.
_TABLES: dict[str, tuple[int, int]] = {
    "contiguous": (15_650, 5_500),
    "AK": (19_550, 6_880),
    "HI": (17_990, 6_325),
}


def region_for_state(state: str) -> str:
    """Map a state code to its poverty-guideline table."""
    code = state.strip().upper()
    if code in ("AK", "ALASKA"):
        return "AK"
    if code in ("HI", "HAWAII"):
        return "HI"
    return "contiguous"


def fpl(household_size: int, state: str = "") -> int:
    """Annual FPL in dollars for a household of the given size."""
    if household_size < 1:
        raise ValueError("household_size must be >= 1")
    first, additional = _TABLES[region_for_state(state)]
    return first + additional * (household_size - 1)


def fpl_limit(household_size: int, percent: float, state: str = "") -> float:
    """Dollar income limit at `percent` percent of FPL."""
    return fpl(household_size, state) * (percent / 100.0)


def income_as_percent_of_fpl(income: float, household_size: int, state: str = "") -> float:
    """A household income expressed as a percent of its FPL."""
    return income / fpl(household_size, state) * 100.0


def fpl_year_warning(today: date | None = None) -> str | None:
    """Warning string when the bundled FPL table is stale, else None."""
    current_year = (today or date.today()).year
    if FPL_YEAR < current_year:
        return (
            f"WARNING. The bundled Federal Poverty Level table is from {FPL_YEAR} "
            f"but it is now {current_year}. Income limits shown may be out of date. "
            f"Check {FPL_SOURCE_URL} for current guidelines."
        )
    return None
