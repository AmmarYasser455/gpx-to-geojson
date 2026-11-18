import json

import pytest

from gpx_to_geojson import parse_gpx
from gpx_to_geojson.cli import main

NS = 'xmlns="http://www.topografix.com/GPX/1/1"'


def gpx(body):
    return f'<?xml version="1.0"?><gpx version="1.1" {NS}>{body}</gpx>'


TRACK = gpx(
    """<trk><name>t</name><trkseg>
    <trkpt lat="0" lon="0"><ele>10</ele><time>2024-01-01T10:00:00Z</time></trkpt>
    <trkpt lat="0" lon="1"><ele>30.5</ele><time>2024-01-01T10:10:00Z</time></trkpt>
    </trkseg></trk>"""
)


def test_track_distance_duration_elevation_and_axis_order():
    fc = parse_gpx(TRACK)
    (f,) = fc["features"]
    assert f["geometry"]["type"] == "LineString"
    # GeoJSON order is lon, lat, ele: the track runs along the equator in longitude.
    assert f["geometry"]["coordinates"] == [[0.0, 0.0], [1.0, 0.0]]
    assert f["properties"]["elevations"] == [10.0, 30.5]
    p = f["properties"]
    # One degree of longitude on the WGS84 equator is a*pi/180 = 111319.49 m.
    assert p["distance_m"] == pytest.approx(111319.49, abs=0.5)
    assert p["duration_s"] == 600.0
    assert p["start_time"] == "2024-01-01T10:00:00Z"
    assert p["times"] == ["2024-01-01T10:00:00Z", "2024-01-01T10:10:00Z"]
    assert (p["elevation_min_m"], p["elevation_max_m"]) == (10.0, 30.5)


def test_multi_segment_track_does_not_count_gap():
    body = """<trk><trkseg>
      <trkpt lat="0" lon="0"/><trkpt lat="0" lon="1"/></trkseg>
      <trkseg><trkpt lat="0" lon="10"/><trkpt lat="0" lon="11"/></trkseg></trk>"""
    (f,) = parse_gpx(gpx(body))["features"]
    assert f["geometry"]["type"] == "MultiLineString"
    assert f["properties"]["segments"] == 2
    assert f["properties"]["distance_m"] == pytest.approx(2 * 111319.49, abs=1)
    assert "duration_s" not in f["properties"]


def test_waypoint_and_route_without_namespace():
    xml = (
        '<gpx version="1.1"><wpt lat="30.0459" lon="31.2243"><name>Cairo Tower</name></wpt>'
        '<rte><rtept lat="0" lon="0"/><rtept lat="1" lon="0"/></rte></gpx>'
    )
    wpt, rte = parse_gpx(xml)["features"]
    assert wpt["geometry"] == {"type": "Point", "coordinates": [31.2243, 30.0459]}
    assert wpt["properties"]["name"] == "Cairo Tower"
    assert rte["properties"]["kind"] == "route"
    assert rte["properties"]["distance_m"] == pytest.approx(110574.39, abs=1)  # 1 deg lat at equator


def test_invalid_and_degenerate_input_is_skipped():
    body = """<wpt lat="95" lon="0"/><wpt lat="x" lon="0"/><wpt lon="3"/>
      <trk><trkseg><trkpt lat="1" lon="1"/></trkseg></trk>
      <rte><rtept lat="1" lon="1"/><rtept lat="200" lon="1"/></rte>"""
    assert parse_gpx(gpx(body))["features"] == []


def test_missing_elevation_gives_2d_and_bad_time_ignored():
    body = """<trk><trkseg>
      <trkpt lat="0" lon="0"><ele>5</ele><time>garbage</time></trkpt>
      <trkpt lat="0" lon="1"/></trkseg></trk>"""
    (f,) = parse_gpx(gpx(body))["features"]
    assert f["geometry"]["coordinates"] == [[0.0, 0.0], [1.0, 0.0]]
    assert "duration_s" not in f["properties"]
    assert f["properties"]["times"] == [None, None]
    assert f["properties"]["elevations"] == [5.0, None]


def test_route_keeps_every_timestamp_and_elevation():
    body = """<rte>
      <rtept lat="0" lon="0"><ele>1</ele><time>2024-01-01T10:00:00Z</time></rtept>
      <rtept lat="0" lon="0.5"><ele>7.5</ele><time>2024-01-01T10:05:00Z</time></rtept>
      <rtept lat="0" lon="1"/>
      <rtept lat="0" lon="1.5"><ele>3</ele><time>2024-01-01T10:20:00Z</time></rtept></rte>"""
    (f,) = parse_gpx(gpx(body))["features"]
    p = f["properties"]
    assert p["times"] == ["2024-01-01T10:00:00Z", "2024-01-01T10:05:00Z", None, "2024-01-01T10:20:00Z"]
    assert p["elevations"] == [1.0, 7.5, None, 3.0]
    assert p["duration_s"] == 1200.0
    # Coordinates stay uniformly 2D because one vertex has no elevation.
    assert all(len(c) == 2 for c in f["geometry"]["coordinates"])


def test_single_timestamp_is_kept():
    body = """<rte><rtept lat="0" lon="0"/>
      <rtept lat="0" lon="1"><time>2024-05-01T08:00:00Z</time></rtept></rte>
      <trk><trkseg><trkpt lat="0" lon="0"><time>2024-05-01T09:00:00Z</time></trkpt>
      <trkpt lat="0" lon="1"/></trkseg></trk>"""
    rte, trk = parse_gpx(gpx(body))["features"]
    assert rte["properties"]["times"] == [None, "2024-05-01T08:00:00Z"]
    assert rte["properties"]["start_time"] == rte["properties"]["end_time"] == "2024-05-01T08:00:00Z"
    assert "duration_s" not in rte["properties"]
    assert trk["properties"]["times"] == ["2024-05-01T09:00:00Z", None]


def test_multi_segment_vertex_arrays_are_nested():
    body = """<trk><trkseg><trkpt lat="0" lon="0"><ele>4</ele></trkpt><trkpt lat="0" lon="1"/></trkseg>
      <trkseg><trkpt lat="0" lon="2"/><trkpt lat="0" lon="3"><ele>9</ele></trkpt></trkseg></trk>"""
    (f,) = parse_gpx(gpx(body))["features"]
    assert f["properties"]["elevations"] == [[4.0, None], [None, 9.0]]
    assert f["properties"]["times"] == [[None, None], [None, None]]


def test_standard_gpx_attributes_are_preserved():
    body = """<metadata><name>Doc</name><desc>d</desc><time>2024-01-01T00:00:00Z</time></metadata>
      <wpt lat="1" lon="2"><ele>5</ele><name>W</name><cmt>c</cmt><desc>wd</desc><src>s</src>
        <link href="https://example.org"><text>site</text></link><sym>Flag</sym><type>poi</type>
        <fix>3d</fix><sat>7</sat><hdop>1.5</hdop><dgpsid>12</dgpsid></wpt>
      <rte><name>R</name><cmt>rc</cmt><desc>rd</desc><src>rs</src><number>3</number><type>walk</type>
        <link href="https://example.org/r"/>
        <rtept lat="0" lon="0"><name>A</name><desc>first</desc></rtept><rtept lat="0" lon="1"/></rte>
      <trk><name>T</name><desc>td</desc><number>x</number><type>run</type>
        <trkseg><trkpt lat="0" lon="0"><sat>4</sat></trkpt><trkpt lat="0" lon="1"/></trkseg>
        <trkseg><trkpt lat="0" lon="2"/><trkpt lat="0" lon="3"><sat>5</sat></trkpt></trkseg></trk>"""
    fc = parse_gpx(gpx(body))
    assert fc["metadata"] == {"name": "Doc", "desc": "d", "time": "2024-01-01T00:00:00Z"}
    wpt, rte, trk = (f["properties"] for f in fc["features"])
    assert wpt == {
        "kind": "waypoint", "name": "W", "cmt": "c", "desc": "wd", "src": "s", "sym": "Flag",
        "type": "poi", "fix": "3d", "sat": 7, "hdop": 1.5, "dgpsid": 12,
        "links": [{"href": "https://example.org", "text": "site"}], "ele": 5.0,
    }
    assert {k: rte[k] for k in ("name", "cmt", "desc", "src", "number", "type", "links")} == {
        "name": "R", "cmt": "rc", "desc": "rd", "src": "rs", "number": 3, "type": "walk",
        "links": [{"href": "https://example.org/r"}],
    }
    assert rte["point_name"] == ["A", None] and rte["point_desc"] == ["first", None]
    assert "point_sym" not in rte
    assert trk["desc"] == "td" and trk["type"] == "run" and "number" not in trk  # "x" is not a number
    assert trk["point_sat"] == [[4, None], [None, 5]]


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("sat", "7", 7),
        ("sat", "7.5", None),
        ("sat", "", None),
        ("hdop", "nan", None),
        ("hdop", "inf", None),
        ("hdop", "-inf", None),
        ("hdop", "abc", None),
        ("hdop", " 2.5 ", 2.5),
        ("magvar", "1e400", None),
        ("magvar", "9" * 400, None),
        ("sat", "9" * 400, None),  # huge integers must not crash (float overflow)
        ("sat", "9" * 5000, None),  # beyond int() digit limit
        ("sat", "-3", None),  # nonNegativeInteger
        ("sat", "+12", 12),
        ("sat", "1_0", None),
        ("sat", "٣", None),  # non-ASCII digits
        ("dgpsid", "0", 0),
        ("time", "0001-01-01T00:00:00+01:00", None),  # overflows when shifted to UTC
        ("time", "9999-12-31T23:59:59-01:00", None),
        ("time", "2024-13-01T00:00:00Z", None),
        ("name", "  ", None),
        ("name", " Cairo ", "Cairo"),
    ],
)
def test_waypoint_field_values_validated(field, value, expected):
    (f,) = parse_gpx(gpx(f'<wpt lat="1" lon="2"><{field}>{value}</{field}></wpt>'))["features"]
    json.dumps(f, allow_nan=False)
    assert f["properties"].get(field) == expected


@pytest.mark.parametrize("value, expected", [("3", 3), ("1" * 16, None), ("9" * 400, None), ("x", None)])
def test_route_number_validated(value, expected):
    doc = gpx(f'<rte><number>{value}</number><rtept lat="0" lon="0"/><rtept lat="0" lon="1"/></rte>')
    (f,) = parse_gpx(doc)["features"]
    assert f["properties"].get("number") == expected


@pytest.mark.parametrize(
    "source, exc",
    [
        (None, TypeError),
        (42, TypeError),
        (1.5, TypeError),
        ({"gpx": []}, TypeError),
        (["<gpx/>"], TypeError),
        ("", ValueError),
        ("   \n", ValueError),
        (b"", ValueError),
        ("not xml", SyntaxError),  # ET.ParseError
        ("<gpx", SyntaxError),
        ("<kml/>", ValueError),
        ("<gpx><wpt lat='nan' lon='0'/></gpx>", None),
        ("<gpx><wpt lat='0' lon='inf'/></gpx>", None),
        ("<gpx><wpt lat='' lon=''/></gpx>", None),
        (b"<gpx><wpt lat='1' lon='2'/></gpx>", 1),
        ("<gpx><wpt lat=' 1 ' lon='2'><ele>nan</ele><time></time></wpt></gpx>", 1),
    ],
)
def test_parse_gpx_boundary_inputs(source, exc):
    if isinstance(exc, type):
        with pytest.raises(exc):
            parse_gpx(source)
        return
    fc = parse_gpx(source)
    json.dumps(fc, allow_nan=False)
    assert len(fc["features"]) == (exc or 0)


@pytest.mark.parametrize("path", [None, 3, "", b"x.gpx", {"p": 1}])
def test_convert_rejects_bad_paths(path):
    from gpx_to_geojson import convert

    with pytest.raises(TypeError):
        convert(path)


def test_antimeridian_rejected_route_and_track():
    rte = gpx('<rte><rtept lat="0" lon="179"/><rtept lat="0" lon="-179"/></rte>')
    trk = gpx('<trk><trkseg><trkpt lat="0" lon="179"/><trkpt lat="0" lon="-179"/></trkseg></trk>')
    for doc in (rte, trk):
        with pytest.raises(ValueError, match="antimeridian"):
            parse_gpx(doc)


def test_nonfinite_elevation_is_missing_and_json_strict():
    pts = "".join(
        f'<trkpt lat="30" lon="31.{i}"><ele>{e}</ele></trkpt>' for i, e in enumerate(["NaN", "inf", "1e999"])
    )
    fc = parse_gpx(gpx(f"<trk><trkseg>{pts}</trkseg></trk>"))
    assert "elevation_min_m" not in fc["features"][0]["properties"]
    assert all(len(c) == 2 for c in fc["features"][0]["geometry"]["coordinates"])
    json.dumps(fc, allow_nan=False)


def test_collapsed_lines_skipped():
    same = '<trkpt lat="30" lon="31"/><trkpt lat="30" lon="31"/>'
    move = '<trkpt lat="30" lon="31"/><trkpt lat="30.001" lon="31"/>'
    fc = parse_gpx(
        gpx(
            '<rte><rtept lat="1" lon="1"/><rtept lat="1" lon="1"/></rte>'
            f"<trk><trkseg>{same}</trkseg><trkseg>{move}</trkseg></trk>"
        )
    )
    assert [f["properties"]["kind"] for f in fc["features"]] == ["track"]
    assert fc["features"][0]["geometry"]["type"] == "LineString"
    assert fc["features"][0]["properties"]["segments"] == 1


def test_not_gpx_and_empty():
    with pytest.raises(ValueError):
        parse_gpx("<kml/>")
    assert parse_gpx(gpx(""))["features"] == []


def test_cli_roundtrip_and_errors(tmp_path, capsys):
    src = tmp_path / "a.gpx"
    src.write_text(TRACK, encoding="utf-8")
    out = tmp_path / "a.geojson"
    assert main([str(src), "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["features"][0]["properties"]["kind"] == "track"
    assert main([str(tmp_path / "missing.gpx")]) == 1
    bad = tmp_path / "bad.gpx"
    bad.write_text("<gpx", encoding="utf-8")
    assert main([str(bad)]) == 1
    assert main([str(src), "-o", str(tmp_path / "no-such-dir" / "x.geojson")]) == 1
    assert "error" in capsys.readouterr().err
