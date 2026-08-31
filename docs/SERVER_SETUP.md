# Server setup - access Abhay Leads from your phone and desktop, both talking to one shared database

`abhayleads serve` runs the same app as a small HTTP server: a JSON API
(so your desktop CLI/app can talk to it instead of a local file) plus a
mobile-friendly web page (so you can browse and edit leads straight from
Safari on your iPhone). Both read/write the same SQLite database, so a
lead you edit on your phone shows up on your desktop and vice versa.

This is meant to run on a machine that's on 24/7 - your office Windows
Server - reachable from the internet via your domain
(`chipiotembedded.com`), with a real TLS certificate. This session ran
on Linux and can't test against your actual server, domain, or router,
so everything below was verified locally (a local `abhayleads serve`,
the JSON API, the web UI, and the remote client all work end-to-end -
see the test suite) but the deployment steps themselves need you to run
them and report back if anything doesn't match what's described here.

## What you'll end up with

- `https://leads.chipiotembedded.com` (or whatever subdomain you pick) -
  open it on your iPhone, log in once with a token, browse/edit leads
  from anywhere.
- Your desktop app/CLI pointed at the same URL instead of a local file,
  so it shows the same leads as your phone.
- The server keeps running fetches and holding your data even when your
  desktop is off, as long as the Windows Server itself is on.

## Prerequisites

- The Windows Server machine, with admin access
- Access to your domain's DNS settings (wherever `chipiotembedded.com`
  is registered/managed)
- Access to your office router/firewall, to forward one port
- This repo on the server (same as `docs/SETUP_WINDOWS.md` steps 1-2)

## 1. Install and generate an access token

On the server, same as any other machine:
```
packaging\setup_windows.bat
```

Then generate a random token - this is the one secret that both your
phone and your desktop will use to prove they're allowed in (there's no
separate username/password system, just this one shared token):
```
venv\Scripts\python -m abhayleads server-token
```
Copy the long random string it prints. Keep it private - anyone with
this token and your URL can read and edit your leads.

## 2. Add the token to the server's config

Find the server's profile config (`venv\Scripts\python -m abhayleads
profile list` shows the path, or **File -> Edit Config** if you're
running the GUI there too) and add:
```yaml
server:
  token: "paste-the-token-from-step-1-here"
  host: "0.0.0.0"
  port: 8443
```
`host: 0.0.0.0` means "listen on every network interface", which is
what you want for a machine other devices connect to.

## 3. Point a DNS record at your server

In your domain's DNS settings, add an **A record** for a subdomain
pointing at your office's public IP address (not the server's local
192.168.x.x/10.x.x.x address - the address your router shows the
internet):
```
leads.chipiotembedded.com   A   <your office's public IP>
```
(A subdomain, not the bare domain, so this doesn't collide with
anything already running on `www.chipiotembedded.com`.) If your office
internet's public IP isn't static, ask your ISP whether it is, or use a
dynamic-DNS service that updates this record automatically when it
changes - otherwise this breaks whenever your IP does.

DNS changes can take a few minutes to a few hours to propagate. You can
check with `nslookup leads.chipiotembedded.com` from any machine once
you're ready to test.

## 4. Forward port 443 on your router

In your office router/firewall admin page, forward external port `443`
(HTTPS) to the Windows Server's local IP address, port `8443` (or
whatever you set `server.port` to in step 2 - matching ports on both
ends is simpler, so consider just using `443` for `server.port` too and
skip the translation). This is what lets a request from your phone,
wherever it is, actually reach the server sitting in your office.

## 5. Get a free TLS certificate with win-acme

A real HTTPS certificate is required - the login cookie is marked
"Secure," meaning browsers refuse to send it over plain HTTP, and
without HTTPS your token would travel in plain text anyway.
[win-acme](https://www.win-acme.com/) is a free, official-feeling
Let's Encrypt client built for Windows, no IIS required.

1. Download the latest `win-acme.v2...trimmed.zip` from
   https://www.win-acme.com/, unzip it somewhere on the server (e.g.
   `C:\win-acme\`).
2. Temporarily forward port **80** (HTTP) on your router to the server
   too, same target IP - win-acme's default validation method needs it
   briefly to prove you control the domain. (You can remove this
   forwarding again afterward if you don't want port 80 open
   permanently; renewal will need it again every ~60 days unless you
   switch win-acme to DNS validation instead.)
3. Run `wacs.exe` as Administrator, choose the simple/default option,
   and enter `leads.chipiotembedded.com` when it asks for the
   hostname. Let it create a new certificate.
4. win-acme saves the certificate files somewhere like
   `C:\ProgramData\win-acme\...\` and prints the exact paths for the
   `.pfx`/`.pem`/key files - note the certificate file and private key
   file paths (uvicorn wants a cert file and a key file separately; if
   win-acme only gives you a `.pfx`, use its "PEM files" export option,
   or `openssl pkcs12 -in cert.pfx -out cert.pem -nokeys` /
   `-out key.pem -nocerts -nodes` to split it).
5. win-acme registers a scheduled task to auto-renew before the
   certificate expires - leave that in place.

## 6. Run the server

```
venv\Scripts\python -m abhayleads serve --cert "C:\path\to\cert.pem" --key "C:\path\to\key.pem"
```
You should see `Serving ... on https://0.0.0.0:8443`. From another
device on the internet, open `https://leads.chipiotembedded.com` (or
`:8443` on the end if you didn't map 443->8443 in step 4) - you should
land on a login page. Log in with the token from step 1. Leave this
running for now and confirm it works from your phone before moving on
to making it permanent.

## 7. Keep it running 24/7

Ctrl+C in step 6 stops the server the moment you close that terminal.
To survive reboots and logouts, run it as a proper Windows service with
[NSSM](https://nssm.cc/) (free, a single .exe, no install):

1. Download NSSM, unzip it, open an admin terminal in that folder.
2. `nssm.exe install AbhayLeadsServer`
3. In the dialog: **Path** = full path to
   `<repo>\venv\Scripts\python.exe`; **Arguments** = `-m abhayleads
   serve --cert "C:\path\to\cert.pem" --key "C:\path\to\key.pem"`;
   **Startup directory** = the repo folder. Install service.
4. `nssm.exe start AbhayLeadsServer`

It now starts automatically on boot and restarts if it crashes. Check
on it any time with `nssm.exe status AbhayLeadsServer`, or `nssm.exe
stop`/`restart AbhayLeadsServer`. If win-acme renews the certificate to
a new file location, update the service's arguments
(`nssm.exe edit AbhayLeadsServer`) and restart it - a renewal in place
at the *same* file path needs nothing further, since the service
reads the cert file fresh each time it starts, not continuously.

(If you'd rather not install NSSM, a Windows Task Scheduler task set to
"run at startup" with the same `python.exe` path/arguments works too,
just without automatic crash-restart.)

## 8. Point your desktop app at the server

On your desktop machine (not the server), edit that profile's
`config.yaml` and add:
```yaml
remote_server:
  base_url: "https://leads.chipiotembedded.com"
  token: "the-same-token-from-step-1"
```
Once this is set, every `abhayleads` CLI command on that machine
(`fetch`, `list`, `show`, `update`, `digest`, etc.) talks to the server
instead of a local database file - so your desktop and phone are always
looking at the exact same leads. Leave `remote_server.base_url` blank
(the default) on any profile that should keep using its own local file
instead.

Note: this pass wires remote-server support into the CLI and the web
UI. The **desktop GUI window** (`abhayleads gui`) still only reads a
local database file - it doesn't yet talk to a remote server. Use the
web UI (step 6's URL, works fine on a desktop browser too) or the CLI
for remote access until that's added.

## 9. Use it from your iPhone

Open `https://leads.chipiotembedded.com` in Safari, log in with the
token once (Safari will offer to remember it / you can add the page to
your home screen for one-tap access). From there you can browse, add,
and edit leads, kick off a fetch, and view stats - full read/write, no
app install needed.

## Notes on security

- The token is the only thing standing between the internet and your
  leads - treat it like a password. Don't put it in a shared doc or
  message it over an insecure channel.
- Everything is over HTTPS only - `serve` without `--cert`/`--key`
  refuses to bind to anything but plain HTTP, which this doc never
  recommends exposing past your own machine/LAN.
- This is a single shared token, not per-person accounts - fine for one
  person (or a small team who all trust each other) accessing their own
  leads; it is not built for giving different people different levels
  of access.
- If the token ever leaks, run `abhayleads server-token` again, update
  `server.token` on the server and `remote_server.token` everywhere
  else, and restart the service.
