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

**Region matters a lot.** Left unconfigured, every query hits the US
edition of Google News (`hl=en-US&gl=US`), so a generic keyword like
"panic button system" comes back almost entirely as US school/hospital
news - not useful if your buyer is elsewhere. Two settings fix this,
and neither changes what counts as a keyword match (scoring still uses
your plain `product.keywords` list, untouched):

```yaml
sources:
  google_news:
    query_suffix: "India"        # appended to every search query
    edition:
      hl: "en-IN"                 # language
      gl: "IN"                    # country
      ceid: "IN:en"                # country:language, Google's combined param
```

Swap `India`/`IN` for your own market. You can also narrow further
(e.g. `query_suffix: "Pune"`) at the cost of missing broader regional
coverage.

**If real matches are still scoring 0**: scoring does exact substring
matching on your `product.keywords` phrases. Google's own search is
fuzzy, so it can return an article that's clearly relevant but never
literally contains your exact phrase - e.g. a keyword `"panic button
system"` won't match a headline that only says "panic button" without
"system". If you notice this, add the shorter/more common phrasing as
its own keyword.

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

**Duplicate places**: OSM occasionally maps one real building as two
separate map elements (a data-entry slip, not something this tool can
detect in advance). Two elements with the *exact same name* found within
the same locality in a single fetch are automatically collapsed into one
lead. This is intentionally exact-match only - "Prakrtii CHS G Block"
and "...F Block" are kept as separate leads, since multi-block societies
often do need separate outreach per block/wing.

If you're upgrading from before this existed (or fetched a lot before
noticing duplicates), run `abhayleads dedupe` once to clean up your
existing database the same way - it keeps whichever duplicate you've
already worked (non-"New" stage or has notes), or the earliest one
otherwise.

### If `osm_places` keeps failing

The public Overpass API mirrors this source uses are, honestly, flaky -
confirmed independently on two different networks while building this:
connection resets, 502s, and timeouts, none of it specific to your setup.
This is a known limitation of relying on free shared Overpass instances,
not a bug to chase.

What to do about it, in order:

1. **Just try again.** These instances go through busy/quiet periods.
   Running `abhayleads fetch --source osm_places` again in an hour or the
   next day often just works.
2. **Check status first**, to avoid guessing:
   https://overpass-api.de/api/status
3. **One-off manual fallback**: go to https://overpass-turbo.eu/, paste
   in a query like the one below (edit the coordinates/radius/tag for
   what you need), run it, then Export -> GeoJSON/CSV to get the same
   data by hand. Slower, but it runs in your browser against the same
   API and tends to succeed when the raw API call doesn't.
   ```
   [out:json][timeout:25];
   (
     nwr["amenity"="hospital"](around:5000,18.5204,73.8567);
   );
   out center tags;
   ```
   (That example point is central Pune - swap in coordinates for your
   locality; look them up at https://nominatim.openstreetmap.org/ui/search.html)
4. If you want, tell me and I can look at wiring in a paid-but-cheap
   alternative later (e.g. Google Places API, which has a free monthly
   credit but needs a billing account) - not done by default since you
   asked to stick to free/no-signup sources.

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
