# State

## Current status

The engine, CLI, and web app are all built and working. 17 program rules
are seeded (12 federal, 5 Kansas as the example state) and the test
suite is green at 144 tests (`.venv/bin/pytest -q`). The working tree is
clean, everything through the README rewrite is committed on `main`.

Federal programs covered. SNAP, WIC, NSLP (school meals), Lifeline, ACA
marketplace subsidies, EITC, Child Tax Credit and ACTC, Saver's Credit,
AOTC, Lifetime Learning Credit, Pell Grant (flagged only), Summer EBT.

Kansas programs covered. LIEAP, KanCare Medicaid and CHIP for children,
Medicaid for pregnant members, the food sales tax credit, the Homestead
refund.

## In flight

A double-click desktop app so non-technical users can run the web app
with no Python and no terminal. New launcher `desktop.py` (console script
`benefit-finder-app`) picks a free port, starts uvicorn on the shared
`app` object, and opens the browser. Packaged with PyInstaller via
`packaging/benefit_finder.spec` (shared across OSes) plus
`packaging/build_mac.sh` and `packaging/build_windows.bat`. The Mac
`.app` is built and launch-tested end-to-end (serves `/`, `/api/meta`,
`/api/screen`), including from a clean unzip. End-user guide in
`docs/HOW-TO-OPEN.md`, maintainer guide in `docs/BUILD.md`. Tests green
at 148 (added `tests/test_desktop.py`). Not yet committed.

The Windows `.exe` build is written but not run (needs a Windows
machine; PyInstaller cannot cross-compile). Code signing / notarization
is intentionally out of scope, so first launch needs the documented
right-click Open (Mac) / Run anyway (Windows) step.

The last commit (`e036819`) wrote the README covering the CLI, the web
app, and the privacy note.

## Next steps

- Add a second state's rule set to prove out the `states/<state>/`
  pattern beyond the Kansas example.
- Decide whether `benefit-finder refresh` (currently a stub, see README)
  gets a real implementation, it would fetch official pages and write an
  overlay directory without touching the shipped rules.
- Keep `FPL_YEAR` (currently 2025 in `fpl.py`) and the EITC/CTC/Saver's
  Credit parameters in `values.py` (`TAX_PARAMS_YEAR`, currently 2025)
  current each January.

## Open questions

- How much further the web app needs to go before it is more than a
  local single-user tool (no accounts or persistence by design, see
  README's Privacy section).
- Whether more federal programs (e.g. TANF, LIHEAP nationally vs. the
  Kansas-specific LIEAP) belong in the federal set or stay state-scoped.
