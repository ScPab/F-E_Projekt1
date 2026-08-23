"""Aufgabe 4 — Abnahme: Rückkanal-Event schreiben und zurücklesen.

Das Event wird in einen **isolierten Named Graph** geschrieben (im ``finally``
per ``DROP GRAPH`` verworfen) und per SPARQL wieder ausgelesen: Annotation
vorhanden, alle Proben als ``oa:hasTarget``, Hypothese from→to korrekt, und die
**RDF-star-Kern-Aussage** abfragbar. Skip ohne Fuseki (Fixtures übernehmen das).
"""

from __future__ import annotations

import pytest

from wissensnetz import feedback as fb
from wissensnetz.config import PREFIXES
from wissensnetz.graphstore import GraphStore

TEST_USER = "pytest-nvaldes"
TARGET = "http://purl.obolibrary.org/obo/NCIT_PanNET"  # ncit:PanNET


def _event() -> fb.SelectionEvent:
    return fb.SelectionEvent(
        user=TEST_USER,
        samples=["TCGA-2J-AAB1", "TCGA-3A-AAL5", "TCGA-HZ-A4BH"],
        hypothesis=fb.Hypothesis(
            from_="ncit:PAAD", to="ncit:PanNET",
            note="Common fate", tag="reclassification",
        ),
        view="gene-tSNE <-> miRNA-tSNE",
        morph_param=1.0,
        confidence=0.7,
        timestamp="2026-08-20T14:12:00",
    )


@pytest.fixture()
def feedback_graph(store: GraphStore):
    """Schreibt ein Event und räumt den Nutzer-Graph danach wieder ab."""
    event = _event()
    graph = fb.write_feedback(store, event)
    try:
        yield store, graph, event
    finally:
        store.update(f"DROP GRAPH <{graph}>")


def test_graph_iri_scheme() -> None:
    assert fb.graph_iri_for("nvaldes") == "http://databridge.hka/graph/user/nvaldes"


def test_annotation_written(feedback_graph) -> None:
    store, graph, _ = feedback_graph
    assert store.ask(
        PREFIXES + f"ASK {{ GRAPH <{graph}> {{ ?a a db:ExpertFinding, oa:Annotation }} }}"
    )


def test_all_samples_are_targets(feedback_graph) -> None:
    store, graph, event = feedback_graph
    rows = store.query(
        PREFIXES
        + f"SELECT ?t WHERE {{ GRAPH <{graph}> {{ ?a a db:ExpertFinding ; oa:hasTarget ?t }} }}"
    )
    assert len(rows) == len(event.samples)


def test_hypothesis_from_to(feedback_graph) -> None:
    store, graph, _ = feedback_graph
    rows = store.query(
        PREFIXES
        + f"""
        SELECT ?from ?to WHERE {{ GRAPH <{graph}> {{
            ?a db:hypothesis ?h . ?h db:from ?from ; db:to ?to . }} }}
        """
    )
    assert len(rows) == 1
    assert rows[0]["from"] == "http://purl.obolibrary.org/obo/NCIT_PAAD"
    assert rows[0]["to"] == TARGET


def test_rdf_star_core_assertion(feedback_graph) -> None:
    # SPARQL-star: Provenienz/Konfidenz direkt an << sample db:reclassifiedAs to >>.
    store, graph, event = feedback_graph
    rows = store.query(
        PREFIXES
        + f"""
        SELECT ?s ?conf WHERE {{ GRAPH <{graph}> {{
            << ?s db:reclassifiedAs <{TARGET}> >> prov:wasDerivedFrom ?anno ;
                                                   db:confidence ?conf .
        }} }}
        """
    )
    assert len(rows) == len(event.samples)
    assert {float(r["conf"]) for r in rows} == {0.7}


def test_list_findings_and_reclassifications(feedback_graph) -> None:
    store, _, event = feedback_graph
    findings = fb.list_findings(store, user=event.user)
    assert len(findings) == 1
    f = findings[0]
    assert f["hypothesis"]["to"] == TARGET
    assert len(f["targets"]) == len(event.samples)

    recls = fb.reclassifications(store, user=event.user)
    assert len(recls) == len(event.samples)
    assert all(r["reclassified_as"] == TARGET for r in recls)


def test_sample_selection_event_json_roundtrip(store: GraphStore) -> None:
    # Das mitgelieferte Beispiel-Event laden, schreiben, zählen, aufräumen.
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data" / "sample" / "selection_event.json"
    event = fb.SelectionEvent.from_json_file(path)
    event.user = "pytest-sample-user"
    graph = fb.write_feedback(store, event)
    try:
        recls = fb.reclassifications(store, user=event.user)
        assert len(recls) == 6  # sechs PAAD-Proben aus Fallstudie 1
    finally:
        store.update(f"DROP GRAPH <{graph}>")
