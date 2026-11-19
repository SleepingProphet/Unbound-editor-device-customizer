#!/bin/bash
set -e

echo "Installing dependencies..."
.venv/bin/python -m pip install --require-hashes -r requirements.txt

echo ""
echo "Building..."
.venv/bin/python -m PyInstaller build.spec --clean

echo ""
echo "Signing .app bundle (ad-hoc)..."
codesign --force --deep --sign - dist/SpeedEditorCustomizer.app

echo ""
echo "Done. Output is at dist/SpeedEditorCustomizer.app"
echo "Run:  open dist/SpeedEditorCustomizer.app"
