"""Regelbasiertes GEO-Series-JSON -> RDF/OWL-Mapping (ABox).

Analog zu `mapping.py` (GDC): dieselbe Konstrukt-für-Konstrukt-Logik, hier
für die Antwort von `GEOWrapper.search(entry_type="gse")` (esummary-
DocumentSummary je GEO-Series). Ontologie/TBox siehe
wissensnetz/ontology/databridge-core.ttl (`db:Series`/`db:Run`).

Kein Enum-Alignment für diesen ersten Ausschnitt (anders als bei
`diagnoses.primary_diagnosis` in mapping.py) — daher immer eine leere
Liste von RDF-star-Annotationen; die Rückgabeform ist trotzdem identisch zu
`mapping.cases_to_graph`, damit `serialize_with_provenance` unverändert
wiederverwendet werden kann.

Global-as-View, wie bei GDC (siehe mapping.py-Modul-Docstring): quellen-
spezifische Übersetzungslogik direkt in diesem Modul.
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


def series_to_graph(series_list: list[dict[str, Any]]) -> tuple[Graph, list[StarAnnotation]]:
    """Übersetzt GEO-Series-Treffer (esummary-DocumentSummaries) in RDF-Tripel.

    Erwartet die Roh-Form von `GEOWrapper.search(entry_type="gse")`, d. h.
    Felder wie `accession`, `title`, `summary`, `taxon`, `gdstype`, `pdat`,
    `n_samples`, `ftplink` sowie das verschachtelte `samples` (Liste von
    `{accession, title}` je GSM innerhalb der Series).
    """
    graph = Graph()
    _bind_prefixes(graph)

    for entry in series_list:
        accession = entry.get("accession")
        if not accession:
            continue
        series_iri = URIRef(f"{INSTANCE_BASE}series/{_slug(accession)}")
        graph.add((series_iri, RDF.type, DB.Series))
        graph.add((series_iri, DB.seriesId, Literal(accession, datatype=XSD.string)))
        if entry.get("title"):
            graph.add((series_iri, RDFS.label, Literal(entry["title"])))
        if entry.get("summary"):
            graph.add((series_iri, RDFS.comment, Literal(entry["summary"])))
        if entry.get("taxon"):
            graph.add((series_iri, DB.organism, Literal(entry["taxon"], datatype=XSD.string)))
        if entry.get("gdstype"):
            graph.add((series_iri, DB.experimentType, Literal(entry["gdstype"], datatype=XSD.string)))
        if entry.get("pdat"):
            graph.add((series_iri, DB.releaseDate, Literal(entry["pdat"], datatype=XSD.string)))
        if entry.get("ftplink"):
            graph.add((series_iri, DB.ftpLink, Literal(entry["ftplink"], datatype=XSD.anyURI)))
        n_samples = entry.get("n_samples")
        if n_samples is not None:
            graph.add((series_iri, DB.sampleCount, Literal(int(n_samples), datatype=XSD.integer)))

        for sample in entry.get("samples") or []:
            gsm_accession = sample.get("accession")
            if not gsm_accession:
                continue
            run_iri = URIRef(f"{INSTANCE_BASE}run/{_slug(gsm_accession)}")
            graph.add((run_iri, RDF.type, DB.Run))
            graph.add((run_iri, DB.runId, Literal(gsm_accession, datatype=XSD.string)))
            if sample.get("title"):
                graph.add((run_iri, RDFS.label, Literal(sample["title"])))
            graph.add((series_iri, DB.hasRun, run_iri))
            graph.add((run_iri, DB.isRunOf, series_iri))

    return graph, []
