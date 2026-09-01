# Getting updates on your iPhone

This app is a local Windows program with no server or cloud component,
so "automatic phone updates" needs an outside delivery channel. This
uses [ntfy](https://ntfy.sh) - free, no account/signup on either end,
and a notification is just one plain HTTP request.

By design, this sends **one digest a day**, not one push per lead - a
single fetch can find hundreds of leads (osm_places alone found 800+ in
early testing), and a phone buzzing hundreds of times would be worse
than useless. `abhayleads digest` summarizes everything that changed
since the last digest into one message: `"12 new leads, 3 updated, 2
due for follow-up."`

## Setup (about 5 minutes)

**1. Install the ntfy app on your iPhone**
App Store -> search "ntfy" -> the app by ntfy.sh -> Get. Free, no
account needed.

**2. Pick a topic name**
This is like a private channel name. Anyone who knows it can read your
notifications and post their own to it (ntfy.sh's default privacy model
is "obscurity," not authentication), so make it long and hard to guess -
not literally `abhayleads`. A reasonable pattern:
```
abhayleads-<yourname>-<random string>
```
e.g. `abhayleads-anurag-9x2kq7`. Anything works as long as it's not
guessable - there's no registration step, a topic just exists the
moment someone posts to or subscribes to it.

**3. Subscribe in the app**
Open ntfy on your phone -> "+" / Subscribe to topic -> paste your topic
name (server: leave it as `ntfy.sh`, the default) -> Subscribe.

**4. Tell Abhay Leads your topic name**
In the GUI: **File -> Edit Config**, add (or edit) this block, then Save:
```yaml
notifications:
  ntfy_topic: "abhayleads-anurag-9x2kq7"
```
(This is also already in `config/config.example.yaml` as a template -
`ntfy_base_url` only needs changing if you're self-hosting ntfy, see
below.)

**5. Test it**
```
dist\Leads\Leads.exe digest
```
or from a dev checkout: `venv\Scripts\python -m abhayleads digest`.
You should see a push notification on your phone within a few seconds.
If nothing shows up, double check the topic name matches exactly
(case-sensitive) in both the app and config.yaml.

## Making it actually automatic

`abhayleads digest` only *sends* when you run it - on its own, nothing
runs it daily. To make that automatic:
```
packaging\schedule_daily_digest.bat
```
Registers a Windows Task Scheduler job that runs `Leads.exe digest`
once a day (default 8am; pass a different time as an argument, e.g.
`packaging\schedule_daily_digest.bat 18:00`). Your PC needs to be on
(idle is fine) at that time.

This does **not** run a fetch - it only summarizes leads that already
exist in the database. Keep finding new ones yourself (click **Find New
Leads**, or `abhayleads fetch`) on whatever cadence works for you; the
digest just reports on whatever's accumulated since the last one,
whenever you ask it to.

To remove the scheduled task later: `schtasks /delete /tn "AbhayLeads Daily Digest" /f`

## Notes on privacy

ntfy.sh is a shared public service - your topic is only private as long
as its name stays secret, there's no password on the free tier. For a
personal lead-tracking summary that's a reasonable tradeoff, but if you
want real access control:
- Self-host ntfy (it's open source, a single small binary) and point
  `notifications.ntfy_base_url` at your own server.
- Or use [ntfy's paid tier](https://ntfy.sh/#pricing), which adds
  authentication.

Either way, only the summary counts are sent (e.g. "12 new leads") -
never lead names, contact details, or notes.
