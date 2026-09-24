"""Encoding-Helfer für das Multi-Variablen-Morphing in MP-lite (Aufgabe 6).

Sinngemäße, eigenständige numpy-Portierung der beiden Encoding-Ideen aus der
Oviedo-Referenz (``demo.py``: ``circularEncoding`` / ``linearEnc``), ohne
fremden Code oder sklearn-Pflicht:

* :func:`circular_encoding` — eine Kategorie-Variable auf einen Kreis: jede
  distinct Klasse bekommt einen gleichmäßig verteilten Punkt, jede Probe landet
  auf der Position ihrer Klasse.
* :func:`linear_encoding` — eine numerische Variable MinMax-skaliert auf eine
  Achse (vertikal/horizontal).
* :func:`is_encodable` — ob eine Variable überhaupt morphen kann (≥ 2 distinct
  Nicht-Null-Werte).

Fehlende Werte (``None``, ``""``, ``"--"``, ``NaN``) landen im Ursprung ``(0, 0)``
bzw. tragen nichts zur Achse bei — so bleibt die App tolerant, solange
Mediator/Wrapper viele Felder noch nicht liefern (siehe HANDOFF.md).
Alle Funktionen liefern ``(n, 2)``-``float``-Arrays in der Reihenfolge der
Eingabe.

English: Encoding helpers for the multi-variable morphing in MP-lite (task
6).

A faithful, standalone numpy port of the two encoding ideas from the Oviedo
reference (``demo.py``: ``circularEncoding`` / ``linearEnc``), without
third-party code or an sklearn requirement:

* :func:`circular_encoding` — maps a categorical variable onto a circle:
  every distinct class gets an evenly distributed point, every sample lands
  at its class's position.
* :func:`linear_encoding` — MinMax-scales a numeric variable onto an axis
  (vertical/horizontal).
* :func:`is_encodable` — whether a variable can morph at all (≥ 2 distinct
  non-null values).

Missing values (``None``, ``""``, ``"--"``, ``NaN``) land at the origin
``(0, 0)`` or contribute nothing to the axis — this keeps the app tolerant
as long as the mediator/wrapper don't yet deliver many fields (see
HANDOFF.md). All functions return ``(n, 2)`` ``float`` arrays in input
order.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

# Als "fehlend" behandelte Rohwerte (das Oviedo-Hover-"--" eingeschlossen).
# EN: Raw values treated as "missing" (including the Oviedo hover "--").
_MISSING_STRINGS = frozenset({"", "--"})


def _is_missing(v: object) -> bool:
    """True für ``None``, leere/`"--"`-Strings und ``NaN``-Floats.

    English: True for ``None``, empty/``"--"`` strings and ``NaN`` floats.
    """
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    return str(v).strip() in _MISSING_STRINGS


def is_encodable(values: Sequence[object]) -> bool:
    """True, wenn ``values`` mindestens **zwei** verschiedene Nicht-Null-Werte
    enthält — nur dann kann die Variable etwas morphen (sonst fielen alle Proben
    auf denselben Punkt bzw. den Ursprung).

    English: True if ``values`` contains at least **two** different
    non-null values — only then can the variable morph anything (otherwise
    all samples would fall on the same point or the origin).
    """
    distinct = {str(v).strip() for v in values if not _is_missing(v)}
    return len(distinct) >= 2


def circular_encoding(values: Sequence[object], *, radius: float = 1.0) -> np.ndarray:
    """Kreis-Encoding einer Kategorie-Variable.

    Die distinct Nicht-Null-Werte werden (sortiert, deterministisch) gleichmäßig
    auf einen Kreis mit Radius ``radius`` verteilt; jede Probe wird an die
    Position ihrer Klasse gesetzt. Fehlende Werte (``None``/``""``/``"--"``)
    landen im Ursprung ``(0, 0)``.

    Rückgabe: ``np.ndarray`` der Form ``(len(values), 2)``.

    English: Circular encoding of a categorical variable.

    The distinct non-null values are distributed evenly (sorted,
    deterministic) around a circle of radius ``radius``; every sample is
    placed at its class's position. Missing values (``None``/``""``/``"--"``)
    land at the origin ``(0, 0)``.

    Returns: ``np.ndarray`` of shape ``(len(values), 2)``.
    """
    n = len(values)
    pos = np.zeros((n, 2), dtype=float)
    classes = sorted({str(v).strip() for v in values if not _is_missing(v)})
    if not classes:
        return pos
    index = {c: i for i, c in enumerate(classes)}
    k = len(classes)
    for j, v in enumerate(values):
        if _is_missing(v):
            continue
        angle = 2.0 * np.pi * index[str(v).strip()] / k
        pos[j, 0] = radius * np.cos(angle)
        pos[j, 1] = radius * np.sin(angle)
    return pos


def linear_encoding(
    values: Sequence[object], dir: str = "ver", *, span: float = 1.0
) -> np.ndarray:
    """Lineares Encoding einer **numerischen** Variable.

    Die (in ``float`` konvertierbaren) Werte werden MinMax auf ``[-span, span]``
    skaliert und auf eine Achse gelegt: ``dir="ver"`` → y-Achse (Default),
    sonst → x-Achse. Fehlende oder nicht-numerische Werte tragen ``0`` bei.

    Rückgabe: ``np.ndarray`` der Form ``(len(values), 2)``.

    English: Linear encoding of a **numeric** variable.

    The values (convertible to ``float``) are MinMax-scaled onto ``[-span,
    span]`` and placed on an axis: ``dir="ver"`` → y-axis (default),
    otherwise → x-axis. Missing or non-numeric values contribute ``0``.

    Returns: ``np.ndarray`` of shape ``(len(values), 2)``.
    """
    n = len(values)
    pos = np.zeros((n, 2), dtype=float)
    nums: list[float | None] = []
    for v in values:
        if _is_missing(v):
            nums.append(None)
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            nums.append(None)  # nicht-numerisch → wie fehlend / EN: non-numeric → treated as missing
    present = [x for x in nums if x is not None]
    if not present:
        return pos
    lo, hi = min(present), max(present)
    span_range = hi - lo
    axis = 1 if dir == "ver" else 0
    for j, x in enumerate(nums):
        if x is None:
            continue
        scaled = 0.0 if span_range == 0 else ((x - lo) / span_range * 2.0 - 1.0) * span
        pos[j, axis] = scaled
    return pos
