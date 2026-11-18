import argparse
import json
import sys

from .core import convert


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="gpx-to-geojson",
        description="Convert GPX tracks, routes and waypoints to GeoJSON (WGS84, lon/lat order).",
    )
    ap.add_argument("gpx", help="input GPX file")
    ap.add_argument("-o", "--output", help="output GeoJSON file (default: stdout)")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default 2)")
    args = ap.parse_args(argv)
    try:
        fc = convert(args.gpx)
    except (OSError, ValueError, SyntaxError) as exc:  # ET.ParseError is a SyntaxError
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(fc, indent=args.indent, ensure_ascii=False) + "\n"
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
