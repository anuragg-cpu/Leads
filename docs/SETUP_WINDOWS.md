# Setup on Windows

This session (Claude Code on the web) runs on Linux, so it can build and
test the Python app, but it **cannot produce a real Windows .exe** -
that has to be built on your own Windows machine. These are the exact
steps.

## 1. Prerequisites

- Windows 10/11
- Python 3.10+ installed from https://python.org (check "Add python.exe
  to PATH" during install)
- This repo, cloned or downloaded, on your machine

## 2. First-time setup

Open a terminal (PowerShell or cmd) in the repo folder and run:

```
packaging\setup_windows.bat
```

This creates a `venv\` virtual environment, installs dependencies, and
copies `config/config.example.yaml` to `%USERPROFILE%\AbhayLeads\config\config.yaml`
- **that's the file you actually edit** with Abhay's keywords once you
have them (the one in `config/` under the repo is just the template).

## 3. Run it without building the .exe yet

```
venv\Scripts\python -m abhayleads gui
venv\Scripts\python -m abhayleads fetch
venv\Scripts\python -m abhayleads stats
```

This is the fastest loop while you're still tuning keywords - no
rebuild needed between changes.

## 4. Build Leads.exe

Once it's working the way you want:

```
packaging\build_exe.bat
```

Output: `dist\Leads\Leads.exe`. Double-click it to open the CRM window
(same as `abhayleads gui`), or run it from a terminal with subcommands:

```
dist\Leads\Leads.exe fetch
dist\Leads\Leads.exe list --due
dist\Leads\Leads.exe stats
```

You can copy the whole `dist\Leads\` folder anywhere (e.g. pin
`Leads.exe` to your taskbar/Start menu) - it's self-contained and
doesn't need Python installed on a machine you move it to.

Data (the SQLite database and your config.yaml) always lives in
`%USERPROFILE%\AbhayLeads\`, not inside the app folder, so rebuilding
the .exe never touches your leads.

## 5. Keeping it updated

After pulling code changes from the repo, just re-run
`packaging\build_exe.bat` (no need to re-run setup unless
`requirements.txt` changed).
