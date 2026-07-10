# benefit-finder

A CLI (plus optional local web app) that screens a US household against
public benefits, assistance programs, and tax credits, and generates an
organized report sorted by estimated annual dollar value. Static rules
engine, no network calls, nothing leaves the machine.

## Session protocol

At the start of a session, read `docs/STATE.md` and `docs/ARCHITECTURE.md`
before acting. There is no experiment log for this repo.

After a chunk of work, update `docs/STATE.md` with what changed, what is
in flight, and next steps.

## Conventions

- Python 3.11+, dependencies are PyYAML plus optional FastAPI/uvicorn for
  the web app. Install with `pip install -e ".[dev]"`.
- Run the CLI with `benefit-finder init`, `screen`, `report` (see README
  for flags). Run the web app with `benefit-finder-web`.
- Run tests with `.venv/bin/pytest -q` (or `pytest -q` once the venv is
  active). All tests must stay green before committing.
- The rules engine (`fpl.py`, `models.py`, `rules_loader.py`, `values.py`,
  `engine.py`, `report.py`, tied together by `core.py`) is independent of
  both interfaces. The CLI and the web app both call
  `core.screen_household`, never duplicate that logic in either
  interface.
- Every program is one YAML file under `src/benefit_finder/rules/`
  (`federal/` or `states/<state>/`), validated against
  `docs/RULE_SCHEMA.md`. The loader rejects unknown keys, follow the
  schema exactly. Set `source_url` and `last_verified` honestly, the
  report prints them.
- Prose fields in rule YAML (description, next_step, notes, describe) use
  plain sentences, no em dashes and no colons.
- Household size is not a single number, a rule declares its
  `household_size_basis` (`all`, `snap`, `tax`, `fafsa`) because a
  college student living away counts differently for different programs.
- The FPL table lives in `fpl.py` with a `FPL_YEAR` constant, bump it
  each January along with `FPL_LAST_VERIFIED`.
- Commit style in this repo is first person, lowercase-leaning, no AI
  attribution trailer (see `git log`).

See `docs/ARCHITECTURE.md` for the module map and `docs/STATE.md` for
current status.
