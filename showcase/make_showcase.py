"""Build the showcase (map.geojson, map.png, index.html) from showcase/data/, offline.

Run from the repository root:  python showcase/make_showcase.py
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from pyproj import Geod  # noqa: E402

from gpx_to_geojson import convert  # noqa: E402

DATA = HERE / "data" / "cairo.gpx"
CREDIT = "Landmark coordinates: examples/cairo.gpx (gpx-to-geojson, MIT)"
GEOD = Geod(ellps="WGS84")
# Label offsets in points, to keep the labels of the close landmarks apart.
POINT_OFFSETS = {"Cairo Tower": (-8, 6), "Tahrir Square": (8, 10)}
LEG_OFFSETS = {1: (6, -14), 2: (-4, -22), 3: (8, 2)}

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Giza to the Citadel: gpx-to-geojson showcase</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  body { margin: 0; font-family: sans-serif; }
  header { padding: 8px 12px; }
  h1 { font-size: 1.2rem; margin: 0 0 4px; }
  p { margin: 2px 0; font-size: .9rem; }
  #map { height: calc(100vh - 110px); }
</style>
</head>
<body>
<header>
  <h1>How long is the route from the Giza pyramids to the Citadel of Saladin?</h1>
  <p>A GPX route through four Cairo landmarks, converted to GeoJSON; lengths are geodesic (WGS84 ellipsoid), in metres.</p>
  <p>Click a leg or a landmark for its properties. <a href="https://github.com/AmmarYasser455/gpx-to-geojson">Source on GitHub</a></p>
</header>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  var map = L.map('map');
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); }
  fetch('map.geojson').then(function (r) { return r.json(); }).then(function (data) {
    var layer = L.geoJSON(data, {
      style: function (f) {
        return f.properties.kind === 'leg' ? { color: '#c2410c', weight: 4 } : { color: '#1d4ed8', weight: 2, dashArray: '4 6' };
      },
      pointToLayer: function (f, ll) { return L.circleMarker(ll, { radius: 7, color: '#1d4ed8', fillOpacity: 0.9 }); },
      onEachFeature: function (f, l) {
        var rows = Object.keys(f.properties).filter(function (k) {
          return typeof f.properties[k] !== 'object' || f.properties[k] === null;
        }).map(function (k) { return '<b>' + esc(k) + '</b>: ' + esc(f.properties[k]); });
        l.bindPopup(rows.join('<br>'));
      }
    }).addTo(map);
    map.fitBounds(layer.getBounds());
  });
</script>
</body>
</html>
"""


def build_collection(gpx=DATA):
    """Run the tool on the GPX and add one LineString per route leg (lon/lat, WGS84)."""
    fc = convert(gpx)
    (route,) = [f for f in fc["features"] if f["properties"]["kind"] == "route"]
    coords = route["geometry"]["coordinates"]  # [lon, lat]
    names = route["properties"]["point_name"]
    legs = []
    for i in range(len(coords) - 1):
        (lon1, lat1), (lon2, lat2) = coords[i], coords[i + 1]
        _, _, d = GEOD.inv(lon1, lat1, lon2, lat2)  # lon, lat order; metres
        legs.append({
            "type": "Feature",
            "properties": {"kind": "leg", "leg": i + 1, "from": names[i], "to": names[i + 1],
                           "distance_m": round(d, 2)},
            "geometry": {"type": "LineString", "coordinates": [coords[i], coords[i + 1]]},
        })
    out = {"type": "FeatureCollection", "features": fc["features"] + legs}
    return json.loads(json.dumps(out, ensure_ascii=False))


def plot(fc, ax):
    """Draw the collection on a matplotlib axis (lon/lat degrees, aspect corrected for latitude)."""
    for f in fc["features"]:
        p, g = f["properties"], f["geometry"]
        if p["kind"] == "leg":
            xs, ys = zip(*g["coordinates"])
            ax.plot(xs, ys, color="#c2410c", lw=2.5, solid_capstyle="round")
            ax.annotate(f"{p['distance_m'] / 1000:.1f} km", (sum(xs) / 2, sum(ys) / 2),
                        textcoords="offset points", xytext=LEG_OFFSETS[p["leg"]], fontsize=9, color="#c2410c")
        elif p["kind"] == "waypoint":
            x, y = g["coordinates"]
            ax.plot(x, y, "o", color="#1d4ed8", ms=7, zorder=3)
            ax.annotate(p["name"], (x, y), textcoords="offset points",
                        xytext=POINT_OFFSETS.get(p["name"], (6, 5)), fontsize=9, ha=(
                            "right" if POINT_OFFSETS.get(p["name"], (1, 0))[0] < 0 else "left"))
    ax.plot([], [], color="#c2410c", lw=2.5, label="Route leg (geodesic length)")
    ax.plot([], [], "o", color="#1d4ed8", label="Landmark (GPX waypoint)")
    ax.legend(loc="lower right")
    ax.set_xlim(31.10, 31.30)
    ax.set_ylim(29.96, 30.07)
    ax.set_aspect(1 / math.cos(math.radians(30.03)))
    ax.set_xlabel("Longitude (deg E, WGS84)")
    ax.set_ylabel("Latitude (deg N); north is up")
    ax.grid(alpha=0.3)


def main(out_dir=None):
    out = Path(out_dir) if out_dir else HERE
    out.mkdir(parents=True, exist_ok=True)
    fc = build_collection()
    (out / "map.geojson").write_text(json.dumps(fc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "index.html").write_text(HTML, encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib missing: map.png skipped")
        return out
    fig, ax = plt.subplots(figsize=(8.5, 7))
    plot(fc, ax)
    total = sum(f["properties"]["distance_m"] for f in fc["features"] if f["properties"]["kind"] == "leg")
    ax.set_title(f"Giza to the Citadel of Saladin: {total / 1000:.1f} km in three legs")
    fig.text(0.99, 0.01, CREDIT, ha="right", va="bottom", fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(out / "map.png", dpi=150)  # 8.5 in x 150 dpi = 1275 px wide
    plt.close(fig)
    return out


if __name__ == "__main__":
    main()
