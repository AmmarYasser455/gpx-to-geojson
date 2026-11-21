import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "brand"
ACCENT = "#f2552c"
INK = {"logo.svg": "#121417", "logo-dark.svg": "#f3eee4"}


@pytest.mark.parametrize("name", sorted(INK))
def test_logo_is_valid_and_on_palette(name):
    path = BRAND / name
    assert path.exists()
    root = ET.parse(path).getroot()
    assert root.get("viewBox") == "0 0 100 100"
    assert root.get("width") == "100" and root.get("height") == "100"
    colours = set()
    for el in root.iter():
        for attr in ("fill", "stroke"):
            v = el.get(attr)
            if v and v != "none":
                colours.add(v.lower())
    assert colours == {INK[name], ACCENT}
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"gradient|opacity|filter|<image|<text", text)


def test_readme_header_and_openterra():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.lstrip().startswith('<p align="center">')
    assert "assets/brand/logo-dark.svg" in readme and "assets/brand/logo.svg" in readme
    assert "[OpenTerra](https://github.com/AmmarYasser455)" in readme
