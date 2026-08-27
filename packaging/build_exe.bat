@echo off
REM Builds dist\Leads\Leads.exe. Run packaging\setup_windows.bat first.
REM Run this from the repo root: packaging\build_exe.bat

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo venv not found - run packaging\setup_windows.bat first.
    exit /b 1
)

pyinstaller --noconfirm packaging\Leads.spec

echo.
echo Build complete: dist\Leads\Leads.exe
echo Double-click it to open the CRM, or from a terminal run e.g.:
echo   dist\Leads\Leads.exe fetch
echo   dist\Leads\Leads.exe stats
