import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHOWCASE = ROOT / "showcase"


def _load():
    spec = importlib.util.spec_from_file_location("make_showcase", SHOWCASE / "make_showcase.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_showcase_geojson_is_current(tmp_path):
    _load().main(tmp_path)
    built = json.loads((tmp_path / "map.geojson").read_text(encoding="utf-8"))
    committed = json.loads((SHOWCASE / "map.geojson").read_text(encoding="utf-8"))
    assert built == committed
    assert (tmp_path / "index.html").is_file()


def test_showcase_real_coordinates():
    fc = json.loads((SHOWCASE / "map.geojson").read_text(encoding="utf-8"))
    legs = [f for f in fc["features"] if f["properties"]["kind"] == "leg"]
    assert len(legs) == 3
    # Giza -> Cairo Tower is about 11.4 km; a swapped lat/lon would change this a lot.
    assert 11_000 < legs[0]["properties"]["distance_m"] < 12_000
    for f in fc["features"]:
        pts = [f["geometry"]["coordinates"]] if f["geometry"]["type"] == "Point" else f["geometry"]["coordinates"]
        for lon, lat in pts:
            assert 31.0 < lon < 31.4 and 29.9 < lat < 30.2  # Cairo: lon ~31.2 E, lat ~30.0 N


def test_showcase_png(tmp_path):
    pytest.importorskip("matplotlib")
    _load().main(tmp_path)
    png = tmp_path / "map.png"
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_showcase_notebook_executes():
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    pytest.importorskip("matplotlib")
    nb = nbformat.read(SHOWCASE / "showcase.ipynb", as_version=4)
    nbclient.NotebookClient(
        nb, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}
    ).execute()
    outputs = [o for c in nb.cells if c.cell_type == "code" for o in c.outputs]
    assert not [o for o in outputs if o.output_type == "error"]
    assert any("image/png" in o.get("data", {}) for o in outputs)
