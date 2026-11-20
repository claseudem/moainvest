"""Generador del mapa mundial del Barómetro Global (``flask --app run build-world-map``).

Descarga los países de Natural Earth 110m (dominio público), los proyecta con
Equal Earth, simplifica los contornos (Douglas-Peucker) y escribe
``templates/moainvest/_world_map.svg``: un ``<g data-region>`` por región del
barómetro (``barometer.region_of``) con un ``<path>`` por país. El SVG se
commitea, así que la app no descarga nada al ejecutarse.
"""
from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

from app.moainvest.barometer import REGIONS, region_of

SOURCE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_admin_0_countries.geojson"
OUT = Path(__file__).resolve().parent / "templates" / "moainvest" / "_world_map.svg"
WIDTH = 1000
TOLERANCE = 0.55  # px del SVG
MIN_RING_AREA = 6.0  # px²: islas más pequeñas se omiten

_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796
_M = math.sqrt(3) / 2


def _equal_earth(lon: float, lat: float) -> tuple[float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(_M * math.sin(phi))
    t2, t6 = t * t, t**6
    x = 2 * math.sqrt(3) * lam * math.cos(t) / (3 * (9 * _A4 * t6 * t2 + 7 * _A3 * t6 + 3 * _A2 * t2 + _A1))
    y = t * (_A4 * t6 * t2 + _A3 * t6 + _A2 * t2 + _A1)
    return x, y


# Extensión de la proyección (latitudes -58..84: sin la Antártida).
_X_MAX = _equal_earth(180, 0)[0]
_Y_TOP = _equal_earth(0, 84)[1]
_Y_BOTTOM = _equal_earth(0, -58)[1]
SCALE = WIDTH / (2 * _X_MAX)
HEIGHT = round((_Y_TOP - _Y_BOTTOM) * SCALE)


def _project(lon: float, lat: float) -> tuple[float, float]:
    x, y = _equal_earth(lon, max(-58.0, min(84.0, lat)))
    return (x + _X_MAX) * SCALE, (_Y_TOP - y) * SCALE


def _simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-9
    far, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm if (dx or dy) else math.hypot(px - x1, py - y1)
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [points[0], points[-1]]
    return _simplify(points[: idx + 1], tol)[:-1] + _simplify(points[idx:], tol)


def _area(points: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def _ring_path(ring: list[list[float]]) -> str:
    pts = _simplify([_project(lon, lat) for lon, lat in ring], TOLERANCE)
    if len(pts) < 4 or _area(pts) < MIN_RING_AREA:
        return ""
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts[:-1]) + "Z"


def _polygons(geometry: dict) -> list:
    return geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]


def _poly_region(code: str, poly: list, default: str) -> str:
    """Territorios de ultramar dibujados con su metrópoli (p. ej. la Guayana Francesa)."""
    lon = sum(p[0] for p in poly[0]) / len(poly[0])
    if code == "FRA" and lon < -20:
        return "latam"
    return default


def build(source: str = SOURCE) -> Path:
    with urllib.request.urlopen(source, timeout=60) as res:  # noqa: S310 (URL fija)
        features = json.load(res)["features"]

    groups: dict[str, list[str]] = {r.slug: [] for r in REGIONS}
    for feature in features:
        props = feature["properties"]
        slug = region_of(props)
        if slug is None:
            continue
        name = props.get("NAME_ES") or props.get("NAME")
        parts: dict[str, str] = {}
        for poly in _polygons(feature["geometry"]):
            region = _poly_region(props.get("ADM0_A3"), poly, slug)
            parts[region] = parts.get(region, "") + "".join(_ring_path(ring) for ring in poly)
        for region, d in parts.items():
            if d:
                groups[region].append(f'<path d="{d}"><title>{name}</title></path>')

    body = "\n".join(
        f'  <g class="map-region" data-region="{r.slug}" tabindex="0" role="button" aria-label="{r.name}">\n    '
        + "\n    ".join(groups[r.slug])
        + "\n  </g>"
        for r in REGIONS
    )
    OUT.write_text(
        "{#- Generado por `flask --app run build-world-map` (app/moainvest/worldmap.py) a partir de\n"
        "    Natural Earth 110m (dominio público), proyección Equal Earth. No editar a mano. -#}\n"
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" class="world-map" data-world-map role="group" aria-label="Mapa mundial por regiones">\n'
        f"{body}\n</svg>\n",
        encoding="utf-8",
    )
    return OUT
