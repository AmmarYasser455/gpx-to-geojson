# Example data

`cairo.gpx` – four well-known Cairo landmarks (Great Pyramid of Giza, Cairo Tower,
Tahrir Square, Citadel of Saladin) as waypoints, plus a route visiting them in that order.

Source and licence: landmark coordinates are taken from the Wikidata items for each
landmark (property P625 "coordinate location"; Wikidata, https://www.wikidata.org, CC0 1.0
public domain), rounded to 4 decimals (roughly 10 m); the file is released under
the repository's MIT licence. The route is a straight-line sequence of those landmarks, not
a recorded or surveyed path. The file has no timestamps or elevations; those features are
exercised by small synthetic GPX documents in `tests/`.
