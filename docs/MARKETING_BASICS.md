# Marketing basics for using this tool

You said you're new to marketing, so here's the minimum you need to use
this tool well - not a full course, just the concepts baked into the app.

## 1. ICP (Ideal Customer Profile)

Before searching for leads, you need a working answer to: **who exactly
buys Abhay, and why?** Not "everyone" - the narrower this is, the better
your search keywords and the higher the signal-to-noise ratio.

A usable ICP answers:
- What problem does Abhay solve?
- Who feels that problem badly enough to look for a fix? (role, company
  size/type, industry)
- What words would *they* type when looking for a solution, or when
  complaining about the problem publicly?

That last question is directly what goes into `product.keywords` in
`config.yaml`. Good keywords are phrases people actually write, e.g.
`"any recommendations for a tool to..."`, `"looking for an alternative
to <competitor>"`, `"how do I <the job Abhay does>"` - not just your
product's category name, which is usually too generic and returns noise.

## 2. Why this tool doesn't scrape LinkedIn/Facebook/etc.

Those sites explicitly forbid scraping in their Terms of Service, and
enforce it with account bans and legal action (LinkedIn has sued scrapers
successfully). "Free" doesn't mean "allowed." This tool sticks to sources
that are either public APIs meant for this kind of use, or public
read-only endpoints used at a low, respectful volume - see
`docs/SOURCES.md` for exactly what each one does and why it's fine.

The tradeoff: this approach finds **signal**, not **verified contact
lists**. You'll mostly get people/companies publicly discussing a
relevant problem - not a database of "500 CFOs at mid-size companies
with emails." Turning a signal into an outbound-ready lead (finding
their company email, etc.) is a manual step you do once something looks
promising - see "What this tool won't do" below.

## 3. What "lead score" means here

Every candidate is scored 0-100 based on how many of your configured
keywords it matches, weighted by whether they're in the title (stronger
signal) and by a per-source multiplier you control. It is **not** a
prediction of "how likely to buy" - it's a rough relevance filter so you
look at the best matches first. Expect to tune `scoring` in `config.yaml`
after your first few runs, once you see what "good" vs "noise" looks
like for your keywords.

## 4. A simple pipeline (the CRM's stages)

`New -> Contacted -> Replied -> Qualified -> Won -> Lost`

- **New**: found by a fetch, nothing done yet.
- **Contacted**: you reached out (reply to their post, DM, email...).
- **Replied**: they responded, in any way.
- **Qualified**: after talking, they're a real potential buyer.
- **Won** / **Lost**: deal closed either way.

Move leads through this manually as you work them - the point of
tracking stage *and* timestamps (visible in a lead's detail view) is
seeing where deals stall, which tells you what to fix (e.g. lots of
`Contacted` leads that never reply might mean your outreach message
needs work, not that you need more leads).

## 5. Follow-up cadence

Leads go cold fast. A reasonable default (already the tool's default,
`follow_up.default_days` in config): if you haven't touched a lead in
3 days, it should nag you. The GUI's "Due for follow-up" filter and the
`abhayleads list --due` CLI command surface these. Set a `next_follow_up`
date on any lead (in its detail view) as a reminder to yourself.

## 6. Outreach basics, briefly

- **Reference the specific thing they said**, not a template. If you
  found them via a Reddit post about a problem, mention *that post*.
  Generic cold pitches get ignored or reported as spam.
- **Ask, don't pitch, first.** "Is this still a problem for you? Here's
  roughly how we solve it, happy to show you if useful" beats a feature
  list.
- **Respect the venue.** Replying publicly in the thread where they
  asked is usually fine and welcomed; DMing a stranger a sales pitch
  out of nowhere reads as spam even when it's well-intentioned.
- **Know the legal basics if you email people directly:** unsolicited
  commercial email is regulated (e.g. CAN-SPAM in the US, GDPR/PECR in
  the EU/UK) - always include a real way to opt out/unsubscribe, use a
  real sender identity, and don't buy/scrape bulk email lists.

## 7. What this tool won't do for you

- It won't find personal emails/phone numbers - that typically requires
  paid enrichment tools (Hunter.io, Apollo.io, Clearbit, etc; some have
  small free tiers you could wire in later as another `sources/` module).
- It won't write your outreach messages - though once leads are in the
  CRM, you could ask Claude to draft one per lead using the `raw_text`
  and `keyword_matched` fields for context.
- It won't tell you if your ICP/keywords are right - that only comes
  from looking at real results and adjusting `config.yaml`.
