@echo off
REM Registers a Windows Task Scheduler job that runs Leads.exe digest
REM once a day - pushes a summary of what's changed to your phone via
REM ntfy. Does NOT run a fetch; it only summarizes whatever leads
REM already exist. Keep finding new leads yourself (Find New Leads in
REM the GUI, or `abhayleads fetch`) - this just handles the daily
REM phone notification on its own schedule.
REM
REM Prerequisites: packaging\build_exe.bat already run, and
REM notifications.ntfy_topic set in your profile's config.yaml (see
REM docs/NOTIFICATIONS.md).
REM
REM Usage: packaging\schedule_daily_digest.bat [HH:MM]   (default 08:00)

set DIGEST_TIME=%1
if "%DIGEST_TIME%"=="" set DIGEST_TIME=08:00

if not exist "%~dp0..\dist\Leads\Leads.exe" (
    echo dist\Leads\Leads.exe not found - run packaging\build_exe.bat first.
    exit /b 1
)

schtasks /create /tn "AbhayLeads Daily Digest" /tr "\"%~dp0..\dist\Leads\Leads.exe\" digest" /sc daily /st %DIGEST_TIME% /f

echo.
echo Scheduled "AbhayLeads Daily Digest" to run daily at %DIGEST_TIME%.
echo Your PC needs to be on (even just idle) at that time for it to fire.
echo.
echo To change the time later:
echo   schtasks /change /tn "AbhayLeads Daily Digest" /st HH:MM
echo To remove it:
echo   schtasks /delete /tn "AbhayLeads Daily Digest" /f
echo To test it right now instead of waiting:
echo   dist\Leads\Leads.exe digest
