"""Aufgabe 3 — Abnahme: SPARQL-Anreicherung (Lesen).

Zwei Testarten:
* **Kontext** gegen die echten Beispieldaten (`loaded_store`, Projekt TCGA-BRCA).
* **Hierarchie** gegen eine **isolierte** Mini-Ontologie in einem eigenen Named
  Graph (im `finally` per `DROP GRAPH` verworfen) — so ist der
  `rdfs:subClassOf*`-Pfad bewiesen, ohne von (nicht geladenem) NCIt abzuhängen.
"""

from __future__ import annotations

import pytest

from wissensnetz import enrichment as e
from wissensnetz.graphstore import GraphStore

# Mini-Klassenhierarchie: B ⊑ A ⊑ db:Disease (alles im Test-Named-Graph).
HIER_GRAPH = "urn:wissensnetz:test:hierarchy"
HIER_A = "urn:test:hier#A"
HIER_B = "urn:test:hier#B"
HIER_TTL = f"""
@prefix db:   <http://databridge.hka/onto#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix t:    <urn:test:hier#> .
t:A rdfs:subClassOf db:Disease .
t:B rdfs:subClassOf t:A .
"""


# --- Kontext (Echtdaten) --------------------------------------------------
def test_case_context_by_submitter_id(loaded_store: GraphStore) -> None:
    ctx = e.case_context(loaded_store, "TCGA-A1-A0SB")
    assert ctx["project_id"] == "TCGA-BRCA"
    assert ctx["gender"] == "female"
    assert ctx["submitter_id"] == "TCGA-A1-A0SB"
    assert len(ctx["diagnoses"]) == 1
    diag = ctx["diagnoses"][0]
    assert diag["label"] == "Infiltrating duct carcinoma, NOS"
    assert diag["age_at_diagnosis"] == 21200
    # Alignment-Tabelle ist leer -> derzeit kein NCIt-Concept.
    assert diag["aligned_concept"] is None


def test_case_context_by_iri(loaded_store: GraphStore) -> None:
    iri = "http://databridge.hka/instance/case/44444444-4444-4444-8444-444444444444"
    ctx = e.case_context(loaded_store, iri)
    assert ctx["case_iri"] == iri
    assert ctx["gender"] == "male"
    assert ctx["diagnoses"][0]["label"] == "Adenocarcinoma, NOS"


def test_case_context_unknown_returns_empty(loaded_store: GraphStore) -> None:
    assert e.case_context(loaded_store, "DOES-NOT-EXIST") == {}


def test_diagnosis_context_by_id(loaded_store: GraphStore) -> None:
    ctx = e.diagnosis_context(loaded_store, "d-11111111")
    assert ctx["diagnosis_iri"].endswith("/diagnosis/d-11111111")
    assert ctx["label"] == "Infiltrating duct carcinoma, NOS"
    assert ctx["age_at_diagnosis"] == 21200
    assert ctx["submitter_id"] == "TCGA-A1-A0SB"
    assert ctx["aligned_concept"] is None


def test_diagnosis_context_unknown_returns_empty(loaded_store: GraphStore) -> None:
    assert e.diagnosis_context(loaded_store, "d-does-not-exist") == {}


# --- Hierarchie (isolierte Named-Graph-Fixture) ---------------------------
@pytest.fixture()
def hierarchy_store(store: GraphStore) -> GraphStore:
    store.load_turtle(HIER_TTL, graph=HIER_GRAPH)
    try:
        yield store
    finally:
        store.update(f"DROP GRAPH <{HIER_GRAPH}>")


def test_subclasses_transitive(hierarchy_store: GraphStore) -> None:
    result = e.subclasses(hierarchy_store, "db:Disease")
    assert HIER_A in result  # direkt
    assert HIER_B in result  # transitiv (B ⊑ A ⊑ Disease)


def test_subclasses_exclude_self(hierarchy_store: GraphStore) -> None:
    result = e.subclasses(hierarchy_store, "db:Disease", include_self=False)
    assert "http://databridge.hka/onto#Disease" not in result
    assert HIER_A in result and HIER_B in result


def test_superclasses_transitive(hierarchy_store: GraphStore) -> None:
    result = e.superclasses(hierarchy_store, HIER_B)
    assert HIER_A in result
    assert "http://databridge.hka/onto#Disease" in result


def test_superclasses_exclude_self(hierarchy_store: GraphStore) -> None:
    result = e.superclasses(hierarchy_store, HIER_B, include_self=False)
    assert HIER_B not in result
    assert HIER_A in result


def test_subclasses_top_level_class_has_only_self(loaded_store: GraphStore) -> None:
    # db:Case ist in der TBox top-level: subclasses == nur die Klasse selbst.
    assert e.subclasses(loaded_store, "db:Case") == ["http://databridge.hka/onto#Case"]
    assert e.subclasses(loaded_store, "db:Case", include_self=False) == []


def test_hierarchy_excludes_restriction_bnodes(loaded_store: GraphStore) -> None:
    # db:Diagnosis rdfs:subClassOf [ owl:Restriction … ] in der TBox — der
    # anonyme Restriction-Blank-Node darf NICHT als Oberklasse erscheinen.
    supers = e.superclasses(loaded_store, "db:Diagnosis")
    assert supers == ["http://databridge.hka/onto#Diagnosis"]
