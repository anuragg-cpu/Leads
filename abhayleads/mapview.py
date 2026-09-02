"""Map-rendering helpers shared by the server web UI's /map page and the
desktop GUI's standalone Map window, so the point-shaping and HTML/JS don't
drift apart between the two."""

import json
from string import Template
from typing import Any, Optional

# Matches style.css's stage badge colors.
STAGE_COLORS = {
    "New": "#8e8e93",
    "Contacted": "#0060c7",
    "Replied": "#8a6100",
    "Qualified": "#9a5300",
    "Won": "#1c7a34",
    "Lost": "#a3222e",
}


def leads_to_map_points(leads) -> list[dict]:
    """leads: an iterable of sqlite3.Row or dict (local vs. remote db), each
    already filtered to have a non-null lat/lon - only what the map needs."""
    return [
        {
            "id": lead["id"],
            "lat": lead["lat"],
            "lon": lead["lon"],
            "company": lead["company"] or lead["contact_name"] or lead["source"],
            "title": lead["title"],
            "stage": lead["stage"],
            "score": lead["score"],
        }
        for lead in leads
    ]


def safe_json_for_script(value: Any) -> str:
    """json.dumps, escaped so it's safe to embed inside a <script> tag even
    if a field (a lead's company name, etc.) happens to contain
    "</script>" or other HTML-sensitive characters - same escaping Flask's
    `tojson` filter and Django's `json_script` use. Starlette's
    Jinja2Templates has no built-in equivalent, so this is done in Python
    rather than relying on a template filter that doesn't exist."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


_PAGE_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Abhay Leads - Map</title>
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, "Segoe UI", Arial, sans-serif; }
  .empty-state { padding: 24px; max-width: 480px; margin: 60px auto; text-align: center; color: #555; }
</style>
</head>
<body>
$body_html
</body>
</html>
""")

_EMPTY_STATE_HTML = (
    '<p class="empty-state">No leads with a map location yet. Only '
    "<strong>osm_places</strong> leads carry coordinates - run "
    '"Find New Leads" (with osm_places enabled) to populate the map. Leads '
    "found before this feature was added won't have a location until "
    "they're re-fetched.</p>"
)

# Only rendered when there's at least one point - otherwise this would
# load Leaflet/tiles from the internet for nothing every time the empty
# map window is opened, and the raw "leads-map" string would leak into
# the empty-state page even though no map is shown (bit us once already
# in the server's version of this page - see map.html's git history).
_MAP_BODY_TEMPLATE = Template("""<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>#leads-map { height: 100%; }</style>
<div id="leads-map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
(function () {
  var points = $points_json;
  var leadUrlBase = $lead_url_base_json;

  var map = L.map('leads-map');
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var stageColors = $stage_colors_json;

  var clusters = L.markerClusterGroup({ maxClusterRadius: 50 });
  var bounds = [];

  points.forEach(function (p) {
    var color = stageColors[p.stage] || '#8e8e93';
    var marker = L.circleMarker([p.lat, p.lon], {
      radius: 8, color: color, fillColor: color, fillOpacity: 0.85, weight: 1
    });
    var popup = '<strong>' + escapeHtml(p.company) + '</strong>';
    if (p.title) popup += '<br>' + escapeHtml(p.title);
    popup += '<br>' + escapeHtml(p.stage) + ' &middot; score ' + p.score;
    if (leadUrlBase) {
      popup += '<br><a href="' + leadUrlBase + '/leads/' + p.id + '" target="_blank" rel="noopener">Open lead &rarr;</a>';
    }
    marker.bindPopup(popup);
    clusters.addLayer(marker);
    bounds.push([p.lat, p.lon]);
  });

  map.addLayer(clusters);
  map.fitBounds(bounds, { padding: [30, 30] });

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
})();
</script>""")


def render_standalone_map_html(points: list[dict], lead_url_base: Optional[str] = None) -> str:
    """A full, self-contained HTML page (its own <html>/<head>/<body>, not
    extending the server's base.html) for the desktop GUI's Map window -
    opened directly in the user's browser from a local temp file, since the
    desktop app has no bundled web view of its own. `lead_url_base`, when
    given (the app is pointed at a remote server), makes each popup's "Open
    lead" link point at that server's real /leads/<id> page; omitted
    entirely in local-only mode since there's no web server to link to."""
    if points:
        body_html = _MAP_BODY_TEMPLATE.substitute(
            points_json=safe_json_for_script(points),
            lead_url_base_json=json.dumps(lead_url_base.rstrip("/")) if lead_url_base else "null",
            stage_colors_json=json.dumps(STAGE_COLORS),
        )
    else:
        body_html = _EMPTY_STATE_HTML
    return _PAGE_TEMPLATE.substitute(body_html=body_html)
