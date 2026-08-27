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

This creates a `venv\` virtual environment and installs dependencies.

**Where your data lives depends on how you run it** - this trips people
up, so note it now:
- **Running from source** (`venv\Scripts\python -m abhayleads ...`,
  what step 3 below uses): profiles, config, and leads all live inside
  the repo folder itself, under `profiles\` (gitignored - never
  committed). Convenient for development since it's all in one place
  you can just look at.
- **Running the built `Leads.exe`** (step 4): profiles live under
  `%USERPROFILE%\AbhayLeads\profiles\` instead, so a rebuild (or
  deleting the repo folder) never touches your real data.

Either way, the very first time you run any command it auto-creates a
profile called "default" with a copy of `config/config.example.yaml` -
**that per-profile copy is what you actually edit**, not the template
in `config/` under the repo. Easiest way to edit it: **File -> Edit
Config** in the GUI, or find its path with `abhayleads profile list`.

## 3. Run it without building the .exe yet

```
venv\Scripts\python -m abhayleads gui
venv\Scripts\python -m abhayleads fetch
venv\Scripts\python -m abhayleads stats
```

This is the fastest loop while you're still tuning keywords - no
rebuild needed between changes. (Remember: this reads/writes
`<repo>\profiles\`, not `%USERPROFILE%\AbhayLeads\` - see above.)

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

Once built, all profile data (each profile's SQLite database and
config.yaml) lives in `%USERPROFILE%\AbhayLeads\profiles\`, not inside
the app folder, so rebuilding the .exe never touches your leads. Note
this is a **different location** than step 3's dev-mode run used (see
the note in step 2) - the exe starts with no profiles of its own the
first time, not whatever you built up while testing from source. To
carry your dev-mode profiles forward, copy `<repo>\profiles\` to
`%USERPROFILE%\AbhayLeads\profiles\`; otherwise just start fresh
(`Leads.exe profile create "Abhay"`).

## 5. Keeping it updated

After pulling code changes from the repo, just re-run
`packaging\build_exe.bat` (no need to re-run setup unless
`requirements.txt` changed).
