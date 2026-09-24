"""Auswahl-Graphen (Aufgabe 13): ein Manifest je ``/selection/*``-Aufruf.

Der Store ist **nicht** global vorbefüllt, sondern **wächst mit den Aufrufen**
(ADR-0003, ``wissensnetz/HANDOFF_pablo_store_waechst.md``). Dabei bleiben zwei
Ebenen bewusst getrennt:

===================  ==========================================  ==============
Ebene                Inhalt                                      Ort
===================  ==========================================  ==============
Wissensbestand       Case, Demographic, Diagnosis, Sample und     Default-Graph
                     die dynamisch erzeugten Properties
Auswahl-Manifest     welche Proben und Fälle zu einer Auswahl      Named Graph
                     gehören, plus die Auswahlparameter
===================  ==========================================  ==============

Läge der Wissensbestand je Auswahl in einem eigenen Named Graph, stünden
dieselben Case-Tripel als Quads mehrfach im Store, und ein ``DROP GRAPH`` würde
Wissen löschen, das eine andere Auswahl noch braucht. So bleibt der Bestand
gemeinsam (und dedupliziert sich über die deterministischen Instanz-IRIs des
Mediator-Mappings von selbst), die Zugehörigkeit ist trotzdem nachvollziehbar.

Das Vokabular dazu steht in ``ontology/selection.ttl`` und wird von
``wissensnetz init`` mitgeladen. Gegenstück zum Lesen ist
:func:`wissensnetz.enrichment.cases_for_selection`.

**Naht zum Mediator:** :func:`write_selection` ist die Funktion, die Pablo
aufruft (HANDOFF, P2). Ihre Signatur ändert sich nach der Übergabe nicht mehr
ohne Absprache. Die Sample-IRIs folgen derselben Bildungsregel wie das
Mediator-Mapping (``INSTANCE_BASE + "sample/" + _slug(sample_id)``, siehe
``mediator/app/semantic/mapping.py`` Zeile 287) — festgenagelt in
``tests/test_selection.py::test_sample_iri_matches_mediator_rule``.

Geschrieben wird per Graph Store Protocol (Turtle in einen Named Graph), nicht
per SPARQL-Update: das Manifest enthält kein RDF-star, ein Turtle-Dokument ist
hier die einfachere und besser prüfbare Form (``selection_manifest`` ist rein
und ohne Store testbar).

English: Selection graphs (task 13): one manifest per ``/selection/*``
call.

The store is **not** globally pre-populated, but **grows with the calls**
(ADR-0003, ``wissensnetz/HANDOFF_pablo_store_waechst.md``). Two levels stay
deliberately separate:

===================  ==========================================  ==============
Level                Content                                     Location
===================  ==========================================  ==============
Knowledge base       Case, Demographic, Diagnosis, Sample and     Default graph
                     the dynamically generated properties
Selection manifest   which samples and cases belong to a          Named graph
                     selection, plus the selection parameters
===================  ==========================================  ==============

If the knowledge base lived per selection in its own named graph, the same
case triples would sit as quads multiple times in the store, and a ``DROP
GRAPH`` would delete knowledge another selection still needs. This way the
base stays shared (and deduplicates itself via the mediator mapping's
deterministic instance IRIs), while membership stays traceable nonetheless.

The vocabulary for this lives in ``ontology/selection.ttl`` and is loaded
by ``wissensnetz init``. The reading counterpart is
:func:`wissensnetz.enrichment.cases_for_selection`.

**Seam to the mediator:** :func:`write_selection` is the function Pablo
calls (HANDOFF, P2). Its signature no longer changes without agreement once
handed over. The sample IRIs follow the same formation rule as the mediator
mapping (``INSTANCE_BASE + "sample/" + _slug(sample_id)``, see
``mediator/app/semantic/mapping.py`` line 287) — pinned down in
``tests/test_selection.py::test_sample_iri_matches_mediator_rule``.

Writing happens via Graph Store Protocol (Turtle into a named graph), not
via SPARQL update: the manifest contains no RDF-star, a Turtle document is
the simpler and better-testable form here (``selection_manifest`` is pure
and testable without a store).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .config import DB, INSTANCE, PREFIXES, PROV
from .graphstore import GraphStore

# Named-Graph-Schema je Auswahl (Konvention aus HANDOFF_review_selection.md,
# "Was bei mir liegt", Punkt 1). <id> ist der recipe_key des Mediators.
# EN: Named-graph schema per selection (convention from
# HANDOFF_review_selection.md, "What's on my end", point 1). <id> is the
# mediator's recipe_key.
SELECTION_GRAPH_BASE = "http://databridge.hka/graph/selection/"

# Instanz-Basen. sample/ und case/ MÜSSEN mit dem Mediator-Mapping übereinstimmen,
# sonst zeigt das Manifest ins Leere.
# EN: Instance bases. sample/ and case/ MUST match the mediator mapping,
# otherwise the manifest points into the void.
_SELECTION_BASE = f"{INSTANCE}selection/"
_SAMPLE_BASE = f"{INSTANCE}sample/"
_CASE_BASE = f"{INSTANCE}case/"

# Turtle-Präfixblock für das Manifest (PREFIXES aus config ist SPARQL-Syntax).
# EN: Turtle prefix block for the manifest (PREFIXES from config is SPARQL syntax).
_TURTLE_PREFIXES = f"""\
@prefix db:   <{DB}> .
@prefix prov: <{PROV}> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
"""

# Trennzeichen für GROUP_CONCAT in list_selections. Kohorten- und Attributnamen
# sind Bezeichner ohne '|', ein Leerzeichen wäre riskanter.
# EN: Separator for GROUP_CONCAT in list_selections. Cohort and attribute
# names are identifiers without '|'; a space would be riskier.
_SEP = "|"


# --------------------------------------------------------------------------
# IRI-/Literal-Hilfen
# EN: IRI/literal helpers
# --------------------------------------------------------------------------
def _slug(value: str) -> str:
    """Instanz-IRI-taugliches Fragment — **identisch** zu ``_slug`` in
    ``mediator/app/semantic/mapping.py`` (Zeile 201) und ``feedback.py``.

    English: Instance-IRI-suitable fragment — **identical** to ``_slug``
    in ``mediator/app/semantic/mapping.py`` (line 201) and ``feedback.py``.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"


def is_iri(ref: str) -> bool:
    """True, wenn ``ref`` eine volle IRI ist (und keine blanke Kennung).

    Öffentlich, weil ``knowledge.py`` damit die Rückgabe von
    :func:`resolve_case_iris` in aufgelöste und nicht aufgelöste Einträge
    trennt.

    English: True if ``ref`` is a full IRI (and not a plain identifier).

    Public because ``knowledge.py`` uses it to split the return value of
    :func:`resolve_case_iris` into resolved and unresolved entries.
    """
    r = ref.strip()
    return r.startswith("http://") or r.startswith("https://") or r.startswith("urn:")


def sample_iri(sample_id: str) -> str:
    """Instanz-IRI einer Probe nach der Regel des Mediator-Mappings.

    Eine bereits vollständige IRI wird unverändert übernommen, damit der
    Aufrufer auch IRIs statt Kennungen übergeben kann.

    English: Instance IRI of a sample following the mediator mapping's
    rule.

    An already-complete IRI is passed through unchanged, so the caller can
    also supply IRIs instead of identifiers.
    """
    ref = sample_id.strip()
    return ref if is_iri(ref) else f"{_SAMPLE_BASE}{_slug(ref)}"


def case_iri(case_ref: str) -> str:
    """Instanz-IRI eines Falls nach der Regel des Mediator-Mappings.

    Achtung: der Mediator bildet die Case-IRI aus ``case_id`` (GDC-UUID), nicht
    aus ``submitter_id``. Für einen blanken ``submitter_id`` ist das hier nur
    ein Notnagel — :func:`write_selection` löst ihn vorher über den Store auf.

    English: Instance IRI of a case following the mediator mapping's rule.

    Caution: the mediator forms the case IRI from ``case_id`` (GDC UUID),
    not from ``submitter_id``. For a plain ``submitter_id`` this is only a
    stopgap here — :func:`write_selection` resolves it via the store
    beforehand.
    """
    ref = case_ref.strip()
    return ref if is_iri(ref) else f"{_CASE_BASE}{_slug(ref)}"


def graph_iri_for_selection(selection_id: str) -> str:
    """Named-Graph-IRI für eine Auswahl.

    English: Named-graph IRI for a selection.
    """
    return f"{SELECTION_GRAPH_BASE}{_slug(selection_id)}"


def selection_iri(selection_id: str) -> str:
    """Instanz-IRI der ``db:Selection`` selbst (Subjekt des Manifests).

    English: Instance IRI of the ``db:Selection`` itself (subject of the manifest).
    """
    return f"{_SELECTION_BASE}{_slug(selection_id)}"


def _string_literal(value: str) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"^^xsd:string'


def _unique(values: list[str] | tuple[str, ...] | None) -> list[str]:
    """Reihenfolge-erhaltende Deduplizierung; leere Werte fallen weg.

    English: Order-preserving deduplication; empty values are dropped.
    """
    seen: set[str] = set()
    out: list[str] = []
    for v in values or ():
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


# --------------------------------------------------------------------------
# Manifest bauen
# EN: Building the manifest
# --------------------------------------------------------------------------
def selection_manifest(
    selection_id: str,
    *,
    source: str,
    cohorts: list[str],
    modality: str,
    attributes: list[str],
    submitter_ids: list[str],
    sample_ids: list[str],
    timestamp: str | None = None,
) -> str:
    """Baut das Auswahl-Manifest als Turtle (für den Named Graph).

    Reine Funktion ohne Store-Zugriff: ``submitter_ids`` und ``sample_ids``
    dürfen Kennungen **oder** volle IRIs sein. Kennungen werden nach der Regel
    des Mediator-Mappings zu Instanz-IRIs (``sample/<slug>`` bzw.
    ``case/<slug>``). Ohne ``timestamp`` wird die aktuelle UTC-Zeit gesetzt.

    English: Builds the selection manifest as Turtle (for the named graph).

    Pure function without store access: ``submitter_ids`` and
    ``sample_ids`` may be identifiers **or** full IRIs. Identifiers are
    turned into instance IRIs (``sample/<slug>`` or ``case/<slug>``)
    following the mediator mapping's rule. Without ``timestamp``, the
    current UTC time is set.
    """
    ts = timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    subject = f"<{selection_iri(selection_id)}>"

    lines = [
        f"{subject} a db:Selection ;",
        f"    db:selectionId {_string_literal(selection_id)} ;",
        f"    db:source {_string_literal(source)} ;",
        f"    db:selectedModality {_string_literal(modality)} ;",
        f'    prov:generatedAtTime "{ts}"^^xsd:dateTime ;',
    ]
    lines += [f"    db:selectedCohort {_string_literal(c)} ;" for c in _unique(cohorts)]
    lines += [f"    db:selectedAttribute {_string_literal(a)} ;" for a in _unique(attributes)]
    lines += [f"    db:hasMember <{sample_iri(s)}> ;" for s in _unique(sample_ids)]
    lines += [f"    db:selectionCase <{case_iri(c)}> ;" for c in _unique(submitter_ids)]

    # Letztes ';' zum '.' machen — so bleibt das Dokument auch ohne Mitglieder gültig.
    # EN: Turn the last ';' into a '.' — this keeps the document valid even
    # without members.
    lines[-1] = lines[-1][:-1].rstrip() + " ."
    return _TURTLE_PREFIXES + "\n" + "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Schreiben / Verwerfen
# EN: Writing / discarding
# --------------------------------------------------------------------------
def resolve_case_iris(store: GraphStore, submitter_ids: list[str]) -> list[str]:
    """Löst ``submitter_id``-Werte über den Default-Graph zu Case-IRIs auf.

    Der Mediator bildet die Case-IRI aus ``case_id`` (GDC-UUID), übergibt uns
    aber ``submitter_id`` (TCGA-Barcode) — die IRI lässt sich daraus nicht
    ausrechnen, nur nachschlagen. Voraussetzung ist die Reihenfolge aus dem
    HANDOFF: **erst** den Wissensbestand in den Default-Graph laden, **dann**
    das Manifest schreiben.

    Nicht auffindbare Kennungen bleiben unverändert (``selection_manifest``
    macht daraus den deterministischen Notnagel ``case/<slug>``); der Join in
    :func:`wissensnetz.enrichment.cases_for_selection` verlangt ohnehin einen
    ``db:Case`` im Bestand, solche Einträge fallen dort also einfach heraus.

    English: Resolves ``submitter_id`` values to case IRIs via the default
    graph.

    The mediator forms the case IRI from ``case_id`` (GDC UUID), but hands
    us ``submitter_id`` (TCGA barcode) — the IRI cannot be computed from
    that, only looked up. This requires the order from the HANDOFF:
    **first** load the knowledge base into the default graph, **then**
    write the manifest.

    Identifiers that cannot be found stay unchanged (``selection_manifest``
    turns them into the deterministic stopgap ``case/<slug>``); the join in
    :func:`wissensnetz.enrichment.cases_for_selection` requires a
    ``db:Case`` in the base anyway, so such entries simply drop out there.
    """
    ids = _unique(submitter_ids)
    if not ids:
        return []
    values = " ".join(_string_literal(i) for i in ids if not is_iri(i))
    resolved: dict[str, str] = {}
    if values:
        rows = store.query(
            PREFIXES
            + f"SELECT ?sid ?c WHERE {{ VALUES ?sid {{ {values} }} "
            f"?c a db:Case ; db:submitterId ?sid . }}"
        )
        for r in rows:
            sid, c = r.get("sid"), r.get("c")
            if sid and c and sid not in resolved:
                resolved[sid] = c
    return [resolved.get(i, i) for i in ids]


def write_selection(store: GraphStore, selection_id: str, **kwargs: Any) -> str:
    """Manifest bauen und in den Named Graph laden; gibt die Graph-IRI zurück.

    Das ist die Naht zum Mediator (HANDOFF, P2)::

        graph_iri = write_selection(
            store, selection_id=recipe_key, source=level.source,
            cohorts=level.cohorts, modality=level.modality,
            attributes=level.attributes,
            submitter_ids=[...], sample_ids=[...],
        )

    Der Named Graph wird dabei **ersetzt**, nicht ergänzt: derselbe
    ``selection_id`` mit einer anderen Probenmenge soll keine Altmitglieder
    stehen lassen. Der Wissensbestand im Default-Graph bleibt unangetastet.

    English: Builds the manifest and loads it into the named graph; returns
    the graph IRI.

    This is the seam to the mediator (HANDOFF, P2)::

        graph_iri = write_selection(
            store, selection_id=recipe_key, source=level.source,
            cohorts=level.cohorts, modality=level.modality,
            attributes=level.attributes,
            submitter_ids=[...], sample_ids=[...],
        )

    The named graph is **replaced**, not appended to: the same
    ``selection_id`` with a different sample set should not leave stale
    members behind. The knowledge base in the default graph is left
    untouched.
    """
    graph = graph_iri_for_selection(selection_id)
    kwargs = dict(kwargs)
    kwargs["submitter_ids"] = resolve_case_iris(store, kwargs.get("submitter_ids") or [])
    turtle = selection_manifest(selection_id, **kwargs)
    store.update(f"DROP SILENT GRAPH <{graph}>")
    store.load_turtle(turtle, graph=graph)
    return graph


def drop_selection(store: GraphStore, selection_id: str) -> None:
    """``DROP GRAPH`` für eine Auswahl.

    Löscht **nur** das Manifest, nicht den Wissensbestand: Case, Demographic,
    Diagnosis und Sample liegen im Default-Graph und werden womöglich von einer
    anderen Auswahl noch gebraucht. ``SILENT``, damit ein zweiter Aufruf nicht
    scheitert.

    English: ``DROP GRAPH`` for a selection.

    Deletes **only** the manifest, not the knowledge base: case,
    demographic, diagnosis and sample live in the default graph and may
    still be needed by another selection. ``SILENT``, so a second call does
    not fail.
    """
    store.update(f"DROP SILENT GRAPH <{graph_iri_for_selection(selection_id)}>")


# --------------------------------------------------------------------------
# Lesen
# EN: Reading
# --------------------------------------------------------------------------
def list_selections(store: GraphStore) -> list[dict[str, Any]]:
    """Alle Auswahlen mit id, Kohorten, Modalität, Attributen, Zeit, Mitgliederzahl.

    Fehlende Werte bleiben ``None`` bzw. leere Liste (tolerant wie die übrigen
    Lesefunktionen). ``members`` zählt die Proben, ``cases`` die Fälle des
    Manifests — beide über ``COUNT(DISTINCT …)``, damit das Kreuzprodukt aus
    Kohorten/Attributen die Zahlen nicht aufbläht.

    English: All selections with id, cohorts, modality, attributes, time,
    member count.

    Missing values stay ``None`` or an empty list (tolerant like the other
    read functions). ``members`` counts the samples, ``cases`` the cases of
    the manifest — both via ``COUNT(DISTINCT …)``, so the cross product of
    cohorts/attributes does not inflate the numbers.
    """
    sparql = PREFIXES + f"""
    SELECT ?g ?sel ?id ?source ?modality ?time
           (GROUP_CONCAT(DISTINCT ?cohort; separator="{_SEP}") AS ?cohorts)
           (GROUP_CONCAT(DISTINCT ?attr; separator="{_SEP}") AS ?attributes)
           (COUNT(DISTINCT ?member) AS ?members)
           (COUNT(DISTINCT ?case) AS ?cases)
    WHERE {{
      GRAPH ?g {{
        ?sel a db:Selection .
        OPTIONAL {{ ?sel db:selectionId ?id }}
        OPTIONAL {{ ?sel db:source ?source }}
        OPTIONAL {{ ?sel db:selectedModality ?modality }}
        OPTIONAL {{ ?sel prov:generatedAtTime ?time }}
        OPTIONAL {{ ?sel db:selectedCohort ?cohort }}
        OPTIONAL {{ ?sel db:selectedAttribute ?attr }}
        OPTIONAL {{ ?sel db:hasMember ?member }}
        OPTIONAL {{ ?sel db:selectionCase ?case }}
      }}
    }}
    GROUP BY ?g ?sel ?id ?source ?modality ?time
    ORDER BY ?time ?id
    """
    selections = []
    for r in store.query(sparql):
        selections.append({
            "graph": r.get("g"),
            "selection_iri": r.get("sel"),
            "selection_id": r.get("id"),
            "source": r.get("source"),
            "modality": r.get("modality"),
            "timestamp": r.get("time"),
            "cohorts": _split(r.get("cohorts")),
            "attributes": _split(r.get("attributes")),
            "members": int(r.get("members") or 0),
            "cases": int(r.get("cases") or 0),
        })
    return selections


def selection_exists(store: GraphStore, selection_id: str) -> bool:
    """True, wenn ein Manifest zu dieser Auswahl im Store liegt.

    English: True if a manifest for this selection is present in the store.
    """
    graph = graph_iri_for_selection(selection_id)
    return store.ask(PREFIXES + f"ASK {{ GRAPH <{graph}> {{ ?s a db:Selection }} }}")


def _split(value: str | None) -> list[str]:
    return [v for v in (value or "").split(_SEP) if v]
