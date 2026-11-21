import argparse
import json
import sys

from .core import convert, parse_gpx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="gpx-to-geojson",
        description="Convert GPX tracks, routes and waypoints to GeoJSON (WGS84, lon/lat order).",
    )
    ap.add_argument("gpx", help="input GPX file, or - to read GPX from standard input")
    ap.add_argument("-o", "--output", help="output GeoJSON file (default: stdout)")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default 2)")
    args = ap.parse_args(argv)
    try:
        if args.gpx == "-":
            fc = parse_gpx(sys.stdin.buffer.read())
        else:
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
