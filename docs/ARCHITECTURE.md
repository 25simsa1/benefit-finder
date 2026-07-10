# Architecture

## Layering

The rules engine is independent of any interface. `core.py` holds the
one shared entry point, `screen_household`, that loads the rules for a
household's state and runs the engine. The CLI and the web app both call
it, so they can never drift. The web package is optional, nothing in the
engine or the CLI imports it.

```
cli.py            web/app.py
       \          /
        core.py  (screen_household, rules_for)
       /    |    \
engine.py rules_loader.py  report.py
   |            |
values.py    models.py
   |            |
 fpl.py     (Household, Member)
```

## Module map (`src/benefit_finder/`)

- `core.py`. The shared entry point, `rules_for` and `screen_household`,
  that loads a household's rules and runs the engine. The one place the
  CLI and web app both call into.
- `models.py`. The `Household` and `Member` dataclasses, profile
  validation (`Household.from_dict`, `Member.validate`), household-size
  math across counting bases (`all`, `snap`, `tax`, `fafsa`), filing
  status inference, and JSON load/save for `profile.json`.
- `fpl.py`. Federal Poverty Level tables by region (contiguous US,
  Alaska, Hawaii), `FPL_YEAR`/`FPL_LAST_VERIFIED` constants, and helpers
  to compute a dollar limit or express income as a percent of FPL.
- `rules_loader.py`. Loads and validates program YAML files into `Rule`
  dataclasses, rejecting unknown keys and malformed income/condition/value
  blocks; layers extra `--rules-dir` directories over the built-in set by
  rule id.
- `values.py`. Dollar-value estimators, fixed/range/per-member values
  plus the tax-credit builtins (EITC, CTC/ACTC, Saver's Credit, SNAP)
  driven by `TAX_PARAMS_YEAR` parameters.
- `engine.py`. The eligibility engine, `evaluate`/`evaluate_all`. Runs a
  rule's conditions and income test against a household and produces an
  `Evaluation` with a verdict (`yes`, `likely`, `borderline`, `no`,
  `enrolled`), human-readable reasons, and an estimated value.
- `report.py`. Renders a list of `Evaluation`s into the markdown report
  (`generate_report`), including the special-situations section and the
  total-value banner math.
- `cli.py`. The `benefit-finder` command, subcommands `init` (interactive
  or `--sample` profile creation), `screen`, `report`, and the `refresh`
  stub. Argument parsing lives in `_build_parser`.
- `web/app.py`. FastAPI app exposing `/api/meta`, `/api/screen`,
  `/api/report` (POST and GET), and serving the static frontend at `/`.
  Validates request bodies with Pydantic models in `web/schemas.py` and
  calls the same `core.screen_household` / `Household.from_dict` path as
  the CLI.
- `web/static/`. The frontend, plain HTML/CSS/JS (no build step). `app.js`
  wires the intake wizard (`wizard.js`), the results dashboard
  (`dashboard.js`), and the report view (`report.js`) through a small API
  client (`api.js`), shared state (`state.js`), and DOM/markdown helpers
  (`dom.js`, `markdown.js`).

## Rules as data

Every program is one YAML file under `rules/federal/` or
`rules/states/<state>/` (12 federal, 5 Kansas today, 17 total). A rule
declares its income test, eligibility conditions, estimated value,
household-size counting basis, and application metadata (`next_step`,
`application_url`, `documents`, `source_url`, `last_verified`). The full
schema, valid enum values, and worked examples are in
`docs/RULE_SCHEMA.md`. Adding a state or program means adding a YAML
file, not code.

## Tests (`tests/`)

`test_fpl.py`, `test_models.py`, `test_values.py`, and `test_engine.py`
cover the corresponding modules directly. `test_rules_files.py` validates
every shipped rule file loads and passes schema checks.
`test_smoke_kansas.py` runs an end-to-end scenario through
`core.screen_household`. `test_hardening.py` and
`test_hardening_round2.py` cover malformed/edge-case input.
`test_api.py` exercises the FastAPI endpoints via `TestClient`.
`conftest.py` holds shared fixtures.

144 tests pass as of this writing (`.venv/bin/pytest -q`).
