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
    # Alignment-Tabelle enthält seit der Mediator-Fixture-Aktualisierung einen
    # Treffer für "Infiltrating duct carcinoma, NOS" (siehe
    # ontology/alignment/ncit_primary_diagnosis.json).
    assert diag["aligned_concept"] == "http://purl.obolibrary.org/obo/NCIT_C4194"


def test_case_context_has_oviedo_fields(loaded_store: GraphStore) -> None:
    # Aufgabe 5: case_context liefert die neuen Oviedo-MP-Felder als Keys, auch
    # wenn Mediator/Wrapper sie noch nicht befüllen (Werte dürfen None sein).
    # Keine Exception, bestehende Felder bleiben intakt.
    ctx = e.case_context(loaded_store, "TCGA-A1-A0SB")
    for key in ("race", "ethnicity", "vital_status"):
        assert key in ctx  # Top-Ebene (Demographic)
    diag = ctx["diagnoses"][0]
    for key in ("tumor_stage", "morphology", "site_of_resection_or_biopsy",
                "has_metastasis"):
        assert key in diag  # pro Diagnose-Eintrag


def test_all_cases_contains_fixture_cases(loaded_store: GraphStore) -> None:
    # Aufgabe 7: Sammel-Leseabfrage liefert je Fall genau einen Eintrag mit den
    # erwarteten Keys; die BRCA-Fixture-Fälle sind enthalten. (Der Store kann
    # weitere Fälle enthalten — daher keine exakte Gesamtzahl prüfen.)
    cases = e.all_cases(loaded_store)
    assert isinstance(cases, list) and cases
    by_sid = {c["submitter_id"]: c for c in cases if c.get("submitter_id")}
    assert "TCGA-A1-A0SB" in by_sid
    brca = by_sid["TCGA-A1-A0SB"]
    assert brca["project_id"] == "TCGA-BRCA"
    assert brca["gender"] == "female"
    assert brca["primary_diagnosis"] == "Infiltrating duct carcinoma, NOS"
    # Neue Aufgabe-5-Felder als Keys vorhanden (Werte dürfen None sein).
    for key in ("race", "ethnicity", "vital_status", "tumor_stage", "morphology",
                "site_of_resection_or_biopsy", "has_metastasis"):
        assert key in brca
    # ein Eintrag je Fall (keine Duplikate durch mehrere Diagnosen)
    sids = [c["submitter_id"] for c in cases if c.get("submitter_id")]
    assert len(sids) == len(set(sids))


def test_all_cases_limit(loaded_store: GraphStore) -> None:
    limited = e.all_cases(loaded_store, limit=2)
    assert len(limited) <= 2


# --- Sample/type (Aufgabe 8) ----------------------------------------------
# Hinweis: case_context/all_cases fragen den DEFAULT-Graph ab (kein
# union-default-graph, s. UNION-Muster in test_graphstore). Ein eigener Named
# Graph wäre für diese Funktionen unsichtbar — daher wird der Test-Fall in den
# Default-Graph geladen und im finally per gezieltem DELETE wieder entfernt
# (Isolation wie bei DROP GRAPH, nur für Default-Graph-Tripel).
_SMP_CASE = "urn:test:sample#c1"
_SMP_SAMPLE = "urn:test:sample#s1"
_SMP_TTL = """
@prefix db: <http://databridge.hka/onto#> .
@prefix ex: <urn:test:sample#> .
ex:c1 a db:Case ; db:submitterId "TEST-SMP-XYZ" ; db:hasSample ex:s1 .
ex:s1 a db:Sample ; db:sampleType "Primary Tumor" .
"""


@pytest.fixture()
def sample_store(loaded_store: GraphStore) -> GraphStore:
    loaded_store.load_turtle(_SMP_TTL)  # Default-Graph
    try:
        yield loaded_store
    finally:
        loaded_store.update(f"DELETE WHERE {{ <{_SMP_CASE}> ?p ?o }}")
        loaded_store.update(f"DELETE WHERE {{ <{_SMP_SAMPLE}> ?p ?o }}")


def test_case_context_returns_sample_type(sample_store: GraphStore) -> None:
    ctx = e.case_context(sample_store, "TEST-SMP-XYZ")
    assert ctx["sample_type"] == "Primary Tumor"


def test_all_cases_returns_sample_type(sample_store: GraphStore) -> None:
    by_sid = {c["submitter_id"]: c for c in e.all_cases(sample_store) if c.get("submitter_id")}
    assert by_sid["TEST-SMP-XYZ"]["sample_type"] == "Primary Tumor"


def test_sample_type_from_fixture(loaded_store: GraphStore) -> None:
    # BRCA-Fixture liefert seit der Mediator-Fixture-Aktualisierung (Teil 2,
    # samples.sample_type -> db:hasSample/db:sampleType) echte Sample-Typen.
    # TCGA-A1-A0SD hat genau ein Sample -> deterministischer Wert; TCGA-A1-A0SB
    # hat zwei Samples (Primary Tumor + Solid Tissue Normal), daher hier nur
    # gegen den Fall mit genau einem Sample geprüft.
    ctx = e.case_context(loaded_store, "TCGA-A1-A0SD")
    assert ctx["sample_type"] == "Primary Tumor"
    brca = next(c for c in e.all_cases(loaded_store) if c.get("submitter_id") == "TCGA-A1-A0SD")
    assert brca["sample_type"] == "Primary Tumor"


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
    assert ctx["aligned_concept"] == "http://purl.obolibrary.org/obo/NCIT_C4194"


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
