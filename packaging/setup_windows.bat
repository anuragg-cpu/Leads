@echo off
REM One-time setup: creates a virtual environment and installs dependencies.
REM Run this from the repo root: packaging\setup_windows.bat

python -m venv venv
if errorlevel 1 (
    echo Could not create a virtual environment. Is Python 3.10+ installed and on PATH?
    exit /b 1
)

call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete. Next steps:
echo   1. Run:  venv\Scripts\python -m abhayleads gui
echo      (first run auto-creates a "default" profile from config\config.example.yaml)
echo   2. Edit its keywords: File -^> Edit Config in the GUI, or `abhayleads profile list`
echo      shows you the file path to edit by hand instead.
echo   3. When ready to build the .exe:  packaging\build_exe.bat
