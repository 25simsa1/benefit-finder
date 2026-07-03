# benefit-finder

A command line tool that screens a US household against public benefits,
assistance programs, and tax credits, then generates an organized report
sorted by estimated annual dollar value.

It is a static rules engine. No network calls, no accounts, nothing
leaves your machine. Each program is a YAML file with an income limit,
eligibility conditions, an estimated value, and a source URL with a
last-verified date.

> **Important.** This is a screening tool, not an eligibility
> determination. Income limits change every year. Every number in the
> output carries a source link so you can verify current limits before
> relying on it.

## Install

Requires Python 3.11+.

```bash
pip install .          # from a clone of this repo
# or for development
pip install -e ".[dev]"
```

## Usage

```bash
# 1. Build your household profile (interactive prompts)
benefit-finder init

# or try the built-in demo profile, a family of 5 in Kansas at $45k AGI
benefit-finder init --sample

# 2. Screen the profile and print a summary table
benefit-finder screen

# 3. Write the full markdown report
benefit-finder report --out report.md
```

`screen` and `report` accept `--profile path/to/profile.json` and a
repeatable `--rules-dir DIR` that layers extra rule files over the
built-in set (matching ids override).

## Web app

The same engine is available as a local web app. Install the `web`
extra and run one command:

```bash
pip install -e ".[web]"
benefit-finder-web            # serves http://127.0.0.1:8000
```

Then open <http://127.0.0.1:8000>. The app has three screens: a
multi-step **intake wizard** (household members as repeatable cards,
AGI and prior-year AGI, housing, and situation flags, with **Export
profile** / **Import profile** so the JSON is interchangeable with the
CLI's `profile.json`), a **results dashboard** of expandable cards
grouped Likely eligible / Borderline / Not eligible and sorted by
estimated annual value with a total-value banner. The dashboard has a
**live income control** at the top: type or drag your annual income and
the eligible-programs list, the total-value banner, and the "percent of
the poverty line" figure recompute instantly (the rest of the household
stays as entered), so you can see exactly where each income threshold
falls. Finally a **report view**
that renders the markdown report with **Download .md** and **Print /
Save as PDF**. The FPL-year warning and the verify-current-limits
disclaimer show at the top of every screen, and any verdict that turns
on the household-size nuance (a college student counted differently for
SNAP than for taxes) explains that in the expanded card.

`benefit-finder-web --host 0.0.0.0 --port 8080 --reload` overrides the
defaults.

### API

The frontend is a thin client over a small API:

| Method | Path | In | Out |
|---|---|---|---|
| `GET` | `/api/meta` | — | enums, labels, disclaimers for the UI |
| `POST` | `/api/screen` | profile JSON | results JSON (program, verdict, reasons, estimated value, apply URL, documents, source_url, last_verified, income math) |
| `POST` | `/api/report` | profile JSON | the markdown report |
| `GET` | `/api/report?profile=<json>` | profile JSON in the query | the markdown report |

Request and response bodies are validated by Pydantic models, and the
same `Household.from_dict` domain validation the CLI uses runs on every
request, so both interfaces accept and reject the same input.

### Privacy

The web app has **no database and no accounts**. Your profile lives in
the browser. It is sent to the local server only to compute a result
and is **never written to disk, logged, or persisted** server-side.
Household financial data does not leave your machine. Use **Export
profile** to save a profile yourself as `profile.json`.

## Architecture

The rules engine is independent of any interface. `benefit_finder.core`
holds the one shared entry point (`screen_household`) that loads the
rules for a household's state and runs the engine; the CLI
(`benefit_finder.cli`) and the web app (`benefit_finder.web`) both call
it, so they can never drift. The web package is optional and nothing in
the engine or the CLI imports it.

## What it screens for

Federal programs. SNAP, WIC, school meals (NSLP), Lifeline, ACA
marketplace subsidies, EITC, Child Tax Credit and ACTC, Saver's Credit,
AOTC, Lifetime Learning Credit, Pell Grant (flagged only, the FAFSA
decides), and Summer EBT.

Kansas programs (the seeded example state). LIEAP energy assistance,
KanCare Medicaid and CHIP for children, the food sales tax credit, and
the Homestead property tax refund.

Verdicts are `yes` (the math clearly works, used for computed tax
credits), `likely` (passes this screener), `borderline` (close enough
that applying is worthwhile), `no`, and `enrolled` (the profile says the
household already receives it).

## The household profile

`benefit-finder init` writes `profile.json`. Fields are state, county,
ZIP, a list of members (age, relationship, student status, disabled,
employed, income type), current and prior-year AGI, housing status and
monthly cost, and flags such as `pregnant_member`, `veteran`,
`recent_job_loss`, `college_student_living_away`, `receives_snap`, and
`receives_medicaid`. Prior-year AGI powers the special situations
section, for example an income drop over 25% suggests financial aid
appeals and an ACA mid-year update.

Household size is not one number. A college student living away can
count differently for SNAP than for taxes or the FAFSA, so each rule
declares which counting basis it uses (`all`, `snap`, `tax`, `fafsa`).

## Adding a state or program

Copy an existing YAML in `src/benefit_finder/rules/` and follow
`docs/RULE_SCHEMA.md`. State rules live in `rules/states/<state>/` and
declare `states: [XX]`, so adding a state means adding files, not code.
Set `source_url` and `last_verified` honestly, the report prints them.

The Federal Poverty Level table lives in `src/benefit_finder/fpl.py`
with a `FPL_YEAR` constant. When the bundled year is older than the
current year, the screen and report commands print a warning.

## Future refresh

`benefit-finder refresh` is a stub today. The design seam already
exists, every rule carries a `source_url`, and `--rules-dir` layers
overrides over built-ins by rule id. A refresh implementation would
fetch official pages, regenerate an overlay directory, and leave the
shipped rules untouched.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Tests cover the FPL table, household-size bases, every verdict path
through the engine, the tax credit estimators, validation of every
shipped rule file, and an end-to-end Kansas smoke scenario.
