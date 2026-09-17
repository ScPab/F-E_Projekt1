"""Aufgabe 14 — Abnahme: Upsert je Property im wachsenden Wissensbestand.

Muster wie ``test_selection.py``: self-isolating (eigene Instanz-IRIs unter
``…/instance/case/pytest-k14-*``, die im ``finally`` wieder abgeräumt werden),
Skip ohne erreichbares Fuseki (übernimmt die ``store``-Fixture).

Der entscheidende Test ist
:func:`test_upsert_replaces_only_the_delivered_property`: ein Fall wird mit
``gender`` **und** ``tumorStage`` geladen, danach nur mit ``gender`` und einem
anderen Wert. Danach muss ``db:gender`` genau **einen** Wert haben (den neuen)
und ``db:tumorStage`` **noch da** sein. Das ist der Grund für die Aufgabe:
"Fall ersetzen" würde hier das ``tumorStage`` eines früheren, reicheren Aufrufs
verlieren.
"""

from __future__ import annotations

import pytest

from wissensnetz import feedback as fb
from wissensnetz import knowledge as kn
from wissensnetz.config import DB, PREFIXES
from wissensnetz.graphstore import GraphStore

INSTANCE = "http://databridge.hka/instance/"

# Eigener Namensraum-Ausschnitt für diese Tests, damit sie einen persistenten
# Store weder stören noch von ihm abhängen.
CASE = f"{INSTANCE}case/pytest-k14-1"
OTHER_CASE = f"{INSTANCE}case/pytest-k14-2"
DEMO = f"{INSTANCE}demographic/pytest-k14-1"
OTHER_DEMO = f"{INSTANCE}demographic/pytest-k14-2"
DIAG = f"{INSTANCE}diagnosis/pytest-k14-1"
SAMPLE = f"{INSTANCE}sample/pytest-k14-1"
PROJECT = f"{INSTANCE}project/pytest-k14-PROJ"

SUBMITTER = "PYTEST-K14-0001"
OTHER_SUBMITTER = "PYTEST-K14-0002"
NCIT = "http://purl.obolibrary.org/obo/NCIT_C7950"

GENDER = f"{DB}gender"
TUMOR_STAGE = f"{DB}tumorStage"


def _turtle(*, gender: str, with_stage: bool = False, with_diagnosis: bool = False) -> str:
    """Nutzlast in der Form, die der Mediator liefert (typisierte Literale,
    Unterknoten je Demographic/Diagnosis/Sample, RDF-star fürs Alignment)."""
    stage = f'    db:tumorStage "Stage IB"^^xsd:string ;\n' if with_stage else ""
    diagnosis = ""
    star = ""
    if with_diagnosis:
        diagnosis = f"""
<{DIAG}> a db:Diagnosis ;
    db:describesCase <{CASE}> ;
    db:primaryDiagnosisLabel "Lobular carcinoma, NOS"^^xsd:string ;
    db:primaryDiagnosis <{NCIT}> .
"""
        star = f"""
@prefix gdc: <http://databridge.hka/source/gdc#> .
<< <{DIAG}> <{DB}primaryDiagnosis> <{NCIT}> >>
    prov:wasDerivedFrom gdc:submission ;
    db:confidence 1.0 .
"""
    return f"""
@prefix db:   <{DB}> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

<{PROJECT}> a db:Project ;
    db:projectId "PYTEST-K14-PROJ"^^xsd:string ;
    db:hasCase <{CASE}> .

<{CASE}> a db:Case ;
    db:submitterId "{SUBMITTER}"^^xsd:string ;
    db:belongsToProject <{PROJECT}> ;
    db:hasDemographic <{DEMO}> ;
    db:hasDiagnosis <{DIAG}> ;
    db:hasSample <{SAMPLE}> .

<{DEMO}> a db:Demographic ;
    db:isDemographicOf <{CASE}> ;
{stage}    db:gender "{gender}"^^xsd:string .

<{SAMPLE}> a db:Sample ;
    db:isSampleOf <{CASE}> ;
    db:sampleType "Primary Tumor"^^xsd:string .

<{OTHER_CASE}> a db:Case ;
    db:submitterId "{OTHER_SUBMITTER}"^^xsd:string ;
    db:belongsToProject <{PROJECT}> ;
    db:hasDemographic <{OTHER_DEMO}> .

<{OTHER_DEMO}> a db:Demographic ;
    db:gender "male"^^xsd:string .
{diagnosis}{star}"""


def _values(store: GraphStore, subject: str, prop: str) -> list[str]:
    rows = store.query(
        PREFIXES + f"SELECT ?o WHERE {{ <{subject}> <{prop}> ?o }} ORDER BY ?o"
    )
    return [r["o"] for r in rows]


def _cleanup(store: GraphStore) -> None:
    """Alles wieder entfernen, was diese Tests in den Default-Graph schreiben."""
    store.update(PREFIXES + f"""
    DELETE {{ << ?s ?p ?o >> ?ap ?av }}
    WHERE {{ << ?s ?p ?o >> ?ap ?av . FILTER(STRSTARTS(STR(?s), "{INSTANCE}") &&
             CONTAINS(STR(?s), "pytest-k14")) }}
    """)
    store.update(PREFIXES + f"""
    DELETE {{ ?s ?p ?o }}
    WHERE {{ ?s ?p ?o . FILTER(CONTAINS(STR(?s), "pytest-k14")) }}
    """)


@pytest.fixture()
def clean_store(store: GraphStore):
    """Store ohne Reste dieser Tests — vorher und nachher."""
    _cleanup(store)
    try:
        yield store
    finally:
        _cleanup(store)


# --------------------------------------------------------------------------
# Der entscheidende Test
# --------------------------------------------------------------------------
def test_upsert_replaces_only_the_delivered_property(clean_store: GraphStore) -> None:
    """Zweiter Aufruf mit weniger Attributen: der neue Wert ersetzt den alten,
    das Attribut des früheren, reicheren Aufrufs bleibt stehen."""
    store = clean_store

    # Aufruf 1: gender UND tumor_stage
    kn.load_knowledge(
        store, _turtle(gender="female", with_stage=True),
        submitter_ids=[SUBMITTER, OTHER_SUBMITTER],
        properties=[GENDER, TUMOR_STAGE],
    )
    assert _values(store, DEMO, GENDER) == ["female"]
    assert _values(store, DEMO, TUMOR_STAGE) == ["Stage IB"]

    # Aufruf 2: NUR gender, mit geändertem Wert
    kn.load_knowledge(
        store, _turtle(gender="male"),
        submitter_ids=[SUBMITTER, OTHER_SUBMITTER],
        properties=[GENDER],
    )

    # genau ein gender, und zwar der neue …
    assert _values(store, DEMO, GENDER) == ["male"]
    # … und tumor_stage aus dem ersten Aufruf lebt noch.
    assert _values(store, DEMO, TUMOR_STAGE) == ["Stage IB"]


def test_append_only_would_duplicate(clean_store: GraphStore) -> None:
    """Gegenprobe: ohne ``properties`` (= bisheriges Anhängen) entstehen genau
    die zwei Werte, wegen derer es diese Aufgabe gibt."""
    store = clean_store
    kn.load_knowledge(store, _turtle(gender="female"), submitter_ids=[SUBMITTER])
    kn.load_knowledge(store, _turtle(gender="male"), submitter_ids=[SUBMITTER])
    assert _values(store, DEMO, GENDER) == ["female", "male"]


# --------------------------------------------------------------------------
# Randfälle
# --------------------------------------------------------------------------
def test_first_load_deletes_nothing_and_does_not_raise(clean_store: GraphStore) -> None:
    """Beim ersten Ladevorgang ist der Fall noch nicht im Store; es gibt nichts
    aufzulösen und nichts zu löschen — das ist der Normalfall, kein Fehler."""
    store = clean_store
    assert not store.ask(PREFIXES + f'ASK {{ ?c db:submitterId "{SUBMITTER}" }}')
    kn.load_knowledge(
        store, _turtle(gender="female"),
        submitter_ids=[SUBMITTER], properties=[GENDER],
    )
    assert _values(store, DEMO, GENDER) == ["female"]


def test_replace_case_properties_is_a_noop_without_input(clean_store: GraphStore) -> None:
    store = clean_store
    assert kn.replace_case_properties(store, case_iris=[], properties=[GENDER]) == 0
    assert kn.replace_case_properties(store, case_iris=[CASE], properties=[]) == 0


def test_properties_none_behaves_like_load_turtle(clean_store: GraphStore) -> None:
    store = clean_store
    kn.load_knowledge(store, _turtle(gender="female"), submitter_ids=[SUBMITTER])
    assert _values(store, DEMO, GENDER) == ["female"]
    assert store.ask(PREFIXES + f"ASK {{ <{SAMPLE}> db:sampleType ?t }}")


def test_upsert_touches_only_the_named_cases(clean_store: GraphStore) -> None:
    """Der zweite Fall in derselben Nutzlast wird nicht angefasst, wenn er nicht
    in ``submitter_ids`` steht — die Eingrenzung hängt am Fall, nicht an der
    Property allein."""
    store = clean_store
    kn.load_knowledge(store, _turtle(gender="female"), submitter_ids=[SUBMITTER])
    assert _values(store, OTHER_DEMO, GENDER) == ["male"]

    kn.replace_case_properties(store, case_iris=[CASE], properties=[GENDER])

    assert _values(store, DEMO, GENDER) == []
    assert _values(store, OTHER_DEMO, GENDER) == ["male"]


def test_tbox_survives_the_upsert(clean_store: GraphStore) -> None:
    """Die TBox liegt im selben Default-Graph wie die ABox; das Löschen ist über
    ``VALUES ?case`` auf Instanz-IRIs verankert und darf sie nicht treffen."""
    store = clean_store
    kn.load_knowledge(store, _turtle(gender="female"), submitter_ids=[SUBMITTER])
    kn.replace_case_properties(
        store, case_iris=[CASE], properties=[GENDER, TUMOR_STAGE, f"{DB}sampleType"]
    )
    assert store.ask(PREFIXES + "ASK { db:Case a owl:Class }")
    assert store.ask(PREFIXES + "ASK { db:gender a owl:DatatypeProperty }")


def test_project_node_survives_the_upsert(clean_store: GraphStore) -> None:
    """Projekt-Knoten sind kohortenweit geteilt; ``db:belongsToProject`` steht
    deshalb nicht im Pfad."""
    store = clean_store
    kn.load_knowledge(store, _turtle(gender="female"), submitter_ids=[SUBMITTER])
    kn.replace_case_properties(
        store, case_iris=[CASE, OTHER_CASE], properties=[GENDER, f"{DB}projectId"]
    )
    assert store.ask(PREFIXES + f'ASK {{ <{PROJECT}> db:projectId "PYTEST-K14-PROJ" }}')
    assert store.ask(PREFIXES + f"ASK {{ <{CASE}> db:belongsToProject <{PROJECT}> }}")


def test_feedback_named_graph_survives_upsert(clean_store: GraphStore) -> None:
    """Ein Update ohne ``GRAPH``-Klausel darf nur den Default-Graph treffen.

    Nicht angenommen, sondern geprüft: Finding in einen Nutzer-Graphen
    schreiben, Upsert ausführen, Finding muss noch da sein.
    """
    store = clean_store
    event = fb.SelectionEvent(
        user="pytest-k14-user",
        samples=[SAMPLE],
        hypothesis=fb.Hypothesis(from_="ncit:PAAD", to="ncit:PanNET"),
        confidence=0.7,
    )
    graph = fb.write_feedback(store, event)
    try:
        kn.load_knowledge(
            store, _turtle(gender="female"),
            submitter_ids=[SUBMITTER], properties=[GENDER, f"{DB}confidence"],
        )
        kn.replace_case_properties(
            store, case_iris=[CASE], properties=[GENDER, f"{DB}confidence"]
        )
        assert len(fb.list_findings(store, user=event.user)) == 1
        assert len(fb.reclassifications(store, user=event.user)) == 1
    finally:
        store.update(f"DROP GRAPH <{graph}>")


# --------------------------------------------------------------------------
# Sonderfall NCIt-Alignment (db:primaryDiagnosis + RDF-star)
# --------------------------------------------------------------------------
def test_primary_diagnosis_label_also_clears_the_alignment(clean_store: GraphStore) -> None:
    """Die Property-Liste des Mediators enthält nur ``db:primaryDiagnosisLabel``.
    Der NCIt-Link und seine RDF-star-Provenienz sind dessen Anhang und müssen
    mitgehen — sonst bliebe Provenienz über eine Aussage stehen, die es nicht
    mehr gibt."""
    store = clean_store
    kn.load_knowledge(
        store, _turtle(gender="female", with_diagnosis=True),
        submitter_ids=[SUBMITTER], properties=[f"{DB}primaryDiagnosisLabel"],
    )
    assert _values(store, DIAG, f"{DB}primaryDiagnosis") == [NCIT]
    assert _star_annotations(store) == 2

    kn.replace_case_properties(
        store, case_iris=[CASE], properties=[f"{DB}primaryDiagnosisLabel"]
    )

    assert _values(store, DIAG, f"{DB}primaryDiagnosisLabel") == []
    assert _values(store, DIAG, f"{DB}primaryDiagnosis") == []
    assert _star_annotations(store) == 0
    # Die Diagnose selbst bleibt am Fall hängen (db:hasDiagnosis wird nicht
    # angefasst), nur ihre Werte sind weg.
    assert store.ask(PREFIXES + f"ASK {{ <{CASE}> db:hasDiagnosis <{DIAG}> }}")


def test_expand_properties_only_adds_the_alignment_pair() -> None:
    props = kn._expand_properties([f"{DB}gender"])
    assert props == [f"{DB}gender"]
    props = kn._expand_properties([f"{DB}primaryDiagnosisLabel"])
    assert props == [f"{DB}primaryDiagnosisLabel", f"{DB}primaryDiagnosis"]
    # CURIE-Schreibweise wird genauso erkannt.
    props = kn._expand_properties(["db:primaryDiagnosisLabel"])
    assert props == ["db:primaryDiagnosisLabel", f"{DB}primaryDiagnosis"]
    # Steht die Objekt-Property schon drin, wird sie nicht verdoppelt.
    props = kn._expand_properties([f"{DB}primaryDiagnosisLabel", f"{DB}primaryDiagnosis"])
    assert props == [f"{DB}primaryDiagnosisLabel", f"{DB}primaryDiagnosis"]


def _star_annotations(store: GraphStore) -> int:
    rows = store.query(
        PREFIXES
        + f"SELECT ?ap ?av WHERE {{ << <{DIAG}> db:primaryDiagnosis ?o >> ?ap ?av }}"
    )
    return len(rows)
