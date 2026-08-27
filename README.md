# Abhay Leads

A local, free-sources lead generation CRM for **Abhay**.

Runs entirely on your machine: it searches free/legal public sources for
people or companies who look like a good fit, scores them against
keywords you configure, and stores them in a local CRM you can browse in
a desktop window or from the command line.

**Where to start:**
1. `docs/SETUP_WINDOWS.md` - install and build `Leads.exe`
2. Edit `%USERPROFILE%\AbhayLeads\config\config.yaml` with Abhay's
   keywords once you have them (template: `config/config.example.yaml`)
3. `docs/MARKETING_BASICS.md` - if you're new to this, read this first
4. `docs/SOURCES.md` - what each lead source does and how to set up the
   free ones that need a key/token

## Quick reference

```
abhayleads gui                     open the CRM window
abhayleads fetch                   search all enabled sources for new leads
abhayleads fetch --source reddit   search just one source
abhayleads list --due              leads due for follow-up
abhayleads update 42 --stage Contacted --notes "sent intro email"
abhayleads stats                   pipeline summary
abhayleads dedupe                  merge osm_places leads that are the same place mapped twice
```

Running the built `Leads.exe` with no arguments opens the same CRM
window; any of the subcommands above work the same way, e.g.
`Leads.exe fetch`.

## Project layout

```
abhayleads/          the application
  sources/            one file per lead source (add more here)
  gui/                PyQt6 desktop CRM
  db.py               SQLite storage
  scoring.py           keyword-based lead scoring
  fetcher.py           orchestrates a fetch run
  cli.py               command-line interface
config/config.example.yaml   config template (copy to config.yaml, don't edit this one)
docs/                  setup + marketing-basics guides
packaging/              Windows setup/build scripts + PyInstaller spec
tests/
```

## Running from source (any OS, for development)

```
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m abhayleads gui
python -m abhayleads fetch
```

Building the actual `.exe` requires Windows - see `docs/SETUP_WINDOWS.md`.
