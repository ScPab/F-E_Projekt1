"""Regelbasiertes cBioPortal-Klinikdaten-JSON -> RDF/OWL-Mapping (ABox).

Anders als GDC/GEO/ENA liefert `CBioPortalWrapper.get_clinical_data()` die
Daten im **Long-Format** (eine Zeile je Attribut/Wert-Paar, Spalten
`patientId`/`sampleId`/`clinicalAttributeId`/`value`, siehe
`wrappers/cbioportal/client.py`) statt einem Datensatz je Case/Sample. Dieses
Modul pivotiert daher zuerst nach `patientId`/`sampleId`, bevor die
Konstrukt-Regeln angewendet werden.

Wiederverwendung statt Duplikat (siehe wissensnetz/ontology/databridge-core.ttl,
Abschnitt "Erweiterung: GEO, ENA, cBioPortal"): cBioPortal bereitet häufig
dieselben TCGA/GDC-Ursprungsdaten auf, daher nutzt dieses Modul bewusst die
bestehenden Klassen/Properties `db:Project`/`db:Case`/`db:Demographic`/
`db:Diagnosis`/`db:Sample` (statt eigener cBioPortal-spezifischer Duplikate).
Die PATIENT-Attribute werden dazu — wie bei GDC (`mapping.py`) — auf
`db:Demographic` (`sexAtBirth`/`race`/`ethnicity`/`vitalStatus`, rdfs:domain in
der Ontologie) bzw. `db:Diagnosis` (`tumorStage`) verteilt statt direkt auf
`db:Case` geschrieben zu werden; nur `db:age` ist bewusst eine eigene,
Case-direkte Property (siehe Ontologie-Kommentar zu `db:age`: anders als
`db:ageAtDiagnosis` nicht an ein Diagnose-Ereignis gebunden).

`clinicalAttributeId`s sind laut Wrapper-Docstring studienspezifisch, nicht
global standardisiert — die Attribut-Tabellen unten decken daher bewusst nur
die über TCGA-abgeleitete Studien hinweg gebräuchlichen IDs ab (analog zum
Kern-Ausschnitt case/project/demographic/diagnosis bei GDC). Unbekannte
Attribute werden ignoriert statt geraten zu mappen.

Kein Enum-Alignment für diesen ersten Ausschnitt, daher immer eine leere
Liste von RDF-star-Annotationen — Rückgabeform identisch zu
`mapping.cases_to_graph`, damit `serialize_with_provenance` unverändert
wiederverwendet werden kann.

English: Rule-based cBioPortal clinical-data JSON -> RDF/OWL mapping (ABox).

Unlike GDC/GEO/ENA, `CBioPortalWrapper.get_clinical_data()` delivers the
data in **long format** (one row per attribute/value pair, columns
`patientId`/`sampleId`/`clinicalAttributeId`/`value`, see
`wrappers/cbioportal/client.py`) instead of one record per case/sample.
This module therefore pivots by `patientId`/`sampleId` first, before
applying the construction rules.

Reuse instead of duplication (see
wissensnetz/ontology/databridge-core.ttl, section "Extension: GEO, ENA,
cBioPortal"): cBioPortal frequently curates the same TCGA/GDC origin data,
so this module deliberately uses the existing classes/properties
`db:Project`/`db:Case`/`db:Demographic`/`db:Diagnosis`/`db:Sample` (instead
of its own cBioPortal-specific duplicates). The PATIENT attributes are
accordingly distributed — as with GDC (`mapping.py`) — onto `db:Demographic`
(`sexAtBirth`/`race`/`ethnicity`/`vitalStatus`, rdfs:domain in the ontology)
or `db:Diagnosis` (`tumorStage`) instead of being written directly onto
`db:Case`; only `db:age` is deliberately its own, case-direct property (see
the ontology comment on `db:age`: unlike `db:ageAtDiagnosis`, not tied to a
diagnosis event).

Per the wrapper docstring, `clinicalAttributeId`s are study-specific, not
globally standardized — the attribute tables below therefore deliberately
cover only the IDs common across TCGA-derived studies (analogous to the
case/project/demographic/diagnosis core slice for GDC). Unknown attributes
are ignored instead of being guess-mapped.

No enum alignment for this first slice, hence always an empty list of
RDF-star annotations — return shape identical to `mapping.cases_to_graph`,
so `serialize_with_provenance` can be reused unchanged.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

DB = Namespace("http://databridge.hka/onto#")
INSTANCE_BASE = "http://databridge.hka/instance/"

StarAnnotation = tuple[URIRef, URIRef, URIRef, str, float]

AttributeMap = dict[str, tuple[str, Callable[[str], Any]]]

# clinicalAttributeId (PATIENT) -> (db:-Property, Cast-Funktion), je Ziel-Node.
# Mehrere IDs je Property, weil Studien dasselbe Konzept unterschiedlich
# benennen (z. B. "SEX" vs. "GENDER").
# EN: clinicalAttributeId (PATIENT) -> (db: property, cast function), per
# target node. Multiple IDs per property because studies name the same
# concept differently (e.g. "SEX" vs. "GENDER").
DEMOGRAPHIC_ATTRIBUTE_MAP: AttributeMap = {
    "SEX": ("sexAtBirth", str),
    "GENDER": ("sexAtBirth", str),
    "VITAL_STATUS": ("vitalStatus", str),
    "RACE": ("race", str),
    "ETHNICITY": ("ethnicity", str),
}
DIAGNOSIS_ATTRIBUTE_MAP: AttributeMap = {
    "AJCC_PATHOLOGIC_TUMOR_STAGE": ("tumorStage", str),
    "TUMOR_STAGE": ("tumorStage", str),
}
CASE_ATTRIBUTE_MAP: AttributeMap = {
    "AGE": ("age", int),
}

# clinicalAttributeId (SAMPLE) -> (db:-Property, Cast-Funktion).
# EN: clinicalAttributeId (SAMPLE) -> (db: property, cast function).
SAMPLE_ATTRIBUTE_MAP: AttributeMap = {
    "SAMPLE_TYPE": ("sampleType", str),
    "ONCOTREE_CODE": ("oncotreeCode", str),
}

_XSD_BY_CAST = {str: XSD.string, int: XSD.integer}


def _slug(value: str) -> str:
    """Instanz-IRI-taugliches Fragment aus einem beliebigen Bezeichner (siehe mapping.py).

    English: Instance-IRI-suitable fragment from an arbitrary identifier (see mapping.py).
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"


def _bind_prefixes(graph: Graph) -> None:
    graph.bind("db", DB)


def _pivot(rows: list[dict[str, Any]], id_key: str) -> dict[str, dict[str, str]]:
    """Long-Format (eine Zeile je Attribut) -> Wide-Format ({id: {attribut: wert}}).

    English: Long format (one row per attribute) -> wide format ({id: {attribute: value}}).
    """
    pivoted: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get(id_key)
        attribute_id = row.get("clinicalAttributeId")
        value = row.get("value")
        if not entity_id or not attribute_id or value is None:
            continue
        pivoted.setdefault(entity_id, {})[attribute_id] = value
    return pivoted


def _apply_attributes(graph: Graph, subject: URIRef, attributes: dict[str, str], attribute_map: AttributeMap) -> bool:
    """Schreibt bekannte Attribute auf `subject`; gibt zurück, ob mindestens eines geschrieben wurde.

    English: Writes known attributes onto `subject`; returns whether at least one was written.
    """
    wrote_any = False
    for attribute_id, value in attributes.items():
        mapping = attribute_map.get(attribute_id)
        if not mapping:
            continue
        prop_name, cast = mapping
        try:
            cast_value = cast(value)
        except (TypeError, ValueError):
            continue
        graph.add((subject, DB[prop_name], Literal(cast_value, datatype=_XSD_BY_CAST[cast])))
        wrote_any = True
    return wrote_any


def clinical_data_to_graph(
    patient_rows: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]],
    *,
    study_id: str,
) -> tuple[Graph, list[StarAnnotation]]:
    """Übersetzt cBioPortal-Klinikdaten (PATIENT- + SAMPLE-Ebene) einer Studie in RDF-Tripel.

    `patient_rows`/`sample_rows`: Rohe `results`-Listen von
    `CBioPortalWrapper.get_clinical_data(study_id, clinical_data_type="PATIENT"|"SAMPLE")`.
    Erzeugt einen `db:Project` (aus `study_id`, ohne Namens-/Beschreibungs-
    Anreicherung — analog zu GDCs `db:Project`, das ebenfalls nur die ID
    trägt), je einen `db:Case` pro Patient (plus bei Bedarf verknüpftes
    `db:Demographic`/`db:Diagnosis`, siehe Modul-Docstring) sowie einen
    `db:Sample` pro Probe, verknüpft über `db:hasSample`/`db:isSampleOf`
    (dieselben Properties wie bei GDC).

    English: Translates cBioPortal clinical data (PATIENT + SAMPLE level) of
    a study into RDF triples.

    `patient_rows`/`sample_rows`: raw `results` lists from
    `CBioPortalWrapper.get_clinical_data(study_id,
    clinical_data_type="PATIENT"|"SAMPLE")`. Generates a `db:Project` (from
    `study_id`, without name/description enrichment — analogous to GDC's
    `db:Project`, which also carries only the ID), one `db:Case` per patient
    (plus a linked `db:Demographic`/`db:Diagnosis` as needed, see module
    docstring), and a `db:Sample` per sample, linked via
    `db:hasSample`/`db:isSampleOf` (the same properties as with GDC).
    """
    graph = Graph()
    _bind_prefixes(graph)

    project_iri = URIRef(f"{INSTANCE_BASE}project/{_slug(study_id)}")
    graph.add((project_iri, RDF.type, DB.Project))
    graph.add((project_iri, DB.projectId, Literal(study_id, datatype=XSD.string)))

    patients = _pivot(patient_rows, "patientId")
    for patient_id, attributes in patients.items():
        case_iri = URIRef(f"{INSTANCE_BASE}case/{_slug(patient_id)}")
        graph.add((case_iri, RDF.type, DB.Case))
        graph.add((case_iri, DB.caseId, Literal(patient_id, datatype=XSD.string)))
        graph.add((case_iri, DB.belongsToProject, project_iri))
        graph.add((project_iri, DB.hasCase, case_iri))
        _apply_attributes(graph, case_iri, attributes, CASE_ATTRIBUTE_MAP)

        demo_iri = URIRef(f"{INSTANCE_BASE}demographic/{_slug(patient_id)}")
        if _apply_attributes(graph, demo_iri, attributes, DEMOGRAPHIC_ATTRIBUTE_MAP):
            graph.add((demo_iri, RDF.type, DB.Demographic))
            graph.add((case_iri, DB.hasDemographic, demo_iri))
            graph.add((demo_iri, DB.isDemographicOf, case_iri))

        diag_iri = URIRef(f"{INSTANCE_BASE}diagnosis/{_slug(patient_id)}")
        if _apply_attributes(graph, diag_iri, attributes, DIAGNOSIS_ATTRIBUTE_MAP):
            graph.add((diag_iri, RDF.type, DB.Diagnosis))
            graph.add((diag_iri, DB.describesCase, case_iri))
            graph.add((case_iri, DB.hasDiagnosis, diag_iri))

    samples = _pivot(sample_rows, "sampleId")
    sample_to_patient = {row["sampleId"]: row.get("patientId") for row in sample_rows if row.get("sampleId")}
    for sample_id, attributes in samples.items():
        sample_iri = URIRef(f"{INSTANCE_BASE}sample/{_slug(sample_id)}")
        graph.add((sample_iri, RDF.type, DB.Sample))
        _apply_attributes(graph, sample_iri, attributes, SAMPLE_ATTRIBUTE_MAP)

        patient_id = sample_to_patient.get(sample_id)
        if patient_id:
            case_iri = URIRef(f"{INSTANCE_BASE}case/{_slug(patient_id)}")
            graph.add((case_iri, DB.hasSample, sample_iri))
            graph.add((sample_iri, DB.isSampleOf, case_iri))

    return graph, []
