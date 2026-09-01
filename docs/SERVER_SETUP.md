# Server setup - host Abhay Leads online, reachable from your phone

`abhayleads serve` runs the same app as a small HTTP server: a JSON API
(so your desktop CLI/app can talk to it instead of a local file) plus a
mobile-friendly web page (so you can browse, add, and edit leads straight
from Safari on your iPhone, or any browser). Both read/write the same
SQLite database, so a lead you edit on your phone shows up on your
desktop and vice versa.

This runs on a machine that's on 24/7 - your office Windows Server -
reachable from the internet with a real TLS certificate. Most of this
doc uses `https://leads.chipiotembedded.com` as the example URL (Paths
A-C, which put the site on your own domain), but if you can't get
router/ISP access and don't want to touch your domain's DNS or pay for
anything, **Path D** gets you online for free with a
Tailscale-provided URL instead (e.g. `https://yourname.tailxxxx.ts.net`)
- see the "Which path" note just below. This session ran on Linux and
can't test against your actual server, domain, or router, so everything
below was verified locally (a local `abhayleads serve`, the JSON API,
the web UI, and the remote client all work end-to-end - see the test
suite) but the deployment steps themselves need you to run them and
report back if anything doesn't match what's described here.

## What you'll end up with

- A real HTTPS URL fully live on the internet - open it on your iPhone
  (or any browser, anywhere), log in once with a token, browse/add/edit
  leads, kick off fetches, all from that one URL.
- Your desktop app/CLI pointed at the same URL instead of a local file,
  so it shows the same leads as your phone.
- The server keeps running and holding your data even when your desktop
  is off, as long as the Windows Server itself is on - a real always-on
  deployment, not a tunnel or a temporary link.

## Four ways to get HTTPS - pick one

Browsers refuse to send the login cookie over plain HTTP (it's marked
"Secure"), so a real certificate is required either way. Which path
fits depends on what you have access to:

- **Path A - Caddy reverse proxy (recommended if you have router
  access).** [Caddy](https://caddyserver.com) is a free web server that
  gets and renews your certificate automatically, forever, with no
  manual steps after initial setup - no PFX conversion, no remembering
  to update a service's arguments when a cert renews. `abhayleads
  serve` itself never touches TLS or the internet directly; it only
  listens on `127.0.0.1`, and Caddy sits in front of it on port 443.
  Needs ports 80/443 forwarded on your router, and your own domain (or
  a subdomain) pointed at your public IP. This is the path below.
- **Path B - win-acme, no reverse proxy.** `abhayleads serve` terminates
  TLS itself using a certificate you generate with win-acme and renew
  by hand (or via win-acme's own scheduled task) every ~60-90 days. One
  fewer moving part to install, more manual upkeep. Also needs router
  port forwarding. Covered further down this doc.
- **Path C - Cloudflare Tunnel.** No router/ISP access needed, but
  requires moving your domain's DNS to Cloudflare (the whole domain,
  not just a subdomain - Cloudflare doesn't support delegating just a
  subdomain through its normal signup flow), which is a bigger, more
  disruptive change if your domain already hosts a live site or email.
  Covered further down this doc.
- **Path D - Tailscale Funnel (free, no router/ISP/DNS changes at
  all).** If you can't get router/ISP access, don't want to touch your
  domain's DNS at all (e.g. it stays on Squarespace, untouched), and
  don't want to pay for anything, this is the one that asks nothing of
  you except installing one free program. The trade-off: your URL is
  Tailscale's, not your own domain, e.g.
  `https://yourname.tailxxxx.ts.net` instead of
  `leads.chipiotembedded.com`. Covered at the very bottom of this doc.

## Prerequisites

- The Windows Server machine, with admin access
- Access to your domain's DNS settings (wherever `chipiotembedded.com`
  is registered/managed) - e.g. Squarespace, see the note under step 3
- Access to your office router/firewall, to forward ports
- Git and this repo on the server - step 0 below

## 0. Get Git and the code onto the server

If `git --version` in a terminal already prints a version, skip to
step 1 - you have this already.

1. Download the installer from https://git-scm.com/download/win, run
   it, keep all the default options. Close and reopen your terminal
   afterward so it picks up the new PATH.
2. The server-mode code in this doc lives on a branch that hasn't been
   merged to `main` yet, so check it out explicitly:
   ```
   cd C:\
   git clone https://github.com/anuragg-cpu/Leads.git AbhayLeads
   cd AbhayLeads
   git checkout claude/abhay-lead-generation-script-f6ktnu
   ```
   (Once that branch is merged, a plain `git clone` with no
   `checkout` will get you the server code directly - ask if you want
   that merged.) Every command from here on assumes you're inside this
   `C:\AbhayLeads` folder.

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
anything already running on `www.chipiotembedded.com`.)

DNS changes can take a few minutes to a few hours to propagate. You can
check with `nslookup leads.chipiotembedded.com` from any machine once
you're ready to test.

### If nslookup times out but your browser works fine

This is a common Windows quirk, not a sign anything's actually broken:
`nslookup` bypasses the normal OS DNS resolver and queries whatever
server is configured directly over raw UDP port 53 - if that
particular server (often an IPv6 one your ISP handed out, e.g.
`2001:....`) isn't actually reachable, `nslookup` hangs and times out
even though every other program (browser, `ping <hostname>`, git,
Caddy, PowerShell) uses the real OS resolver and works fine.

Confirm with `ping <hostname>` instead (not an IP) - if the very first
line shows a resolved address (`Pinging google.com [142.250...]`), DNS
itself is fine even if the ping replies after that say "timed out"
(that's just ICMP being blocked, unrelated to DNS). If `ping
google.com` resolves but shows an IPv6 address and then "Destination
host unreachable," your network has a non-working IPv6 path - the fix
is to disable IPv6 on the active adapter (`ncpa.cpl` -> right-click the
adapter -> Properties -> uncheck "Internet Protocol Version 6") so
everything falls back to IPv4, which is what's actually working.
Once that's done, `nslookup` should also stop timing out. Either way,
if `ping <hostname>` and your browser both work, you can trust that
DNS is fine for the actual deployment even if `nslookup` alone still
misbehaves - or just target it at a known-good server directly to
sidestep the issue: `nslookup leads.chipiotembedded.com 8.8.8.8`.

### If your office's public IP isn't static

Most office/business internet connections change IP occasionally (a
router reboot, an ISP-side change) - if that happens, the plain A
record above goes stale and `leads.chipiotembedded.com` stops
resolving to your server until you notice and fix it by hand. Check
first: visit https://whatismyip.com now and again in a day or two - if
it's identical, ask your ISP whether your IP is static/"sticky" (many
business plans are, sometimes for a small fee); if so, skip this
section entirely and use the plain A record above.

If it does change, use [DuckDNS](https://www.duckdns.org) (free, no
account beyond signing in with GitHub/Google, no periodic
manual reconfirmation) to keep a hostname pointed at your current IP
automatically, then point `leads.chipiotembedded.com` at *that*
hostname instead of a fixed IP:

1. Go to https://www.duckdns.org and sign in (GitHub/Google/etc).
2. Under "domains", type a subdomain you want (e.g. `chipiot-office`)
   and click **add domain** - you get `chipiot-office.duckdns.org`.
   Copy the **token** shown at the top of the page (a UUID) - this
   authenticates updates as coming from you.
3. In `chipiotembedded.com`'s DNS settings, add a **CNAME** instead of
   the A record above:
   ```
   leads.chipiotembedded.com   CNAME   chipiot-office.duckdns.org
   ```
   On Squarespace (Settings -> Domains -> chipiotembedded.com -> DNS
   Settings -> Custom Records): click **Add Record**, not "Add
   Preset" - presets are prebuilt bundles for specific known services
   (Google Workspace, etc.), not a general-purpose custom record.
   Type `CNAME`, Host `leads` (Squarespace appends the base domain
   itself, so just `leads`, not the full `leads.chipiotembedded.com`),
   Data `chipiot-office.duckdns.org`, default TTL.
   Set this once - from here on, whenever DuckDNS's record changes,
   `leads.chipiotembedded.com` automatically follows it.
4. On the Windows Server, save this as `C:\caddy\duckdns-update.ps1`
   (swap in your own subdomain and token from step 2):
   ```powershell
   Invoke-RestMethod -Uri "https://www.duckdns.org/update?domains=chipiot-office&token=YOUR-TOKEN-HERE&ip="
   ```
   Leaving `ip=` empty is deliberate - DuckDNS reads the public IP the
   request itself arrived from, which is exactly the address you want
   published, so there's nothing to detect or fill in yourself.
5. Run it once by hand to confirm it works:
   ```
   powershell -ExecutionPolicy Bypass -File C:\caddy\duckdns-update.ps1
   ```
   It should print `OK`. Check https://www.duckdns.org - your
   domain's current IP should now be filled in.
6. Register it to run every 5 minutes so it keeps up automatically:
   ```
   schtasks /create /tn "DuckDNS Update" /tr "powershell.exe -ExecutionPolicy Bypass -File C:\caddy\duckdns-update.ps1" /sc minute /mo 5 /ru SYSTEM
   ```

Verify with `nslookup chipiot-office.duckdns.org` and `nslookup
leads.chipiotembedded.com` - both should resolve to your current
public IP.

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

---

## Path C - Cloudflare Tunnel (no router/ISP access needed)

If you can't get into your router's admin page and can't get your ISP
to forward ports either (some ISP-supplied boxes are locked down with
no local admin panel at all, managed only by the ISP remotely), this
path skips port forwarding entirely. Instead of your server accepting
inbound internet connections, a small program (`cloudflared`) makes an
*outbound* connection to Cloudflare, which relays public traffic back
through that tunnel - no open ports, no router changes, no ISP call.
Cloudflare also issues and renews the HTTPS certificate automatically,
so this replaces Caddy too.

This only delegates the `leads` subdomain to Cloudflare - your existing
`www.chipiotembedded.com` site and any email on that domain stay
entirely on Squarespace, untouched.

Do steps 0-2 above (get the code, install, generate/set the token -
`server.host` stays `127.0.0.1` same as the Caddy path, since
`cloudflared` connects to it locally same as Caddy would have), then:

1. Sign up free at https://dash.cloudflare.com/sign-up.
2. In the Cloudflare dashboard, **Add a Site** and type the full
   subdomain `leads.chipiotembedded.com` (not just the bare domain).
   Pick the Free plan. Cloudflare shows two nameservers, e.g.
   `bob.ns.cloudflare.com` / `kate.ns.cloudflare.com` (yours will
   differ) - note them.
3. In Squarespace (Settings -> Domains -> chipiotembedded.com -> DNS
   Settings -> Custom Records), add two **NS** records delegating just
   this subdomain: Host `leads`, Data = each Cloudflare nameserver from
   step 2 (one record per nameserver). If you already added a CNAME
   for `leads` pointing at a DuckDNS hostname earlier, remove it first
   - it would conflict with this delegation, and you no longer need
   DuckDNS at all with this path (Cloudflare Tunnel doesn't care what
   your public IP is, or whether it changes).
4. Back in Cloudflare, click **Check nameservers** on that site - once
   it shows "Active" (can take a few minutes to a few hours), continue.
5. On the server, download `cloudflared-windows-amd64.exe` from
   https://github.com/cloudflare/cloudflared/releases/latest, rename it
   to `cloudflared.exe`, put it in `C:\cloudflared\`.
6. Authenticate and create a tunnel:
   ```
   cd C:\cloudflared
   cloudflared.exe tunnel login
   ```
   Opens a browser to authorize against your Cloudflare account - pick
   the `leads.chipiotembedded.com` zone when prompted.
   ```
   cloudflared.exe tunnel create abhayleads
   ```
   Note the tunnel ID and the credentials file path it prints (looks
   like `C:\Users\<you>\.cloudflared\<tunnel-id>.json`).
7. Route the subdomain to this tunnel:
   ```
   cloudflared.exe tunnel route dns abhayleads leads.chipiotembedded.com
   ```
8. Create `C:\cloudflared\config.yml`:
   ```yaml
   tunnel: abhayleads
   credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json
   ingress:
     - hostname: leads.chipiotembedded.com
       service: http://127.0.0.1:8443
     - service: http_status:404
   ```
   (swap in the real credentials-file path from step 6)
9. Test it - in one terminal: `cloudflared.exe tunnel run abhayleads`;
   in another: `venv\Scripts\python -m abhayleads serve` (no
   `--cert`/`--key` needed - Cloudflare handles HTTPS at their edge,
   same reasoning as the Caddy path). Visit
   `https://leads.chipiotembedded.com` from your phone.
10. Make both permanent:
    ```
    cloudflared.exe service install
    ```
    installs `cloudflared` itself as a Windows service using
    `config.yml`. For `abhayleads serve`, use `nssm.exe install
    AbhayLeadsServer` exactly as in step 7 of the Caddy path above.

Steps 8-9 from the top of this doc (pointing your desktop app at the
server, using it from your iPhone) are identical either way.

---

## Path D - Tailscale Funnel (free, no router/ISP/DNS changes at all)

Use this when router/ISP access isn't available, you don't want to
touch your domain's DNS at all, and you don't want to pay for anything.
[Tailscale](https://tailscale.com) is free for personal use, no time
limit, no credit card. Like Cloudflare Tunnel, a program on the server
makes an outbound-only connection out - no open ports, no router
changes. The trade-off: the public URL is Tailscale's
(`https://<machine>.<tailnet>.ts.net`), not your own domain, since
that's what makes this path need nothing from your domain's DNS.

Do steps 0-2 from the top of this doc (get the code, install,
generate/set the token - `server.host` stays `127.0.0.1`, same as the
Caddy path, since Tailscale connects to it locally), then:

1. Sign up free at https://tailscale.com (sign in with Google,
   Microsoft, GitHub, or email - no credit card).
2. Install Tailscale on the Windows Server: download from
   https://tailscale.com/download/windows, run it, sign in with the
   same account when prompted. This connects the server to your
   private Tailscale network and assigns it a name.
3. In the admin console (https://login.tailscale.com/admin/machines),
   find this server in the list and note its name (e.g. `server`).
   Your tailnet's domain is shown in the admin console too, something
   like `tailxxxx.ts.net` - combined, this server's address is
   `server.tailxxxx.ts.net`.
4. Enable HTTPS certificates for your tailnet - in the admin console,
   go to DNS settings (https://login.tailscale.com/admin/dns) and turn
   on **HTTPS Certificates**. Required before Funnel will work.
5. Enable Funnel via Access Controls
   (https://login.tailscale.com/admin/acls). This isn't a toggle -
   it's a policy file. If your policy uses the newer `"grants"` format
   (Tailscale's current default for new accounts), add a `"nodeAttrs"`
   block as a sibling of `"grants"`, not nested inside it:
   ```json
   "nodeAttrs": [
     {
       "target": ["autogroup:member"],
       "attr":   ["funnel"],
     },
   ],
   ```
   Save. If your policy already has other content in `"nodeAttrs"`,
   add this as one more entry in that array instead of replacing it.
6. Test it - in one terminal, run the app:
   ```
   venv\Scripts\python -m abhayleads serve
   ```
   In a second terminal, turn on Funnel pointing at that port:
   ```
   tailscale funnel 8443
   ```
   This prints your public HTTPS URL (something like
   `https://server.tailxxxx.ts.net/`) and keeps it live while that
   terminal stays open. Visit that URL from your phone - no Tailscale
   app needed on the phone, Funnel makes it genuinely public, same as
   any other website. (If the exact command differs from what's shown
   here - Tailscale's CLI does evolve - run `tailscale funnel --help`
   on the server for the current syntax.)
7. Make it permanent:
   ```
   tailscale funnel --bg 8443
   ```
   The `--bg` flag keeps the funnel active in the background, surviving
   that terminal closing (Tailscale itself already runs as a Windows
   service from step 2). Then set up `abhayleads serve` to run 24/7 the
   same way as the Caddy path's step 7: `nssm.exe install
   AbhayLeadsServer` with Path = `<repo>\venv\Scripts\python.exe`,
   Arguments = `-m abhayleads serve`, Startup directory = the repo
   folder, then `nssm.exe start AbhayLeadsServer`.

## Steps 8-9, Path D version

Same idea as the top of this doc, just with a different URL:

**Point your desktop app at the server** - that profile's
`config.yaml`:
```yaml
remote_server:
  base_url: "https://server.tailxxxx.ts.net"
  token: "the-same-token-from-step-1"
```

**Use it from your iPhone** - open `https://server.tailxxxx.ts.net` in
Safari, log in with the token, same full read/write experience as
every other path in this doc.

### Troubleshooting NSSM: "Unexpected status SERVICE_PAUSED"

If `nssm start AbhayLeadsServer` prints this, the service isn't really
running - the wrapped `abhayleads serve` process crashed almost
immediately after NSSM launched it, and NSSM's crash-loop protection
paused the service rather than endlessly restarting it. To see the
actual error:
```
nssm set AbhayLeadsServer AppStdout C:\AbhayLeads\service-stdout.log
nssm set AbhayLeadsServer AppStderr C:\AbhayLeads\service-stderr.log
nssm restart AbhayLeadsServer
type C:\AbhayLeads\service-stderr.log
```
Also double check what NSSM actually saved for the three key fields
(a typo in the install dialog is the most common cause):
```
nssm get AbhayLeadsServer Application
nssm get AbhayLeadsServer AppParameters
nssm get AbhayLeadsServer AppDirectory
```
These should read exactly `<repo>\venv\Scripts\python.exe`,
`-m abhayleads serve`, and `<repo>` (e.g. `C:\AbhayLeads`).
`nssm status AbhayLeadsServer` gives the current real state at any
time if the start/restart output is ambiguous.

### Troubleshooting the client: "Server rejected the access token"

If a client machine's `abhayleads` commands (once `remote_server` is
configured) fail with `RemoteDatabaseError: Server rejected the
access token - check server.token matches on both ends`, the
connection itself is working (it reached the server and got a real
HTTP response) - `server.token` in the server's config.yaml and
`remote_server.token` in the client's config.yaml just don't match
character-for-character. Easiest fix: regenerate a fresh token with
`abhayleads server-token`, then paste that exact same value into both
files in one sitting (rather than hunting for a typo in what's
already there), and restart the `AbhayLeadsServer` service so it picks
up the change.
