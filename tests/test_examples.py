import json
from pathlib import Path

import pytest

from gpx_to_geojson import convert

ROOT = Path(__file__).resolve().parent.parent
GPX = ROOT / "examples" / "cairo.gpx"


def test_cairo_example_known_facts():
    fc = convert(GPX)
    wpts = {f["properties"]["name"]: f["geometry"]["coordinates"] for f in fc["features"] if f["properties"]["kind"] == "waypoint"}
    assert len(wpts) == 4
    # Cairo Tower is at about 31.22 E, 30.05 N (lon, lat order).
    lon, lat = wpts["Cairo Tower"]
    assert lon == pytest.approx(31.22, abs=0.02) and lat == pytest.approx(30.05, abs=0.02)
    (route,) = [f for f in fc["features"] if f["properties"]["kind"] == "route"]
    # Giza -> Cairo Tower is ~11 km, Cairo Tower -> Tahrir ~1 km, Tahrir -> Citadel ~3.5 km.
    assert 14_000 < route["properties"]["distance_m"] < 17_500
    # Route-point names are kept per vertex, in route order.
    assert route["properties"]["point_name"] == [
        "Great Pyramid of Giza", "Cairo Tower", "Tahrir Square", "Citadel of Saladin"
    ]


def test_demo_geojson_is_current():
    expected = json.loads(json.dumps(convert(GPX), ensure_ascii=False))
    assert json.loads((ROOT / "docs" / "demo.geojson").read_text(encoding="utf-8")) == expected
