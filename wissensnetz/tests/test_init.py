"""Aufgabe 1 — Abnahme: Dataset existiert und TBox-Klassen sind abfragbar."""

from __future__ import annotations

from wissensnetz.config import PREFIXES
from wissensnetz.graphstore import GraphStore
from wissensnetz.init import initialize, tbox_loaded

EXPECTED_CLASSES = {
    "http://databridge.hka/onto#Project",
    "http://databridge.hka/onto#Case",
    "http://databridge.hka/onto#Demographic",
    "http://databridge.hka/onto#Diagnosis",
}


def test_dataset_exists_after_init(store: GraphStore) -> None:
    assert store.dataset_exists()


def test_initialize_is_idempotent(store: GraphStore) -> None:
    # Zweiter Lauf darf nicht scheitern und meldet die TBox als vorhanden.
    report = initialize(store)
    assert report["dataset"] == store.settings.dataset
    assert report["tbox"].startswith("skipped")
    assert tbox_loaded(store)


def test_tbox_classes_queryable(store: GraphStore) -> None:
    rows = store.query(PREFIXES + "SELECT ?c WHERE { ?c a owl:Class }")
    found = {r["c"] for r in rows}
    assert EXPECTED_CLASSES <= found


def test_marker_class_present(store: GraphStore) -> None:
    assert store.ask(PREFIXES + "ASK { db:Case a owl:Class }")
