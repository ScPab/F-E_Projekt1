"""Aufgabe 2 — Abnahme: Beispiel-ABox laden und erwartete Cases/Diagnosen lesen."""

from __future__ import annotations

from wissensnetz.config import PREFIXES
from wissensnetz.graphstore import GraphStore

EXPECTED_SUBMITTER_IDS = {"TCGA-A1-A0SB", "TCGA-A1-A0SD", "TCGA-A1-A0SE", "TCGA-A1-A0SH"}


def test_load_and_count_cases(loaded_store: GraphStore) -> None:
    rows = loaded_store.query(
        PREFIXES + "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a db:Case }"
    )
    assert int(rows[0]["n"]) == 4


def test_case_submitter_ids(loaded_store: GraphStore) -> None:
    rows = loaded_store.query(
        PREFIXES + "SELECT ?sid WHERE { ?c a db:Case ; db:submitterId ?sid }"
    )
    assert {r["sid"] for r in rows} == EXPECTED_SUBMITTER_IDS


def test_diagnosis_labels(loaded_store: GraphStore) -> None:
    rows = loaded_store.query(
        PREFIXES
        + "SELECT ?label WHERE { ?d a db:Diagnosis ; db:primaryDiagnosisLabel ?label }"
    )
    labels = {r["label"] for r in rows}
    assert "Infiltrating duct carcinoma, NOS" in labels
    assert "Lobular carcinoma, NOS" in labels
    assert len(rows) == 4


def test_case_diagnosis_join(loaded_store: GraphStore) -> None:
    # Fall -> Diagnose -> Label über die ObjectProperty db:hasDiagnosis.
    rows = loaded_store.query(
        PREFIXES
        + """
        SELECT ?sid ?label WHERE {
            ?c a db:Case ; db:submitterId ?sid ; db:hasDiagnosis ?d .
            ?d db:primaryDiagnosisLabel ?label .
        }
        """
    )
    pairs = {(r["sid"], r["label"]) for r in rows}
    assert ("TCGA-A1-A0SB", "Infiltrating duct carcinoma, NOS") in pairs
    assert ("TCGA-A1-A0SH", "Adenocarcinoma, NOS") in pairs


def test_load_turtle_from_text(store: GraphStore) -> None:
    # Roh-Text (statt Pfad) laden und wieder auslesen.
    store.load_turtle(
        """@prefix db: <http://databridge.hka/onto#> .
        <http://databridge.hka/instance/case/UNITTEST-1> a db:Case ;
            db:submitterId "UNITTEST-1" .""",
    )
    assert store.ask(
        PREFIXES
        + 'ASK { <http://databridge.hka/instance/case/UNITTEST-1> db:submitterId "UNITTEST-1" }'
    )
