"""GPX -> GeoJSON conversion.

GPX coordinates are WGS84 (EPSG:4326). GeoJSON output keeps (lon, lat[, elevation])
order as required by RFC 7946. Distances are geodesic, computed on the WGS84
ellipsoid with ``pyproj.Geod`` (metres); durations are seconds.
"""

from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.parsers import expat

from pyproj import CRS
from shapely.geometry import LineString, MultiLineString, Point, mapping

GEOD = CRS.from_epsg(4326).get_geod()  # WGS84 ellipsoid


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _text(el, name):
    for c in _children(el, name):
        if c.text and c.text.strip():
            return c.text.strip()
    return None


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


_FRACTION = re.compile(r"(?<=:\d\d)[.,](\d+)")


def _normalize_fraction(value):
    """Fractional seconds as exactly six digits: ``datetime.fromisoformat`` on
    Python < 3.11 accepts only 3 or 6 digits (and no comma separator)."""
    return _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), value, count=1)


def _parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(_normalize_fraction(value.strip()).replace("Z", "+00:00"))
        if dt.tzinfo is None:  # GPX times are UTC by specification
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):  # malformed, or out of range once shifted to UTC
        return None


# Standard GPX 1.1 metadata (``ele`` and ``time`` are handled separately).
# Numeric fields are converted; invalid or non-finite numbers are dropped.
WPT_TEXT = ("name", "cmt", "desc", "src", "sym", "type", "fix")
WPT_NUM = ("magvar", "geoidheight", "sat", "hdop", "vdop", "pdop", "ageofdgpsdata", "dgpsid")
LINE_TEXT = ("name", "cmt", "desc", "src", "type")
LINE_NUM = ("number",)
INTS = {"sat", "dgpsid", "number"}


# GPX integer fields are xsd:nonNegativeInteger. At most 15 digits keeps the
# value exactly representable as a JSON/float number (below 2**53).
INT_RE = re.compile(r"\+?[0-9]{1,15}")


def _number(value, name):
    """Validated number for GPX field ``name``, or None when invalid/unsupported."""
    if not isinstance(value, str):
        return None
    if name in INTS:
        return int(value) if INT_RE.fullmatch(value) else None
    try:
        num = float(value)
    except ValueError:
        return None
    return num if math.isfinite(num) else None


def _links(el):
    links = []
    for link in _children(el, "link"):
        href = link.attrib.get("href", "").strip()
        if href:
            links.append({k: v for k, v in (("href", href), ("text", _text(link, "text")), ("type", _text(link, "type"))) if v})
    return links


def _meta(el, text_fields, num_fields):
    """Standard GPX metadata of ``el`` that is present, as JSON-safe values."""
    meta = {f: _text(el, f) for f in text_fields if _text(el, f) is not None}
    for f in num_fields:
        num = _number(_text(el, f), f)
        if num is not None:
            meta[f] = num
    if _links(el):
        meta["links"] = _links(el)
    return meta


def _point(el):
    """Return (lon, lat, ele, time, meta), or None when the position is invalid."""
    try:
        lat, lon = float(el.attrib["lat"]), float(el.attrib["lon"])
    except (KeyError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    try:
        ele = float(_text(el, "ele")) if _text(el, "ele") is not None else None
    except ValueError:
        ele = None
    if ele is not None and not math.isfinite(ele):  # NaN/inf are not valid JSON
        ele = None
    return lon, lat, ele, _parse_time(_text(el, "time")), _meta(el, WPT_TEXT, WPT_NUM)


def _points(el, name):
    return [p for p in map(_point, _children(el, name)) if p]


def _usable(points):
    """True when the points form a valid, non-collapsed line.

    Raises ValueError for lines crossing the antimeridian (a jump of more than
    180 degrees of longitude between consecutive points), which GeoJSON cannot
    represent as one plain LineString.
    """
    if len({(p[0], p[1]) for p in points}) < 2:  # stationary: zero-length line
        return False
    for a, b in zip(points, points[1:]):
        if abs(a[0] - b[0]) > 180:
            raise ValueError("line crosses the antimeridian (180 degrees longitude); not supported")
    geom = LineString([(p[0], p[1]) for p in points])
    return geom.is_valid and not geom.is_empty


def _length(points):
    """Geodesic length in metres on the WGS84 ellipsoid."""
    return GEOD.line_length([p[0] for p in points], [p[1] for p in points])


def _stats(segments):
    """Distance, time and elevation summary for a list of point lists."""
    allpts = [p for s in segments for p in s]
    # Distance is summed per segment: gaps between segments are not travelled.
    stats = {"distance_m": round(sum(_length(s) for s in segments), 3)}
    times = [p[3] for p in allpts if p[3] is not None]
    if times:
        stats["start_time"] = _iso(min(times))
        stats["end_time"] = _iso(max(times))
    if len(times) >= 2:
        stats["duration_s"] = (max(times) - min(times)).total_seconds()
    eles = [p[2] for p in allpts if p[2] is not None]
    if eles:
        stats["elevation_min_m"] = min(eles)
        stats["elevation_max_m"] = max(eles)
    return stats


def _coords(points):
    # Always 2D [lon, lat]: RFC 7946 defines a third value as WGS84 ellipsoidal
    # height, whereas GPX <ele> is normally height above mean sea level. Elevation
    # is therefore kept as a property (``ele`` / ``elevations``), never as a coordinate.
    return [(p[0], p[1]) for p in points]


def _vertex_props(segments, multi):
    """Per-vertex arrays (``None`` where missing): ``times``, ``elevations`` and,
    for each standard point field present on any vertex, ``point_<field>``
    (e.g. ``point_name`` for named route points). Nested per segment if ``multi``."""
    arrays = {
        "times": [[_iso(p[3]) for p in s] for s in segments],
        "elevations": [[p[2] for p in s] for s in segments],
    }
    for f in (*WPT_TEXT, *WPT_NUM, "links"):
        if any(f in p[4] for s in segments for p in s):
            arrays[f"point_{f}"] = [[p[4].get(f) for p in s] for s in segments]
    if not multi:
        arrays = {k: v[0] for k, v in arrays.items()}
    return arrays


def _feature(geom, props):
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


def _refuse_entity(*_args):
    raise ValueError("GPX with XML entity declarations is not supported")


def _fromstring(source):
    """Parse XML, refusing entity declarations (GPX never needs them; they allow
    entity-expansion blow-ups such as the "billion laughs" attack)."""
    scan = expat.ParserCreate()
    scan.EntityDeclHandler = _refuse_entity
    try:
        scan.Parse(source, True)
    except expat.ExpatError:
        pass  # malformed XML: ElementTree below reports it as ParseError
    return ET.fromstring(source)


def parse_gpx(source: str) -> dict:
    """Convert GPX XML text to a GeoJSON FeatureCollection (dict).

    Waypoints become Points, routes LineStrings and tracks LineStrings (one
    segment) or MultiLineStrings. Lines with fewer than two valid points and
    points with invalid coordinates are skipped, as are collapsed lines (all
    positions identical). Non-finite elevations are treated as missing. Lines
    crossing the antimeridian raise ValueError. Standard GPX fields (name, cmt,
    desc, src, link, sym, type, number, fix, sat, dop values, ...) are kept as
    properties; route/track point fields as per-vertex ``point_<field>`` arrays.
    ``<extensions>`` are not converted.

    ``source`` must be a non-empty ``str`` or UTF-8 ``bytes``; any other type
    raises TypeError and blank input raises ValueError.
    """
    if isinstance(source, (bytes, bytearray)):
        source = bytes(source)
    elif not isinstance(source, str):
        raise TypeError(f"GPX source must be str or bytes, not {type(source).__name__}")
    if not source.strip():
        raise ValueError("empty GPX input")
    root = _fromstring(source)
    if _local(root.tag) != "gpx":
        raise ValueError("not a GPX document (root element is not <gpx>)")
    features = []
    for wpt in _children(root, "wpt"):
        p = _point(wpt)
        if p is None:
            continue
        props = {"kind": "waypoint", "name": None, **p[4]}
        if p[2] is not None:
            props["ele"] = p[2]
        if p[3]:
            props["time"] = _iso(p[3])
        features.append(_feature(Point(*_coords([p])[0]), props))
    for rte in _children(root, "rte"):
        pts = _points(rte, "rtept")
        if not _usable(pts):
            continue
        props = {"kind": "route", "name": None, **_meta(rte, LINE_TEXT, LINE_NUM), **_stats([pts])}
        props.update(_vertex_props([pts], False))
        features.append(_feature(LineString(_coords(pts)), props))
    for trk in _children(root, "trk"):
        segs = [s for s in (_points(g, "trkpt") for g in _children(trk, "trkseg")) if _usable(s)]
        if not segs:
            continue
        multi = len(segs) > 1
        props = {"kind": "track", "name": None, **_meta(trk, LINE_TEXT, LINE_NUM), "segments": len(segs)}
        props.update(_stats(segs))
        props.update(_vertex_props(segs, multi))
        geom = MultiLineString([_coords(s) for s in segs]) if multi else LineString(_coords(segs[0]))
        features.append(_feature(geom, props))
    fc = {"type": "FeatureCollection", "features": features}
    for meta in _children(root, "metadata"):  # document metadata as a foreign member
        info = _meta(meta, ("name", "desc", "keywords"), ())
        if _parse_time(_text(meta, "time")):
            info["time"] = _iso(_parse_time(_text(meta, "time")))
        if info:
            fc["metadata"] = info
    # Round-trip through JSON so coordinates are plain lists, as in a parsed GeoJSON file.
    return json.loads(json.dumps(fc, allow_nan=False))


def convert(path) -> dict:
    """Read a GPX file and return a GeoJSON FeatureCollection dict.

    The encoding comes from the XML declaration (default UTF-8).
    """
    return parse_gpx(Path(_path(path)).read_bytes())


def _path(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise TypeError(f"path must be a non-empty str or os.PathLike, not {value!r}")
    return value


def convert_file(src, dst) -> dict:
    """Convert GPX file ``src`` to a GeoJSON file ``dst``; returns the collection."""
    fc = convert(src)
    Path(_path(dst)).write_text(json.dumps(fc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return fc
