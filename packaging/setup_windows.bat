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

if not exist "%USERPROFILE%\AbhayLeads\config" mkdir "%USERPROFILE%\AbhayLeads\config"
if not exist "%USERPROFILE%\AbhayLeads\config\config.yaml" (
    copy config\config.example.yaml "%USERPROFILE%\AbhayLeads\config\config.yaml"
    echo Created %USERPROFILE%\AbhayLeads\config\config.yaml - edit this to add your keywords.
)

echo.
echo Setup complete. Next steps:
echo   1. Edit %USERPROFILE%\AbhayLeads\config\config.yaml
echo   2. Run:  venv\Scripts\python -m abhayleads gui
echo   3. When ready to build the .exe:  packaging\build_exe.bat
