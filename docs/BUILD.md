# Building the double-click app

The desktop app bundles Python, the web server, the rule files, and the
frontend into a single double-clickable app. Users run it with no Python
and no terminal. It launches the local web server on a free port and
opens the default browser. Everything still runs locally.

The launcher lives in `src/benefit_finder/desktop.py` (console script
`benefit-finder-app`). Packaging is driven by
`packaging/benefit_finder.spec`, a single PyInstaller spec that adapts to
the OS it is run on. PyInstaller cannot cross-compile, so each OS build
must run on that OS.

## macOS

```bash
bash packaging/build_mac.sh
```

Output:

- `dist/Benefit Finder.app` — the app.
- `dist/Benefit Finder-mac.zip` — zip this to send. Zipping preserves the
  `.app` bundle structure through email and downloads.

The app is unsigned, so first launch needs a right-click → Open (see
`docs/HOW-TO-OPEN.md`). Removing that step requires an Apple Developer
account for signing and notarization, which is intentionally out of
scope.

## Windows

Run on a Windows machine, from a Command Prompt at the repo root:

```bat
packaging\build_windows.bat
```

Output:

- `dist\Benefit Finder\Benefit Finder.exe` and its support folder.

Zip the whole `dist\Benefit Finder` folder and share the zip. The
Windows build keeps a small console window that shows a "close this
window to quit" message. First launch may show a SmartScreen prompt
(More info → Run anyway) because the app is unsigned.

## Notes

- The build scripts create/use a local virtualenv and install the
  `package` extra (`pip install -e ".[package]"`), which adds PyInstaller.
- `dist/` and `build/` are build artifacts and are not committed.
- The spec bundles `benefit_finder/rules/**` and
  `benefit_finder/web/static/**` as data and collects uvicorn's dynamic
  submodules as hidden imports. If a future dependency imports things
  dynamically and goes missing in the frozen app, add it to
  `hiddenimports` in the spec.
