# Server setup - host Abhay Leads online at leads.chipiotembedded.com

`abhayleads serve` runs the same app as a small HTTP server: a JSON API
(so your desktop CLI/app can talk to it instead of a local file) plus a
mobile-friendly web page (so you can browse, add, and edit leads straight
from Safari on your iPhone, or any browser). Both read/write the same
SQLite database, so a lead you edit on your phone shows up on your
desktop and vice versa.

This runs on a machine that's on 24/7 - your office Windows Server -
reachable from the internet at `https://leads.chipiotembedded.com`, with
a real TLS certificate. This session ran on Linux and can't test against
your actual server, domain, or router, so everything below was verified
locally (a local `abhayleads serve`, the JSON API, the web UI, and the
remote client all work end-to-end - see the test suite) but the
deployment steps themselves need you to run them and report back if
anything doesn't match what's described here.

## What you'll end up with

- `https://leads.chipiotembedded.com` fully live on the internet - open
  it on your iPhone (or any browser, anywhere), log in once with a
  token, browse/add/edit leads, kick off fetches, all from that one URL.
- Your desktop app/CLI pointed at the same URL instead of a local file,
  so it shows the same leads as your phone.
- The server keeps running and holding your data even when your desktop
  is off, as long as the Windows Server itself is on - a real always-on
  deployment, not a tunnel or a temporary link.

## Two ways to get HTTPS - pick one

Browsers refuse to send the login cookie over plain HTTP (it's marked
"Secure"), so a real certificate for `leads.chipiotembedded.com` is
required either way. Two ways to get there:

- **Path A - Caddy reverse proxy (recommended).**
  [Caddy](https://caddyserver.com) is a free web server that gets and
  renews your certificate automatically, forever, with no manual steps
  after initial setup - no PFX conversion, no remembering to update a
  service's arguments when a cert renews. `abhayleads serve` itself
  never touches TLS or the internet directly; it only listens on
  `127.0.0.1`, and Caddy sits in front of it on port 443. This is the
  path below.
- **Path B - win-acme, no reverse proxy.** `abhayleads serve` terminates
  TLS itself using a certificate you generate with win-acme and renew
  by hand (or via win-acme's own scheduled task) every ~60-90 days. One
  fewer moving part to install, more manual upkeep. Covered at the
  bottom of this doc if you'd rather avoid running a second process.

## Prerequisites

- The Windows Server machine, with admin access
- Access to your domain's DNS settings (wherever `chipiotembedded.com`
  is registered/managed)
- Access to your office router/firewall, to forward ports
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
  host: "127.0.0.1"
  port: 8443
```
`host: 127.0.0.1` (loopback-only) is deliberate for the Caddy path -
`abhayleads serve` itself is never directly reachable from the internet,
only Caddy is, which then forwards requests to it locally. (Path B at
the bottom uses `0.0.0.0` instead, since there's no proxy in front of it
there.)

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

## 4. Forward ports 80 and 443 on your router

In your office router/firewall admin page, forward external ports `80`
and `443` to the Windows Server's local IP address, same ports. Caddy
needs both: `80` briefly to prove to Let's Encrypt that you control the
domain (and to redirect any stray plain-HTTP visitors to HTTPS), `443`
for the actual site. This is what lets a request from your phone,
wherever it is, actually reach the server sitting in your office.

## 5. Install Caddy and point it at leads.chipiotembedded.com

1. Download the Windows zip from https://caddyserver.com/download
   (no extra options needed), and unzip it to e.g. `C:\caddy\` so you
   have `C:\caddy\caddy.exe`.
2. In that same folder, create a file named `Caddyfile` (no extension)
   with this content - a ready-to-copy version of this also lives in
   the repo at `packaging\Caddyfile.example`:
   ```
   leads.chipiotembedded.com {
       reverse_proxy 127.0.0.1:8443
   }
   ```
   That's the entire config. Caddy reads "there's a domain name here"
   and automatically requests, installs, and renews a Let's Encrypt
   certificate for it - nothing else to configure.
3. Quick test run: `C:\caddy\caddy.exe run --config C:\caddy\Caddyfile`
   (leave it running in this terminal for now). The first time it talks
   to Let's Encrypt it needs port 80 reachable (step 4) - if that's not
   forwarded yet, it'll fail to get a certificate.

## 6. Run the server

In a separate terminal:
```
venv\Scripts\python -m abhayleads serve
```
No `--cert`/`--key` needed here - Caddy is handling TLS, this only
needs to answer on `127.0.0.1:8443` per step 2's config, which is the
default `serve` prints. From another device on the internet, open
`https://leads.chipiotembedded.com` - you should land on a login page,
with a padlock in the address bar (Caddy's certificate). Log in with the
token from step 1. Leave both processes running for now and confirm it
works from your phone before moving on to making them permanent.

## 7. Keep both running 24/7

Closing either terminal stops that process. To survive reboots and
logouts, run both as Windows services with [NSSM](https://nssm.cc/)
(free, a single .exe, no install):

```
nssm.exe install AbhayLeadsServer
```
**Path** = full path to `<repo>\venv\Scripts\python.exe`; **Arguments**
= `-m abhayleads serve`; **Startup directory** = the repo folder.

```
nssm.exe install AbhayLeadsCaddy
```
**Path** = `C:\caddy\caddy.exe`; **Arguments** = `run --config
C:\caddy\Caddyfile`; **Startup directory** = `C:\caddy`.

Then `nssm.exe start AbhayLeadsServer` and `nssm.exe start
AbhayLeadsCaddy`. Both now start automatically on boot and restart if
they crash - and Caddy renews the certificate on its own from here on,
nothing to maintain. Check on them any time with `nssm.exe status
AbhayLeadsServer` / `AbhayLeadsCaddy`.

(If you'd rather not install NSSM, two Windows Task Scheduler tasks set
to "run at startup" with the same paths/arguments work too, just
without automatic crash-restart.)

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
app install needed, from wherever you have signal, not just at the
office.

## Notes on security

- The token is the only thing standing between the internet and your
  leads - treat it like a password. Don't put it in a shared doc or
  message it over an insecure channel.
- Everything is over HTTPS only. `abhayleads serve` itself refuses to
  bind to anything but plain HTTP without `--cert`/`--key` - that's
  fine and expected on the Caddy path above since Caddy is the only
  thing actually facing the internet (on `127.0.0.1`, `serve` is
  unreachable from outside anyway); never bind `serve` to `0.0.0.0`
  without either `--cert`/`--key` or a TLS-terminating proxy in front.
- This is a single shared token, not per-person accounts - fine for one
  person (or a small team who all trust each other) accessing their own
  leads; it is not built for giving different people different levels
  of access.
- If the token ever leaks, run `abhayleads server-token` again, update
  `server.token` on the server and `remote_server.token` everywhere
  else, and restart the `AbhayLeadsServer` service.

---

## Path B - win-acme, no reverse proxy

If you'd rather run one process instead of two, `abhayleads serve` can
terminate TLS itself. Do steps 1, 3-4 above (using `0.0.0.0` instead of
`127.0.0.1` for `server.host` in step 2, and forwarding just port 443,
plus 80 temporarily below), then:

1. Download the latest `win-acme.v2...trimmed.zip` from
   https://www.win-acme.com/, unzip it somewhere on the server (e.g.
   `C:\win-acme\`).
2. Temporarily forward port **80** (HTTP) on your router to the server
   too, same target IP - win-acme's default validation method needs it
   briefly to prove you control the domain. (Renewal will need it again
   every ~60 days unless you switch win-acme to DNS validation.)
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
6. Run it: `venv\Scripts\python -m abhayleads serve --cert
   "C:\path\to\cert.pem" --key "C:\path\to\key.pem"`. You should see
   `Serving ... on https://0.0.0.0:443`.
7. For 24/7, `nssm.exe install AbhayLeadsServer` as in step 7 above, but
   with `-m abhayleads serve --cert "..." --key "..."` as the
   Arguments. If win-acme renews the certificate to a new file path,
   update the service's arguments (`nssm.exe edit AbhayLeadsServer`)
   and restart it - a renewal in place at the *same* path needs nothing
   further, since the service reads the cert file fresh each time it
   starts, not continuously.

Steps 8-9 (pointing your desktop app at the server, using it from your
iPhone) are identical either way.
