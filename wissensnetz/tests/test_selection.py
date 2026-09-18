"""Aufgabe 13 — Abnahme: Auswahl-Manifeste im Named Graph, Wissensbestand im
Default-Graph.

Muster wie ``test_feedback.py``: die Manifeste werden in **isolierte** Named
Graphs geschrieben und im ``finally`` per ``drop_selection`` wieder verworfen,
Skip ohne erreichbares Fuseki (übernimmt die ``store``-Fixture).

Der wichtigste Test der Aufgabe ist
:func:`test_selections_do_not_see_each_other`: zwei Auswahlen mit
**überlappenden** Fällen, und jede sieht nur ihre eigenen. Genau das ist der
Unterschied zu ``all_cases(store)``, das den ganzen Store sieht.
"""

from __future__ import annotations

import re

import pytest
from rdflib import RDF, Graph, Namespace

from wissensnetz import enrichment
from wissensnetz import selection as sel
from wissensnetz.config import PREFIXES
from wissensnetz.graphstore import GraphStore

DB = Namespace("http://databridge.hka/onto#")
INSTANCE = "http://databridge.hka/instance/"

# Die vier Fälle der Beispiel-ABox (data/sample/cases_brca_sample.ttl).
CASE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
)

SEL_A = "pytest-selection-a"
SEL_B = "pytest-selection-b"


def _submitter_ids(store: GraphStore, case_ids: tuple[str, ...]) -> list[str]:
    """``db:submitterId`` zu den gegebenen Case-IRIs — so, wie der Mediator sie
    an :func:`write_selection` übergibt (Barcodes, nicht IRIs)."""
    values = " ".join(f"<{INSTANCE}case/{c}>" for c in case_ids)
    rows = store.query(
        PREFIXES
        + f"SELECT ?sid WHERE {{ VALUES ?c {{ {values} }} ?c db:submitterId ?sid }} ORDER BY ?sid"
    )
    return [r["sid"] for r in rows]


def _sample_ids(store: GraphStore, case_ids: tuple[str, ...]) -> list[str]:
    """Die ``sample_id``-Kennungen der Proben dieser Fälle (aus der Sample-IRI
    zurückgelesen) — ebenfalls die Form, die der Mediator übergibt."""
    values = " ".join(f"<{INSTANCE}case/{c}>" for c in case_ids)
    rows = store.query(
        PREFIXES
        + f"SELECT ?s WHERE {{ VALUES ?c {{ {values} }} ?c db:hasSample ?s }} ORDER BY ?s"
    )
    return [r["s"].rsplit("/", 1)[-1] for r in rows]


@pytest.fixture()
def two_selections(loaded_store: GraphStore):
    """Zwei Auswahlen mit **überlappenden** Fällen (Fall 2 und 3 in beiden)."""
    store = loaded_store
    a_cases, b_cases = CASE_IDS[:3], CASE_IDS[1:]
    sel.write_selection(
        store,
        SEL_A,
        source="gdc",
        cohorts=["TCGA-BRCA"],
        modality="gene_expression",
        attributes=["sex_at_birth", "tumor_stage"],
        submitter_ids=_submitter_ids(store, a_cases),
        sample_ids=_sample_ids(store, a_cases),
        timestamp="2026-09-17T10:00:00+00:00",
    )
    sel.write_selection(
        store,
        SEL_B,
        source="gdc",
        cohorts=["TCGA-BRCA", "TCGA-KIRC"],
        modality="gene_expression",
        attributes=["race"],
        submitter_ids=_submitter_ids(store, b_cases),
        sample_ids=_sample_ids(store, b_cases),
        timestamp="2026-09-17T11:00:00+00:00",
    )
    try:
        yield store, a_cases, b_cases
    finally:
        sel.drop_selection(store, SEL_A)
        sel.drop_selection(store, SEL_B)


# --------------------------------------------------------------------------
# Manifest (ohne Store)
# --------------------------------------------------------------------------
def test_graph_iri_scheme() -> None:
    assert sel.graph_iri_for_selection("abc123") == (
        "http://databridge.hka/graph/selection/abc123"
    )


def test_sample_iri_matches_mediator_rule() -> None:
    """Die Bildungsregel ist die Naht zum Mediator-Mapping
    (``INSTANCE_BASE + "sample/" + _slug(sample_id)``,
    ``mediator/app/semantic/mapping.py`` Zeile 287). Ändert sie sich dort,
    muss dieser Test rot werden — sonst zeigt das Manifest ins Leere."""

    def mediator_slug(value: str) -> str:
        # Wortgleiche Kopie von mapping.py::_slug (Zeile 201) — bewusst
        # dupliziert statt importiert: kein Import aus mediator/ (CLAUDE.md).
        return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"

    for raw in ("TCGA-2J-AAB1-01A", "abcd-1234", " spaced id ", "kräftig/1", ""):
        assert sel.sample_iri(raw) == f"{INSTANCE}sample/{mediator_slug(raw)}"

    # Eine bereits vollständige IRI wird unverändert übernommen.
    iri = f"{INSTANCE}sample/TCGA-2J-AAB1-01A"
    assert sel.sample_iri(iri) == iri


def test_manifest_parses_as_turtle_and_holds_expected_triples() -> None:
    turtle = sel.selection_manifest(
        "abc123",
        source="gdc",
        cohorts=["TCGA-BRCA", "TCGA-KIRC", "TCGA-BRCA"],  # Dublette fällt weg
        modality="gene_expression",
        attributes=["sex_at_birth", "tumor_stage"],
        submitter_ids=["TCGA-AA-0001", "TCGA-AA-0002"],
        sample_ids=["s-1", "s-2", "s-3"],
        timestamp="2026-09-17T10:00:00+00:00",
    )
    g = Graph()
    g.parse(data=turtle, format="turtle")

    subj = list(g.subjects(RDF.type, DB.Selection))
    assert len(subj) == 1
    s = subj[0]
    assert str(s) == f"{INSTANCE}selection/abc123"
    assert str(g.value(s, DB.selectionId)) == "abc123"
    assert str(g.value(s, DB.source)) == "gdc"
    assert str(g.value(s, DB.selectedModality)) == "gene_expression"
    assert {str(o) for o in g.objects(s, DB.selectedCohort)} == {"TCGA-BRCA", "TCGA-KIRC"}
    assert {str(o) for o in g.objects(s, DB.selectedAttribute)} == {"sex_at_birth", "tumor_stage"}
    assert {str(o) for o in g.objects(s, DB.hasMember)} == {
        f"{INSTANCE}sample/s-{i}" for i in (1, 2, 3)
    }
    assert {str(o) for o in g.objects(s, DB.selectionCase)} == {
        f"{INSTANCE}case/TCGA-AA-0001", f"{INSTANCE}case/TCGA-AA-0002"
    }
    prov_time = g.value(s, Namespace("http://www.w3.org/ns/prov#").generatedAtTime)
    assert str(prov_time) == "2026-09-17T10:00:00+00:00"


def test_manifest_without_members_is_valid_turtle() -> None:
    """Auch eine leere Auswahl muss ein gültiges Dokument ergeben (das letzte
    ';' wird zum '.')."""
    turtle = sel.selection_manifest(
        "leer", source="gdc", cohorts=[], modality="gene_expression",
        attributes=[], submitter_ids=[], sample_ids=[],
    )
    g = Graph()
    g.parse(data=turtle, format="turtle")
    assert (None, None, DB.Selection) in g


# --------------------------------------------------------------------------
# Schreiben / Auflisten / Verwerfen
# --------------------------------------------------------------------------
def test_write_then_list_finds_the_selection(two_selections) -> None:
    store, a_cases, _ = two_selections
    entries = {e["selection_id"]: e for e in sel.list_selections(store)}
    assert SEL_A in entries and SEL_B in entries

    a = entries[SEL_A]
    assert a["graph"] == sel.graph_iri_for_selection(SEL_A)
    assert a["source"] == "gdc"
    assert a["modality"] == "gene_expression"
    assert a["cohorts"] == ["TCGA-BRCA"]
    assert sorted(a["attributes"]) == ["sex_at_birth", "tumor_stage"]
    assert a["timestamp"] == "2026-09-17T10:00:00+00:00"
    assert a["cases"] == len(a_cases)
    assert a["members"] > 0


def test_write_selection_replaces_instead_of_appending(two_selections) -> None:
    """Derselbe ``selection_id`` mit weniger Mitgliedern lässt keine Altlasten
    stehen — sonst wüchse das Manifest bei jedem Aufruf."""
    store, a_cases, _ = two_selections
    sel.write_selection(
        store,
        SEL_A,
        source="gdc",
        cohorts=["TCGA-BRCA"],
        modality="gene_expression",
        attributes=["sex_at_birth", "tumor_stage"],
        submitter_ids=_submitter_ids(store, a_cases[:1]),
        sample_ids=_sample_ids(store, a_cases[:1]),
        timestamp="2026-09-17T10:00:00+00:00",
    )
    entry = next(e for e in sel.list_selections(store) if e["selection_id"] == SEL_A)
    assert entry["cases"] == 1


def test_drop_selection_keeps_the_knowledge_base(loaded_store: GraphStore) -> None:
    store = loaded_store
    sel.write_selection(
        store,
        "pytest-selection-drop",
        source="gdc",
        cohorts=["TCGA-BRCA"],
        modality="gene_expression",
        attributes=[],
        submitter_ids=_submitter_ids(store, CASE_IDS),
        sample_ids=_sample_ids(store, CASE_IDS),
    )
    assert sel.selection_exists(store, "pytest-selection-drop")
    before = len(enrichment.all_cases(store))

    sel.drop_selection(store, "pytest-selection-drop")

    assert not sel.selection_exists(store, "pytest-selection-drop")
    assert not any(
        e["selection_id"] == "pytest-selection-drop" for e in sel.list_selections(store)
    )
    # Der Wissensbestand im Default-Graph bleibt unangetastet.
    assert len(enrichment.all_cases(store)) == before
    assert store.ask(
        PREFIXES + f"ASK {{ <{INSTANCE}case/{CASE_IDS[0]}> a db:Case }}"
    )
    # Zweiter Aufruf darf nicht scheitern (DROP SILENT).
    sel.drop_selection(store, "pytest-selection-drop")


# --------------------------------------------------------------------------
# Begrenzte Lesefunktion — der wichtigste Test der Aufgabe
# --------------------------------------------------------------------------
def test_selections_do_not_see_each_other(two_selections) -> None:
    """Zwei Auswahlen mit überlappenden Fällen: jede sieht nur ihre eigenen.

    Das ist der Unterschied zu ``all_cases(store)``, das den gesamten Store
    sieht — und der Grund, warum die ``obs`` eines ``.h5ad`` nicht mehr von
    dem abhängt, was zufällig sonst noch geladen wurde.
    """
    store, a_cases, b_cases = two_selections
    expected_a = {f"{INSTANCE}case/{c}" for c in a_cases}
    expected_b = {f"{INSTANCE}case/{c}" for c in b_cases}

    got_a = {c["case_iri"] for c in enrichment.cases_for_selection(store, SEL_A)}
    got_b = {c["case_iri"] for c in enrichment.cases_for_selection(store, SEL_B)}

    assert got_a == expected_a
    assert got_b == expected_b
    # Die Überlappung ist gewollt, die Abgrenzung auch:
    assert got_a & got_b == expected_a & expected_b
    assert got_a != got_b
    # …und beide sind echte Teilmengen dessen, was der ganze Store hergibt.
    all_iris = {c["case_iri"] for c in enrichment.all_cases(store)}
    assert got_a < all_iris
    assert got_b <= all_iris


def test_cases_for_selection_has_the_same_shape_as_all_cases(two_selections) -> None:
    """Gleiche Schlüssel wie ``all_cases`` — ``build_obs`` im Mediator bleibt
    dadurch unverändert (HANDOFF, P3)."""
    store, _, _ = two_selections
    limited = enrichment.cases_for_selection(store, SEL_A)
    full = {c["case_iri"]: c for c in enrichment.all_cases(store)}
    assert limited
    # Einwertige Felder müssen identisch sein; bei mehreren Diagnosen je Fall
    # ist "erste Diagnose gewinnt" nicht über beide Abfragen hinweg garantiert.
    single_valued = (
        "submitter_id", "project_id", "sex_at_birth", "race", "ethnicity", "vital_status",
    )
    for c in limited:
        reference = full[c["case_iri"]]
        assert set(c) == set(reference)
        for key in single_valued:
            assert c[key] == reference[key]


def test_cases_for_selection_is_tolerant(two_selections) -> None:
    """Fehlende Werte sind ``None``, keine Exception — und eine unbekannte
    Auswahl liefert schlicht eine leere Liste."""
    store, _, _ = two_selections
    assert enrichment.cases_for_selection(store, "gibt-es-nicht") == []
    for c in enrichment.cases_for_selection(store, SEL_A):
        assert c["case_iri"]
        assert "sex_at_birth" in c and "tumor_stage" in c


def test_manifest_case_iris_point_into_the_knowledge_base(two_selections) -> None:
    """``write_selection`` löst ``submitter_id`` über den Store zur echten
    Case-IRI auf — der Mediator bildet sie aus ``case_id``, nicht aus dem
    Barcode, sie lässt sich also nicht ausrechnen."""
    store, a_cases, _ = two_selections
    graph = sel.graph_iri_for_selection(SEL_A)
    rows = store.query(
        PREFIXES
        + f"SELECT ?case WHERE {{ GRAPH <{graph}> {{ ?s db:selectionCase ?case }} }}"
    )
    assert {r["case"] for r in rows} == {f"{INSTANCE}case/{c}" for c in a_cases}
