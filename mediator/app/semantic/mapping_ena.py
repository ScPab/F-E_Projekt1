"""Regelbasiertes ENA-Run-JSON -> RDF/OWL-Mapping (ABox).

Analog zu `mapping.py` (GDC) und `mapping_geo.py`: für die Antwort von
`ENAWrapper.search(result="read_run", fields=[...])`. Ontologie/TBox siehe
wissensnetz/ontology/databridge-core.ttl (`db:Study`/`db:Run`) — `db:Run`
wird bewusst mit `mapping_geo.py` geteilt (siehe Kommentar dort in der
Ontologie: dieselbe Rolle "ein Lauf/Sample innerhalb einer Serie/Studie").

Kein Enum-Alignment für diesen ersten Ausschnitt, daher immer eine leere
Liste von RDF-star-Annotationen — Rückgabeform identisch zu
`mapping.cases_to_graph`, damit `serialize_with_provenance` unverändert
wiederverwendet werden kann. Global-as-View wie bei GDC/GEO.
"""

from __future__ import annotations

import re
from typing import Any

from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

DB = Namespace("http://databridge.hka/onto#")
INSTANCE_BASE = "http://databridge.hka/instance/"

StarAnnotation = tuple[URIRef, URIRef, URIRef, str, float]


def _slug(value: str) -> str:
    """Instanz-IRI-taugliches Fragment aus einem beliebigen Bezeichner (siehe mapping.py)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"


def _bind_prefixes(graph: Graph) -> None:
    graph.bind("db", DB)


def _to_int(value: Any) -> int | None:
    """ENA liefert numerische Felder (z. B. `read_count`) als String — robust in int wandeln."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def runs_to_graph(runs: list[dict[str, Any]]) -> tuple[Graph, list[StarAnnotation]]:
    """Übersetzt ENA-`read_run`-Treffer in RDF-Tripel (Study + Run).

    Erwartet Felder wie `run_accession`, `study_accession`, `description`,
    `library_strategy`, `instrument_platform`, `scientific_name`,
    `read_count` (siehe `ENAWrapper.search`/`get_schema("read_run")` für die
    volle Feldliste; nicht angeforderte Felder fehlen einfach im Dict und
    werden hier übersprungen statt einen Fehler zu werfen).
    """
    graph = Graph()
    _bind_prefixes(graph)
    seen_studies: set[str] = set()

    for run in runs:
        run_accession = run.get("run_accession")
        if not run_accession:
            continue
        run_iri = URIRef(f"{INSTANCE_BASE}run/{_slug(run_accession)}")
        graph.add((run_iri, RDF.type, DB.Run))
        graph.add((run_iri, DB.runId, Literal(run_accession, datatype=XSD.string)))
        if run.get("description"):
            graph.add((run_iri, RDFS.label, Literal(run["description"])))
        if run.get("library_strategy"):
            graph.add((run_iri, DB.libraryStrategy, Literal(run["library_strategy"], datatype=XSD.string)))
        if run.get("instrument_platform"):
            graph.add((run_iri, DB.instrumentPlatform, Literal(run["instrument_platform"], datatype=XSD.string)))
        if run.get("scientific_name"):
            graph.add((run_iri, DB.organism, Literal(run["scientific_name"], datatype=XSD.string)))
        read_count = _to_int(run.get("read_count"))
        if read_count is not None:
            graph.add((run_iri, DB.readCount, Literal(read_count, datatype=XSD.integer)))

        study_accession = run.get("study_accession")
        if study_accession:
            study_iri = URIRef(f"{INSTANCE_BASE}study/{_slug(study_accession)}")
            if study_accession not in seen_studies:
                graph.add((study_iri, RDF.type, DB.Study))
                graph.add((study_iri, DB.studyId, Literal(study_accession, datatype=XSD.string)))
                seen_studies.add(study_accession)
            graph.add((study_iri, DB.hasRun, run_iri))
            graph.add((run_iri, DB.isRunOf, study_iri))

    return graph, []
