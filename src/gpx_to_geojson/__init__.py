"""Convert GPX tracks, routes and waypoints to GeoJSON."""

from .core import convert, convert_file, parse_gpx

__all__ = ["convert", "convert_file", "parse_gpx"]
__version__ = "0.1.0"
