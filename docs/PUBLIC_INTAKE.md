# Public form intake - taking leads from a public website

If you have a marketing site or landing page with a contact/lead
form, this lets that form submit directly into Abhay Leads - no
separate serverless function needed, and without exposing your real
admin token (which can read/edit/delete everything) to the public.

## How this is safe to put in public JS

`abhayleads serve`'s main API (`/api/...`) uses one shared admin
token that can do anything - list, edit, delete, reset everything.
That token must never appear in a public website's source code.

Public intake is a **separate, optional token** for one narrow
endpoint that can only ever *create* a lead - nothing else. Even if
someone views your page's source and copies it, the worst they can do
is submit fake leads, same as spam through any contact form. It's
rate-limited per IP (5 submissions/minute) and supports a honeypot
field to quietly ignore basic bots.

## Enable it

1. Generate a token (same command used for the admin one - just run it
   again for a second, different value):
   ```
   abhayleads server-token
   ```
2. Add it to the server's `config.yaml`:
   ```yaml
   server:
     token: "your-existing-admin-token"
     public_intake_token: "the-new-token-from-step-1"
   ```
3. Restart `abhayleads serve` (or the `AbhayLeadsServer` service if
   running via NSSM - see `docs/SERVER_SETUP.md`). Leaving
   `public_intake_token` blank (the default) keeps this feature off
   entirely - `/public/intake/...` won't even respond until it's set.

## The endpoint

```
POST https://your-server-url/public/intake/<public_intake_token>
Content-Type: application/json
```
The token is part of the URL, not a header - same pattern as
Formspree's form IDs - so a plain `fetch()`/`<form>` submit from any
website works with no special headers beyond `Content-Type`.

Body (all fields optional except needing at least `name` or `company`):
```json
{
  "name": "Priya Sharma",
  "company": "Sunrise Housing Society",
  "email": "priya@example.com",
  "phone": "9876543210",
  "message": "We need panic buttons for our 200-flat society",
  "segment": "Housing Society",
  "website": ""
}
```
- `name` -> stored as the lead's contact name
- `company`, `email`, `phone` -> stored as-is
- `message` and `segment` -> folded together into the lead's notes/raw
  text (there's no dedicated "segment" field on a lead)
- `website` -> **honeypot**, leave this input in your form's HTML but
  hide it with CSS (e.g. `position:absolute;left:-9999px`) - a real
  visitor never fills it in, but a bot blindly filling every field
  will. If it arrives non-empty, the request returns a normal-looking
  success but nothing is actually saved.

## Responses

| Status | Meaning |
|---|---|
| `200 {"ok": true}` | Saved (or silently dropped, if the honeypot tripped - same response either way, on purpose) |
| `400` | Missing both `name` and `company` |
| `404` | Wrong or missing token in the URL |
| `429` | Rate limit hit (5/minute per IP) - try again shortly |

## Example: wiring an HTML form

```html
<form id="lead-form">
  <input name="name" placeholder="Your name">
  <input name="company" placeholder="Company / Society name">
  <input name="phone" placeholder="Phone">
  <select name="segment">
    <option>Housing Society</option>
    <option>Co-working Space</option>
    <option>Hospital</option>
    <option>Campus</option>
  </select>
  <textarea name="message" placeholder="Tell us about your needs"></textarea>
  <!-- honeypot - keep this hidden via CSS, never shown to real users -->
  <input name="website" style="position:absolute;left:-9999px" tabindex="-1" autocomplete="off">
  <button type="submit">Send</button>
</form>

<script>
document.getElementById('lead-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  try {
    const resp = await fetch(
      'https://your-server-url/public/intake/YOUR_PUBLIC_INTAKE_TOKEN',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }
    );
    if (resp.ok) {
      form.reset();
      alert('Thanks - we got it!');
    } else if (resp.status === 429) {
      alert('Too many submissions - please try again in a minute.');
    } else {
      alert('Something went wrong - please try again.');
    }
  } catch {
    alert('Could not reach the server - check your connection and try again.');
  }
});
</script>
```

Swap in your real server URL and `public_intake_token` from step 1
above. That's the whole integration - no proxy function, no other
service to host or maintain.
