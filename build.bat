@echo off
echo Installing dependencies...
.venv\Scripts\python -m pip install --require-hashes -r requirements.txt

echo.
echo Building...
.venv\Scripts\python -m PyInstaller build.spec --clean

echo.
echo Done. Output is in dist\SpeedEditorCustomizer\
echo Run dist\SpeedEditorCustomizer\SpeedEditorCustomizer.exe to test.
pause
