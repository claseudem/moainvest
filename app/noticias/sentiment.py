"""Sentimiento de un titular: alcista, bajista o neutral.

Clasificador por palabras clave (inglés y español), sin modelos ni servicios
externos: rápido, gratuito y explicable. Es una **estimación**; la interfaz
lo indica así. Si dos señales se contradicen, el titular queda neutral.
"""
from __future__ import annotations

import re
from typing import Literal

Sentiment = Literal["alcista", "bajista", "neutral"]

BULLISH = (
    "surge", "surges", "soar", "soars", "jump", "jumps", "rally", "rallies", "rallying", "gain", "gains",
    "rise", "rises", "rising", "climb", "climbs", "beat", "beats", "tops", "record high", "all-time high",
    "upgrade", "upgraded", "outperform", "raises guidance", "raises forecast", "boost", "boosts", "rebound",
    "rebounds", "bullish", "buy rating", "strong demand", "breakout", "higher",
    "sube", "suben", "dispara", "se dispara", "repunta", "récord", "máximos", "alcista", "gana", "ganancias",
    "mejora", "supera",
)

BEARISH = (
    "plunge", "plunges", "tumble", "tumbles", "fall", "falls", "falling", "drop", "drops", "slump", "slumps",
    "sink", "sinks", "slide", "slides", "selloff", "sell-off", "miss", "misses", "downgrade", "downgraded",
    "cut", "cuts", "lawsuit", "probe", "investigation", "warns", "warning", "layoffs", "crash", "crashes",
    "bearish", "lower", "weak", "loses", "losses", "decline", "declines", "underperform", "fears", "short seller",
    "shaky", "concerns", "worries", "jitters",
    "cae", "caen", "cayó", "se desploma", "desplome", "pérdidas", "baja", "bajista", "recorta", "demanda judicial",
    "advierte", "despidos",
)


def _matches(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", text)]


def signals(title: str) -> dict[str, list[str]]:
    """Palabras del titular que lo empujan a alcista o bajista (para explicarlo en la UI)."""
    text = title.lower()
    return {"alcistas": _matches(text, BULLISH), "bajistas": _matches(text, BEARISH)}


def classify(title: str) -> Sentiment:
    found = signals(title)
    up, down = len(found["alcistas"]), len(found["bajistas"])
    if up > down:
        return "alcista"
    if down > up:
        return "bajista"
    return "neutral"
