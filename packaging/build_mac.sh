#!/usr/bin/env bash
# Build the Benefit Finder Mac app and zip it for sending.
# Run from the repo root:  bash packaging/build_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

./.venv/bin/pip install -e ".[package]" >/dev/null

rm -rf build "dist/Benefit Finder.app" "dist/Benefit Finder-mac.zip"

./.venv/bin/pyinstaller packaging/benefit_finder.spec --noconfirm

# Zip the .app so it survives download and keeps its structure.
cd dist
ditto -c -k --sequesterRsrc --keepParent "Benefit Finder.app" "Benefit Finder-mac.zip"
cd ..

echo
echo "Built: dist/Benefit Finder.app"
echo "Send:  dist/Benefit Finder-mac.zip"
