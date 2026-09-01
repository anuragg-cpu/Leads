# Abhay Leads

A local, free-sources lead generation CRM - built for **Abhay**, and set
up so you can run the same tool for another product/company as a
separate **profile** with its own keywords and its own leads.

Runs entirely on your machine: it searches free/legal public sources for
people or companies who look like a good fit, scores them against
keywords you configure, and stores them in a local CRM you can browse in
a desktop window or from the command line.

**Where to start:**
1. `docs/SETUP_WINDOWS.md` - install and build `Leads.exe`
2. First run creates a profile automatically. Edit its keywords either
   from the GUI (**File -> Edit Config**) or by hand - `abhayleads
   profile list` shows you where each profile's `config.yaml` lives.
3. `docs/MARKETING_BASICS.md` - if you're new to this, read this first
4. `docs/SOURCES.md` - what each lead source does and how to set up the
   free ones that need a key/token
5. `docs/NOTIFICATIONS.md` - get a daily summary pushed to your iPhone
6. `docs/SERVER_SETUP.md` - run a 24/7 server so your phone and desktop
   share one set of leads, with full read/write from Safari

## Quick reference

```
abhayleads gui                     open the CRM window
abhayleads fetch                   search all enabled sources for new leads
abhayleads fetch --source reddit   search just one source
abhayleads list --due              leads due for follow-up
abhayleads show 42                 full detail for lead 42
abhayleads update 42 --stage Contacted --notes "sent intro email"
abhayleads update 42 --phone "+91 98765 43210" --email "x@y.com"
abhayleads stats                   pipeline summary
abhayleads dedupe                  merge osm_places leads that are the same place mapped twice
abhayleads reset                   delete ALL leads in the current profile to start over
abhayleads add --company "Acme" --contact-name "Jane" --phone "..."   add a lead by hand
abhayleads digest                  push a summary of what's new to your phone (docs/NOTIFICATIONS.md)
abhayleads server-token             generate a token for `serve`/`remote_server` (docs/SERVER_SETUP.md)
abhayleads serve                    run the HTTP server (JSON API + mobile web UI) for phone/desktop access
```

Running the built `Leads.exe` with no arguments opens the same CRM
window; any of the subcommands above work the same way, e.g.
`Leads.exe fetch`. Ctrl+C during `fetch` stops it early - whatever was
already found stays saved, same as clicking **Stop** in the GUI.

### Profiles - running this for more than one product

Each profile is a separate `config.yaml` + `leads.db`, so a second
product's keywords and leads never mix with Abhay's.

```
abhayleads profile list                    * marks the active one
abhayleads profile create "OtherCo"        new profile, starts from the template
abhayleads profile use "OtherCo"           switch which profile fetch/list/gui use
abhayleads --profile "OtherCo" fetch       run one command against a specific profile
abhayleads profile delete "OtherCo"        remove it from the list (keeps its files)
abhayleads profile delete "OtherCo" --delete-files   also delete its config.yaml/leads.db
```

The GUI has the same thing under the **Profile** menu, plus **File ->
Edit Config** to edit the active profile's `config.yaml` as raw text
without leaving the app (it validates the YAML before saving, so a typo
can't silently break your next fetch).

### Editing a lead

Double-click any row (or select it and press Enter, or right-click ->
Open/Edit Lead) to open its detail screen. Every field is editable -
company name, contact name, email, phone, URL, stage, follow-up date,
notes - since sources like OSM or Google News rarely come with a phone
number; you fill that in yourself once you've actually called or
visited the place.

Found a lead some other way entirely (a phone call, a referral, a
business card)? Click **Add Lead** in the toolbar (or `abhayleads add`
from the CLI) to enter it directly - it goes straight into the same
pipeline as everything else.

### Stopping a fetch early

Click **Stop** next to Find New Leads (enabled only while a fetch is
running) to end it early - whatever's already been found stays saved,
this just stops looking for more. It finishes whatever single network
request is in flight first, so it's not always instant.

### Accessing leads from your phone/desktop over the internet

By default everything lives in a local SQLite file. To share one set of
leads between your desktop and your phone (full read/write from Safari,
not just a daily digest), run `abhayleads serve` on a machine that's on
24/7 and point other installs at it with `remote_server.base_url`/
`remote_server.token` in their `config.yaml` - see
`docs/SERVER_SETUP.md` for the full walkthrough (TLS certificate,
keeping it running as a service, etc.). The desktop GUI window
(`abhayleads gui`) is local-only for now; use the CLI or the server's
own web UI for remote access.

## Project layout

```
abhayleads/          the application
  sources/            one file per lead source (add more here)
  gui/                PyQt6 desktop CRM
  server/              `abhayleads serve` - JSON API + mobile web UI (docs/SERVER_SETUP.md)
  db.py               SQLite storage
  remote_db.py         HTTP client with the same interface as db.py, for talking to `serve`
  profiles.py          multi-profile support (separate config.yaml + leads.db per product)
  scoring.py           keyword-based lead scoring
  fetcher.py           orchestrates a fetch run
  cli.py               command-line interface
config/config.example.yaml   template a new profile starts from
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
