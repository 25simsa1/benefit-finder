@echo off
REM Build the Benefit Finder Windows app.
REM Run from the repo root in a Command Prompt:  packaging\build_windows.bat
setlocal

cd /d "%~dp0.."

if not exist .venv (
    python -m venv .venv
)

call .venv\Scripts\pip install -e ".[package]"

if exist build rmdir /s /q build
if exist "dist\Benefit Finder" rmdir /s /q "dist\Benefit Finder"

call .venv\Scripts\pyinstaller packaging\benefit_finder.spec --noconfirm

echo.
echo Built: dist\Benefit Finder\Benefit Finder.exe
echo To send: zip the whole "dist\Benefit Finder" folder and share the zip.
endlocal
