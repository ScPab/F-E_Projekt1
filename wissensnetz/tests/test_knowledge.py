"""Aufgabe 14 — Abnahme: Upsert je Property im wachsenden Wissensbestand.

Muster wie ``test_selection.py``: self-isolating (eigene Instanz-IRIs unter
``…/instance/case/pytest-k14-*``, die im ``finally`` wieder abgeräumt werden),
Skip ohne erreichbares Fuseki (übernimmt die ``store``-Fixture).

Der entscheidende Test ist
:func:`test_upsert_replaces_only_the_delivered_property`: ein Fall wird mit
``sexAtBirth`` **und** ``tumorStage`` geladen, danach nur mit ``sexAtBirth``
und einem anderen Wert. Danach muss ``db:sexAtBirth`` genau **einen** Wert
haben (den neuen) und ``db:tumorStage`` **noch da** sein. Das ist der Grund für die Aufgabe:
"Fall ersetzen" würde hier das ``tumorStage`` eines früheren, reicheren Aufrufs
verlieren.

English: Task 14 — acceptance: upsert per property in the growing
knowledge base.

Pattern like ``test_selection.py``: self-isolating (own instance IRIs under
``…/instance/case/pytest-k14-*``, cleaned up again in ``finally``), skipped
without a reachable Fuseki (handled by the ``store`` fixture).

The decisive test is
:func:`test_upsert_replaces_only_the_delivered_property`: a case is loaded
with ``sexAtBirth`` **and** ``tumorStage``, then again with only
``sexAtBirth`` and a different value. Afterward ``db:sexAtBirth`` must have
exactly **one** value (the new one) and ``db:tumorStage`` must **still be
there**. That is the reason for this task: "replace the case" would lose
the ``tumorStage`` from an earlier, richer call here.
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
# EN: Own namespace slice for these tests, so they neither disturb nor
# depend on a persistent store.
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

SEX_AT_BIRTH = f"{DB}sexAtBirth"
TUMOR_STAGE = f"{DB}tumorStage"


def _turtle(*, sex_at_birth: str, with_stage: bool = False, with_diagnosis: bool = False) -> str:
    """Nutzlast in der Form, die der Mediator liefert (typisierte Literale,
    Unterknoten je Demographic/Diagnosis/Sample, RDF-star fürs Alignment).

    English: Payload in the shape the mediator delivers (typed literals,
    sub-nodes per demographic/diagnosis/sample, RDF-star for the alignment).
    """
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
{stage}    db:sexAtBirth "{sex_at_birth}"^^xsd:string .

<{SAMPLE}> a db:Sample ;
    db:isSampleOf <{CASE}> ;
    db:sampleType "Primary Tumor"^^xsd:string .

<{OTHER_CASE}> a db:Case ;
    db:submitterId "{OTHER_SUBMITTER}"^^xsd:string ;
    db:belongsToProject <{PROJECT}> ;
    db:hasDemographic <{OTHER_DEMO}> .

<{OTHER_DEMO}> a db:Demographic ;
    db:sexAtBirth "male"^^xsd:string .
{diagnosis}{star}"""


def _values(store: GraphStore, subject: str, prop: str) -> list[str]:
    rows = store.query(
        PREFIXES + f"SELECT ?o WHERE {{ <{subject}> <{prop}> ?o }} ORDER BY ?o"
    )
    return [r["o"] for r in rows]


def _cleanup(store: GraphStore) -> None:
    """Alles wieder entfernen, was diese Tests in den Default-Graph schreiben.

    English: Removes everything these tests write into the default graph again.
    """
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
    """Store ohne Reste dieser Tests — vorher und nachher.

    English: A store without leftovers from these tests — before and after.
    """
    _cleanup(store)
    try:
        yield store
    finally:
        _cleanup(store)


# --------------------------------------------------------------------------
# Der entscheidende Test
# EN: The decisive test
# --------------------------------------------------------------------------
def test_upsert_replaces_only_the_delivered_property(clean_store: GraphStore) -> None:
    """Zweiter Aufruf mit weniger Attributen: der neue Wert ersetzt den alten,
    das Attribut des früheren, reicheren Aufrufs bleibt stehen.

    English: Second call with fewer attributes: the new value replaces the
    old one, the attribute from the earlier, richer call stays.
    """
    store = clean_store

    # Aufruf 1: sex_at_birth UND tumor_stage / EN: call 1: sex_at_birth AND tumor_stage
    kn.load_knowledge(
        store, _turtle(sex_at_birth="female", with_stage=True),
        submitter_ids=[SUBMITTER, OTHER_SUBMITTER],
        properties=[SEX_AT_BIRTH, TUMOR_STAGE],
    )
    assert _values(store, DEMO, SEX_AT_BIRTH) == ["female"]
    assert _values(store, DEMO, TUMOR_STAGE) == ["Stage IB"]

    # Aufruf 2: NUR sex_at_birth, mit geändertem Wert / EN: call 2: ONLY sex_at_birth, with a changed value
    kn.load_knowledge(
        store, _turtle(sex_at_birth="male"),
        submitter_ids=[SUBMITTER, OTHER_SUBMITTER],
        properties=[SEX_AT_BIRTH],
    )

    # genau ein sex_at_birth, und zwar der neue … / EN: exactly one sex_at_birth, and it's the new one …
    assert _values(store, DEMO, SEX_AT_BIRTH) == ["male"]
    # … und tumor_stage aus dem ersten Aufruf lebt noch. / EN: … and tumor_stage from the first call still lives.
    assert _values(store, DEMO, TUMOR_STAGE) == ["Stage IB"]


def test_append_only_would_duplicate(clean_store: GraphStore) -> None:
    """Gegenprobe: ohne ``properties`` (= bisheriges Anhängen) entstehen genau
    die zwei Werte, wegen derer es diese Aufgabe gibt.

    English: Control test: without ``properties`` (= the previous
    appending behavior), exactly the two values this task exists to
    prevent are created.
    """
    store = clean_store
    kn.load_knowledge(store, _turtle(sex_at_birth="female"), submitter_ids=[SUBMITTER])
    kn.load_knowledge(store, _turtle(sex_at_birth="male"), submitter_ids=[SUBMITTER])
    assert _values(store, DEMO, SEX_AT_BIRTH) == ["female", "male"]


# --------------------------------------------------------------------------
# Randfälle
# EN: Edge cases
# --------------------------------------------------------------------------
def test_first_load_deletes_nothing_and_does_not_raise(clean_store: GraphStore) -> None:
    """Beim ersten Ladevorgang ist der Fall noch nicht im Store; es gibt nichts
    aufzulösen und nichts zu löschen — das ist der Normalfall, kein Fehler.

    English: On the first load, the case is not yet in the store; there is
    nothing to resolve and nothing to delete — this is the normal case, not
    an error.
    """
    store = clean_store
    assert not store.ask(PREFIXES + f'ASK {{ ?c db:submitterId "{SUBMITTER}" }}')
    kn.load_knowledge(
        store, _turtle(sex_at_birth="female"),
        submitter_ids=[SUBMITTER], properties=[SEX_AT_BIRTH],
    )
    assert _values(store, DEMO, SEX_AT_BIRTH) == ["female"]


def test_replace_case_properties_is_a_noop_without_input(clean_store: GraphStore) -> None:
    store = clean_store
    assert kn.replace_case_properties(store, case_iris=[], properties=[SEX_AT_BIRTH]) == 0
    assert kn.replace_case_properties(store, case_iris=[CASE], properties=[]) == 0


def test_properties_none_behaves_like_load_turtle(clean_store: GraphStore) -> None:
    store = clean_store
    kn.load_knowledge(store, _turtle(sex_at_birth="female"), submitter_ids=[SUBMITTER])
    assert _values(store, DEMO, SEX_AT_BIRTH) == ["female"]
    assert store.ask(PREFIXES + f"ASK {{ <{SAMPLE}> db:sampleType ?t }}")


def test_upsert_touches_only_the_named_cases(clean_store: GraphStore) -> None:
    """Der zweite Fall in derselben Nutzlast wird nicht angefasst, wenn er nicht
    in ``submitter_ids`` steht — die Eingrenzung hängt am Fall, nicht an der
    Property allein.

    English: The second case in the same payload is not touched if it is
    not in ``submitter_ids`` — the scoping is anchored on the case, not on
    the property alone.
    """
    store = clean_store
    kn.load_knowledge(store, _turtle(sex_at_birth="female"), submitter_ids=[SUBMITTER])
    assert _values(store, OTHER_DEMO, SEX_AT_BIRTH) == ["male"]

    kn.replace_case_properties(store, case_iris=[CASE], properties=[SEX_AT_BIRTH])

    assert _values(store, DEMO, SEX_AT_BIRTH) == []
    assert _values(store, OTHER_DEMO, SEX_AT_BIRTH) == ["male"]


def test_tbox_survives_the_upsert(clean_store: GraphStore) -> None:
    """Die TBox liegt im selben Default-Graph wie die ABox; das Löschen ist über
    ``VALUES ?case`` auf Instanz-IRIs verankert und darf sie nicht treffen.

    English: The TBox lives in the same default graph as the ABox; the
    deletion is anchored via ``VALUES ?case`` on instance IRIs and must not
    hit it.
    """
    store = clean_store
    kn.load_knowledge(store, _turtle(sex_at_birth="female"), submitter_ids=[SUBMITTER])
    kn.replace_case_properties(
        store, case_iris=[CASE], properties=[SEX_AT_BIRTH, TUMOR_STAGE, f"{DB}sampleType"]
    )
    assert store.ask(PREFIXES + "ASK { db:Case a owl:Class }")
    assert store.ask(PREFIXES + "ASK { db:sexAtBirth a owl:DatatypeProperty }")


def test_project_node_survives_the_upsert(clean_store: GraphStore) -> None:
    """Projekt-Knoten sind kohortenweit geteilt; ``db:belongsToProject`` steht
    deshalb nicht im Pfad.

    English: Project nodes are shared cohort-wide; ``db:belongsToProject``
    is therefore not in the path.
    """
    store = clean_store
    kn.load_knowledge(store, _turtle(sex_at_birth="female"), submitter_ids=[SUBMITTER])
    kn.replace_case_properties(
        store, case_iris=[CASE, OTHER_CASE], properties=[SEX_AT_BIRTH, f"{DB}projectId"]
    )
    assert store.ask(PREFIXES + f'ASK {{ <{PROJECT}> db:projectId "PYTEST-K14-PROJ" }}')
    assert store.ask(PREFIXES + f"ASK {{ <{CASE}> db:belongsToProject <{PROJECT}> }}")


def test_feedback_named_graph_survives_upsert(clean_store: GraphStore) -> None:
    """Ein Update ohne ``GRAPH``-Klausel darf nur den Default-Graph treffen.

    Nicht angenommen, sondern geprüft: Finding in einen Nutzer-Graphen
    schreiben, Upsert ausführen, Finding muss noch da sein.

    English: An update without a ``GRAPH`` clause must only hit the
    default graph.

    Not assumed, but verified: write a finding into a user graph, run the
    upsert, the finding must still be there.
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
            store, _turtle(sex_at_birth="female"),
            submitter_ids=[SUBMITTER], properties=[SEX_AT_BIRTH, f"{DB}confidence"],
        )
        kn.replace_case_properties(
            store, case_iris=[CASE], properties=[SEX_AT_BIRTH, f"{DB}confidence"]
        )
        assert len(fb.list_findings(store, user=event.user)) == 1
        assert len(fb.reclassifications(store, user=event.user)) == 1
    finally:
        store.update(f"DROP GRAPH <{graph}>")


# --------------------------------------------------------------------------
# Sonderfall NCIt-Alignment (db:primaryDiagnosis + RDF-star)
# EN: Special case: NCIt alignment (db:primaryDiagnosis + RDF-star)
# --------------------------------------------------------------------------
def test_primary_diagnosis_label_also_clears_the_alignment(clean_store: GraphStore) -> None:
    """Die Property-Liste des Mediators enthält nur ``db:primaryDiagnosisLabel``.
    Der NCIt-Link und seine RDF-star-Provenienz sind dessen Anhang und müssen
    mitgehen — sonst bliebe Provenienz über eine Aussage stehen, die es nicht
    mehr gibt.

    English: The mediator's property list contains only
    ``db:primaryDiagnosisLabel``. The NCIt link and its RDF-star provenance
    are its attachment and must go along — otherwise provenance would
    remain on a statement that no longer exists.
    """
    store = clean_store
    kn.load_knowledge(
        store, _turtle(sex_at_birth="female", with_diagnosis=True),
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
    # EN: The diagnosis itself stays attached to the case (db:hasDiagnosis
    # is not touched), only its values are gone.
    assert store.ask(PREFIXES + f"ASK {{ <{CASE}> db:hasDiagnosis <{DIAG}> }}")


def test_expand_properties_only_adds_the_alignment_pair() -> None:
    props = kn._expand_properties([f"{DB}sexAtBirth"])
    assert props == [f"{DB}sexAtBirth"]
    props = kn._expand_properties([f"{DB}primaryDiagnosisLabel"])
    assert props == [f"{DB}primaryDiagnosisLabel", f"{DB}primaryDiagnosis"]
    # CURIE-Schreibweise wird genauso erkannt.
    # EN: CURIE notation is recognized the same way.
    props = kn._expand_properties(["db:primaryDiagnosisLabel"])
    assert props == ["db:primaryDiagnosisLabel", f"{DB}primaryDiagnosis"]
    # Steht die Objekt-Property schon drin, wird sie nicht verdoppelt.
    # EN: If the object property is already present, it is not duplicated.
    props = kn._expand_properties([f"{DB}primaryDiagnosisLabel", f"{DB}primaryDiagnosis"])
    assert props == [f"{DB}primaryDiagnosisLabel", f"{DB}primaryDiagnosis"]


def _star_annotations(store: GraphStore) -> int:
    rows = store.query(
        PREFIXES
        + f"SELECT ?ap ?av WHERE {{ << <{DIAG}> db:primaryDiagnosis ?o >> ?ap ?av }}"
    )
    return len(rows)
