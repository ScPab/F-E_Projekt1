"""Regelbasiertes GDC-Case-JSON -> RDF/OWL-Mapping (ABox).

Setzt die Konstrukt-Regeln aus wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL für
den Kern-Ausschnitt case/project/demographic/diagnosis um (Ontologie/TBox
siehe wissensnetz/ontology/databridge-core.ttl): enum-Werte werden — wo eine
Alignment-Tabelle einen Treffer liefert — auf externe Bio-Ontologien (hier:
NCIt für primary_diagnosis) abgebildet, sonst bleibt der Rohtext als Literal
erhalten. Kanten-Provenienz/-Konfidenz für Alignment-Aussagen werden über
RDF-star modelliert (siehe serialize_with_provenance).

Global-as-View: GDC ist aktuell die einzige angebundene Quelle, daher ist
diese Übersetzungslogik bewusst quellenspezifisch (siehe Marcels Empfehlung
im Mapping-Konzept: "Für eine Quelle genügt zunächst GaV"). Für eine zweite
Quelle: eigenes mapping_<source>.py nach demselben Muster, siehe
/docs/adding_new_sources.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

DB = Namespace("http://databridge.hka/onto#")
NCIT = Namespace("http://purl.obolibrary.org/obo/NCIT_")
PROV = Namespace("http://www.w3.org/ns/prov#")

INSTANCE_BASE = "http://databridge.hka/instance/"

# (Subjekt, Prädikat, Objekt, Quelle-als-Turtle-Term, Konfidenz) für eine noch
# anzuhängende RDF-star-Provenienz-Annotation, siehe serialize_with_provenance.
StarAnnotation = tuple[URIRef, URIRef, URIRef, str, float]


def load_alignment_table(path: str | Path) -> dict[str, str]:
    """Lädt die Enum->NCIt-Alignment-Tabelle.

    Fehlt die Datei (z. B. noch nicht befüllt/nicht gemountet), wird eine
    leere Tabelle zurückgegeben — Alignment ist optional, der Fallback auf
    Literal-Text greift dann für alle Werte (siehe cases_to_graph).
    """
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _slug(value: str) -> str:
    """Instanz-IRI-taugliches Fragment aus einem beliebigen Bezeichner (z. B. TCGA-Barcode, UUID)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"


def _bind_prefixes(graph: Graph) -> None:
    graph.bind("db", DB)
    graph.bind("ncit", NCIT)
    graph.bind("prov", PROV)


def cases_to_graph(
    cases: list[dict[str, Any]],
    *,
    alignment: dict[str, str] | None = None,
) -> tuple[Graph, list[StarAnnotation]]:
    """Übersetzt GDC-`cases`-Treffer in RDF-Tripel (case/project/demographic/diagnoses).

    Erwartet die verschachtelte Form, wie sie GDCWrapper.search("cases",
    fields=[...]) liefert (project.project_id, demographic.gender,
    diagnoses[].primary_diagnosis, diagnoses[].age_at_diagnosis).

    Gibt den Haupt-Graphen sowie eine Liste offener RDF-star-Annotationen
    zurück (Provenienz/Konfidenz für erfolgreiche NCIt-Alignments) — diese
    hängt serialize_with_provenance an die Turtle-Ausgabe an.
    """
    alignment = alignment or {}
    graph = Graph()
    _bind_prefixes(graph)
    star_annotations: list[StarAnnotation] = []
    seen_projects: set[str] = set()

    for case in cases:
        case_id = case.get("case_id") or case.get("submitter_id")
        if not case_id:
            continue
        case_iri = URIRef(f"{INSTANCE_BASE}case/{_slug(case_id)}")
        graph.add((case_iri, RDF.type, DB.Case))
        graph.add((case_iri, DB.caseId, Literal(case_id, datatype=XSD.string)))
        if case.get("submitter_id"):
            graph.add((case_iri, DB.submitterId, Literal(case["submitter_id"], datatype=XSD.string)))

        project = case.get("project") or {}
        project_id = project.get("project_id")
        if project_id:
            project_iri = URIRef(f"{INSTANCE_BASE}project/{_slug(project_id)}")
            if project_id not in seen_projects:
                graph.add((project_iri, RDF.type, DB.Project))
                graph.add((project_iri, DB.projectId, Literal(project_id, datatype=XSD.string)))
                seen_projects.add(project_id)
            graph.add((case_iri, DB.belongsToProject, project_iri))
            graph.add((project_iri, DB.hasCase, case_iri))

        demographic = case.get("demographic") or {}
        if demographic:
            demo_iri = URIRef(f"{INSTANCE_BASE}demographic/{_slug(case_id)}")
            graph.add((demo_iri, RDF.type, DB.Demographic))
            if demographic.get("gender"):
                graph.add((demo_iri, DB.gender, Literal(demographic["gender"], datatype=XSD.string)))
            graph.add((case_iri, DB.hasDemographic, demo_iri))
            graph.add((demo_iri, DB.isDemographicOf, case_iri))

        for idx, diagnosis in enumerate(case.get("diagnoses") or []):
            diag_key = diagnosis.get("diagnosis_id") or f"{case_id}-diag{idx}"
            diag_iri = URIRef(f"{INSTANCE_BASE}diagnosis/{_slug(diag_key)}")
            graph.add((diag_iri, RDF.type, DB.Diagnosis))
            graph.add((diag_iri, DB.describesCase, case_iri))
            graph.add((case_iri, DB.hasDiagnosis, diag_iri))

            primary = diagnosis.get("primary_diagnosis")
            if primary:
                graph.add((diag_iri, DB.primaryDiagnosisLabel, Literal(primary, datatype=XSD.string)))
                ncit_iri = alignment.get(primary)
                if ncit_iri:
                    concept_iri = URIRef(ncit_iri)
                    graph.add((diag_iri, DB.primaryDiagnosis, concept_iri))
                    star_annotations.append(
                        (diag_iri, DB.primaryDiagnosis, concept_iri, "gdc:submission", 1.0)
                    )

            if diagnosis.get("age_at_diagnosis") is not None:
                graph.add(
                    (diag_iri, DB.ageAtDiagnosis, Literal(diagnosis["age_at_diagnosis"], datatype=XSD.integer))
                )

    return graph, star_annotations


def serialize_with_provenance(graph: Graph, star_annotations: list[StarAnnotation]) -> str:
    """Serialisiert den Graphen nach Turtle und hängt RDF-star-Provenienz-Blöcke an.

    RDF-star wird hier bewusst als Text angehängt statt über eine
    rdflib-interne Quoted-Triple-API erzeugt — die Turtle-Star-Unterstützung
    unterscheidet sich je rdflib-Version, während dieses Textformat exakt dem
    Beispiel aus wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL entspricht und
    damit garantiert spezifikationskonform bleibt:
        << s p o >> prov:wasDerivedFrom gdc:submission ; db:confidence 1.0 .
    """
    turtle = graph.serialize(format="turtle")
    if not star_annotations:
        return turtle

    blocks = [
        turtle,
        "",
        "# RDF-star: Provenienz & Konfidenz für Alignment-Aussagen",
        "# (siehe wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL, Abschnitt 4; ADR-0002)",
        "@prefix gdc: <http://databridge.hka/source/gdc#> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "",
    ]
    for subj, pred, obj, source, confidence in star_annotations:
        blocks.append(
            f"<< <{subj}> <{pred}> <{obj}> >>\n"
            f"    prov:wasDerivedFrom {source} ;\n"
            f"    db:confidence {confidence} .\n"
        )
    return "\n".join(blocks)
