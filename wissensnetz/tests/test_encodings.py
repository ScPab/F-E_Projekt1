"""Aufgabe 6 — Abnahme: Encoding-Helfer für das Multi-Variablen-Morphing.

Reine numpy-Funktionen, **kein Fuseki** nötig. Das Modul liegt im Prototyp
(`prototype/mp_lite/encodings.py`) und wird per Dateipfad geladen — nicht via
``import encodings`` (das kollidiert mit Pythons stdlib-Paket ``encodings``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# numpy ist eine Prototyp-Abhängigkeit (mit bokeh installiert), keine Kern-
# Abhängigkeit von ``wissensnetz`` — ohne numpy die Tests überspringen, damit die
# Suite auch ohne Prototyp-Extras grün bleibt (wie die Fuseki-Skips).
np = pytest.importorskip("numpy")

_ENC_PATH = (
    Path(__file__).resolve().parents[1] / "prototype" / "mp_lite" / "encodings.py"
)
_spec = importlib.util.spec_from_file_location("mp_lite_encodings_test", _ENC_PATH)
enc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enc)


# --- is_encodable ---------------------------------------------------------
def test_is_encodable_needs_two_distinct() -> None:
    assert enc.is_encodable(["a", "b"]) is True
    assert enc.is_encodable(["a", "a", "b"]) is True
    # 0 oder 1 distinct Nicht-Null-Wert -> nicht morphbar
    assert enc.is_encodable([]) is False
    assert enc.is_encodable(["a", "a", "a"]) is False
    assert enc.is_encodable([None, "--", ""]) is False
    assert enc.is_encodable(["a", "--", None]) is False  # nur 1 echter Wert


# --- circular_encoding ----------------------------------------------------
def test_circular_encoding_shape_and_origin_for_missing() -> None:
    values = ["a", "b", None, "--", ""]
    pos = enc.circular_encoding(values)
    assert isinstance(pos, np.ndarray)
    assert pos.shape == (5, 2)
    # fehlende Werte -> Ursprung
    for j in (2, 3, 4):
        assert np.allclose(pos[j], [0.0, 0.0])
    # vorhandene Werte -> nicht im Ursprung (auf dem Einheitskreis)
    assert not np.allclose(pos[0], [0.0, 0.0])
    assert np.isclose(np.linalg.norm(pos[0]), 1.0)


def test_circular_encoding_same_class_same_point() -> None:
    pos = enc.circular_encoding(["x", "y", "x"])
    assert np.allclose(pos[0], pos[2])   # gleiche Klasse -> gleiche Position
    assert not np.allclose(pos[0], pos[1])


def test_circular_encoding_radius() -> None:
    pos = enc.circular_encoding(["a", "b"], radius=5.0)
    assert np.isclose(np.linalg.norm(pos[0]), 5.0)


def test_circular_encoding_empty_all_origin() -> None:
    pos = enc.circular_encoding([None, "--"])
    assert pos.shape == (2, 2)
    assert np.allclose(pos, 0.0)


# --- linear_encoding ------------------------------------------------------
def test_linear_encoding_vertical_axis_and_missing() -> None:
    pos = enc.linear_encoding([0.0, 10.0, None], dir="ver")
    assert pos.shape == (3, 2)
    assert np.allclose(pos[:, 0], 0.0)          # x bleibt 0 bei "ver"
    assert np.isclose(pos[0, 1], -1.0)          # Min -> -span
    assert np.isclose(pos[1, 1], 1.0)           # Max -> +span
    assert np.allclose(pos[2], [0.0, 0.0])      # fehlend -> Ursprung


def test_linear_encoding_horizontal() -> None:
    pos = enc.linear_encoding([1.0, 3.0], dir="hor")
    assert np.allclose(pos[:, 1], 0.0)          # y bleibt 0 bei "hor"
    assert np.isclose(pos[0, 0], -1.0)
    assert np.isclose(pos[1, 0], 1.0)


def test_linear_encoding_non_numeric_is_missing() -> None:
    # Nicht-konvertierbare Strings zählen wie fehlend (-> Ursprung).
    pos = enc.linear_encoding(["low", "high"])
    assert np.allclose(pos, 0.0)
