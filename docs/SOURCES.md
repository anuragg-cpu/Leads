# Lead sources

All sources are free and stick to public APIs or low-volume, polite,
read-only access - see `docs/MARKETING_BASICS.md` for why scraping sites
like LinkedIn/Facebook is deliberately excluded.

## Hacker News (`hackernews`)

Uses the free public Algolia HN Search API. No key, no setup.
Best for: dev tools, technical products, startup-adjacent audiences.

## Google News (`google_news`)

Uses Google News' public RSS search feed. No key, no setup.
Best for: catching press mentions, funding news, "X launches" stories -
useful as buying-intent/growth signals for outbound targets.

## GitHub (`github`)

Uses the free public GitHub REST search API.
- Works with **no setup** at 10 requests/minute.
- Optional: create a free personal access token (no scopes needed) at
  https://github.com/settings/tokens -> "Generate new token (classic)"
  -> no scopes checked -> generate. Set it as the `GITHUB_TOKEN`
  environment variable to raise the limit to 30/minute.

Best for: dev tools, APIs, infra products - finds repos actively being
built in your problem space.

## Reddit (`reddit`)

Best for: people describing a problem or asking for recommendations in
communities relevant to Abhay. Configure which subreddits to search
under `sources.reddit.subreddits` in `config.yaml`.

Two modes:

1. **No setup (fallback)**: reads each subreddit's public search JSON
   endpoint directly, throttled to about 1 request every 2 seconds.
   Fine for occasional personal use.

2. **Recommended - free OAuth app**: more reliable and clearly within
   Reddit's terms for programmatic access.
   1. Go to https://www.reddit.com/prefs/apps
   2. Click "create app" (bottom left)
   3. Type: **script**, name: anything (e.g. "AbhayLeads"), redirect
      URI: `http://localhost:8080` (unused, but required)
   4. After creating, note the string under the app name (client ID)
      and the "secret" field (client secret)
   5. Set environment variables `REDDIT_CLIENT_ID` and
      `REDDIT_CLIENT_SECRET` to those values before running the app/exe.

On Windows, set env vars permanently via:
`setx REDDIT_CLIENT_ID "your-id-here"` (then open a new terminal), or
System Properties -> Environment Variables.

## Places near you (`osm_places`)

Different from every other source: it doesn't search text for signal, it
builds a **canvassing list** - named hospitals, co-working spaces,
campuses, and apartment complexes near each town/locality you list in
`product.target_locations`, using free public map data. Good fit for a
product sold to a specific kind of physical place in a specific area
(e.g. a hardware install business), where the buyer isn't out there
publicly posting about the problem.

Two free APIs, no key needed:
- **Nominatim** turns each locality name into coordinates, capped at
  1 request/second and cached to disk after the first run.
- **Overpass API** queries OpenStreetMap for named places matching your
  `categories` within `radius_meters` of that point.

Because there's no free text to keyword-match, these get a flat floor
score instead (`scoring.source_base_score.osm_places`) - treat them as
a cold-outreach target list, not a "someone's actively looking" signal.

Keep `target_locations` at town/locality granularity - a state-level
entry like "Maharashtra" geocodes to one point near the state's center,
and a few-km radius around it won't cover much.

**Note on reliability**: public Overpass mirrors are known to rate-limit
or block cloud/datacenter IP ranges (this is a common complaint from
people running scrapers/bots against it) - if `osm_places` comes back
empty or errors on your first run, try again in a few minutes, or check
https://overpass-api.de/api/status for the primary instance's health.

## Government tender portals (not automated - here's why)

Given Abhay is sold via procurement/tenders to hospitals, campuses, and
housing societies, GeM (gem.gov.in), the Central Public Procurement
Portal (eprocure.gov.in), and Maharashtra's own eProcurement portal
(mahatenders.gov.in) all looked worth adding. They're not, though:

- CPPP and mahatenders (same government NIC platform) both require
  **solving a CAPTCHA** just to list active tenders - confirmed by
  fetching their search pages directly. Automating past that would mean
  defeating an anti-bot measure, which isn't something this tool does.
- GeM's bid-search endpoints reset the connection outright when hit
  programmatically (bot-blocked).

**What to do instead - genuinely free, and actually within these
portals' own intended use**: register as a vendor on GeM and on
mahatenders.gov.in (both free), then use each portal's own **tender
alert subscription** feature to get emailed when a new tender matching
your category (e.g. "security systems", "electronic surveillance",
"alarm systems") and location is posted. That's the portals' own free
notification mechanism - it does exactly what a scraper would have done,
without the CAPTCHA problem.

## Adding another source later

Once you've told me about Abhay, good candidates to add (all have free
tiers, none require scraping):

- **Google Custom Search JSON API** - 100 free queries/day, broader web
  search than Google News.
- **ProductHunt API** - free with a token, good for finding people
  launching adjacent/competing products.
- **RSS feeds you choose** - company blogs, job boards (a company hiring
  for a role your product supports is a buying signal), industry
  newsletters.
- **Twitter/X API** - free tier is very limited (read access mostly
  gone), usually not worth it unless you already pay for API access.

To add one: copy the shape of any file in `abhayleads/sources/`
(subclass `BaseLeadSource`, implement `fetch()`), register it in
`abhayleads/sources/__init__.py`'s `SOURCE_REGISTRY`, and add its config
block to `config/config.example.yaml`.
