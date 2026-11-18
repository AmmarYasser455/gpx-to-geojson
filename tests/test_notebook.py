import json
import os
from pathlib import Path

NB = Path(__file__).resolve().parent.parent / "examples" / "demo.ipynb"


def test_notebook_runs(monkeypatch):
    nb = json.loads(NB.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    monkeypatch.chdir(NB.parent.parent)
    ns = {"__name__": "__notebook__"}
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            exec("".join(cell["source"]), ns)
    assert os.path.exists("examples/cairo.gpx")
