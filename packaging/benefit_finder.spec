# PyInstaller spec for the Benefit Finder double-click app.
#
# Build with:   pyinstaller packaging/benefit_finder.spec
# On macOS this produces dist/Benefit Finder.app
# On Windows this produces dist/Benefit Finder/Benefit Finder.exe
#
# Run from the repo root so the relative paths below resolve.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "benefit_finder"

# Bundle the rule YAML files and the web frontend as data, preserving the
# package-relative layout the app reads them from at runtime.
datas = [
    (str(PKG / "rules"), "benefit_finder/rules"),
    (str(PKG / "web" / "static"), "benefit_finder/web/static"),
]

# uvicorn imports its loop/protocol backends dynamically, so PyInstaller
# cannot see them by static analysis. Collect them explicitly.
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("benefit_finder")
)

a = Analysis(
    [str(PKG / "desktop.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# On macOS a windowed app must not spawn a Terminal, so console=False.
# On Windows we keep a console window: it shows the friendly "close this
# window to quit" message and gives beginners an obvious off-switch.
is_windows = sys.platform.startswith("win")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Benefit Finder",
    console=is_windows,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="Benefit Finder",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Benefit Finder.app",
        icon=None,
        bundle_identifier="com.benefitfinder.app",
        info_plist={
            "CFBundleName": "Benefit Finder",
            "CFBundleDisplayName": "Benefit Finder",
            "LSBackgroundOnly": False,
        },
    )
