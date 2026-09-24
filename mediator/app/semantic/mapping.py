"""Regelbasiertes GDC-Case-JSON -> RDF/OWL-Mapping (ABox).

Setzt die Konstrukt-Regeln aus wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL für
den Ausschnitt case/project/demographic/diagnosis/samples um (Ontologie/TBox
siehe wissensnetz/ontology/databridge-core.ttl, inkl. der für die
Oviedo-Hover-Feldliste ergänzten Properties — siehe
wissensnetz/prototype/mp_lite/HANDOFF.md): enum-Werte werden — wo eine
Alignment-Tabelle einen Treffer liefert — auf externe Bio-Ontologien (hier:
NCIt für primary_diagnosis) abgebildet, sonst bleibt der Rohtext als Literal
erhalten. Kanten-Provenienz/-Konfidenz für Alignment-Aussagen werden über
RDF-star modelliert (siehe serialize_with_provenance).

Global-as-View: GDC ist aktuell die einzige angebundene Quelle, daher ist
diese Übersetzungslogik bewusst quellenspezifisch (siehe Marcels Empfehlung
im Mapping-Konzept: "Für eine Quelle genügt zunächst GaV"). Für eine zweite
Quelle: eigenes mapping_<source>.py nach demselben Muster, siehe
/docs/adding_new_sources.md.

English: Rule-based GDC case JSON -> RDF/OWL mapping (ABox).

Implements the construction rules from
wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL for the
case/project/demographic/diagnosis/samples slice (ontology/TBox: see
wissensnetz/ontology/databridge-core.ttl, including the properties added for
the Oviedo hover field list — see wissensnetz/prototype/mp_lite/HANDOFF.md):
enum values are — where an alignment table has a hit — mapped onto external
bio-ontologies (here: NCIt for primary_diagnosis), otherwise the raw text is
kept as a literal. Edge provenance/confidence for alignment statements is
modeled via RDF-star (see serialize_with_provenance).

Global-as-view: GDC is currently the only connected source, so this
translation logic is deliberately source-specific (see Marcel's
recommendation in the mapping concept: "For one source, GaV is enough for
now"). For a second source: its own mapping_<source>.py following the same
pattern, see /docs/adding_new_sources.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

DB = Namespace("http://databridge.hka/onto#")
NCIT = Namespace("http://purl.obolibrary.org/obo/NCIT_")
PROV = Namespace("http://www.w3.org/ns/prov#")

INSTANCE_BASE = "http://databridge.hka/instance/"

# (Subjekt, Prädikat, Objekt, Quelle-als-Turtle-Term, Konfidenz) für eine noch
# anzuhängende RDF-star-Provenienz-Annotation, siehe serialize_with_provenance.
# EN: (subject, predicate, object, source-as-Turtle-term, confidence) for an
# RDF-star provenance annotation still to be appended, see
# serialize_with_provenance.
StarAnnotation = tuple[URIRef, URIRef, URIRef, str, float]


# ---------------------------------------------------------------------------
# Generisches Attribut-Mapping (M4/M5, siehe
# recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, Abschnitt 3): ein
# UI-"Obj"-Attribut (Trigger) wird auf ein GDC-Feld + eine db:-Property
# abgebildet. Ersetzt die frühere feste if-Kaskade in cases_to_graph.
#
# EN: Generic attribute mapping (M4/M5, see
# recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, section 3): a UI "Obj"
# attribute (trigger) is mapped onto a GDC field + a db: property. Replaces
# the former fixed if-cascade in cases_to_graph.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributeMapping:
    """Wohin (Ziel-Entity/Property) und wie (Datentyp) ein Attribut übersetzt wird.

    English: Where (target entity/property) and how (data type) an attribute is translated.
    """

    gdc_field: str  # Punktpfad wie von GDC geliefert, z. B. "demographic.race" / EN: dotted path as delivered by GDC, e.g. "demographic.race"
    entity: str  # "case" | "project" | "demographic" | "diagnosis" | "sample"
    property_uri: URIRef
    datatype: URIRef = XSD.string


# Bekannte Attribute: Oviedo-/UI-Attributname (siehe Umsetzungsplan Abschnitt
# 1, Teil 1a) -> GDC-Feld + bereits in databridge-core.ttl deklarierte
# db:-Property. `primary_diagnosis` ist hier nur für die Feld-Ableitung
# (resolve_case_fields) gelistet — die ABox-Erzeugung bleibt Sonderfall
# (Alignment + Label-Fallback + RDF-star, siehe cases_to_graph).
# EN: Known attributes: Oviedo/UI attribute name (see implementation plan
# section 1, part 1a) -> GDC field + db: property already declared in
# databridge-core.ttl. `primary_diagnosis` is listed here only for field
# derivation (resolve_case_fields) — ABox generation remains a special case
# (alignment + label fallback + RDF-star, see cases_to_graph).
KNOWN_ATTRIBUTES: dict[str, AttributeMapping] = {
    # GDC hat das Feld von `gender` auf `sex_at_birth` umbenannt; der alte Name
    # existiert in der API nicht mehr (live gegen /files/_mapping und
    # /cases/_mapping geprueft, 2026-09-18). GDC ignoriert unbekannte Felder
    # stillschweigend, deshalb blieb die Spalte lange unbemerkt leer.
    # Der alte UI-Name wird ueber LEGACY_ATTRIBUTE_ALIASES weiter angenommen.
    # EN: GDC renamed the field from `gender` to `sex_at_birth`; the old name
    # no longer exists in the API (checked live against /files/_mapping and
    # /cases/_mapping, 2026-09-18). GDC silently ignores unknown fields,
    # which is why the column stayed unnoticed empty for a long time. The old
    # UI name is still accepted via LEGACY_ATTRIBUTE_ALIASES.
    "sex_at_birth": AttributeMapping("demographic.sex_at_birth", "demographic", DB.sexAtBirth),
    "race": AttributeMapping("demographic.race", "demographic", DB.race),
    "ethnicity": AttributeMapping("demographic.ethnicity", "demographic", DB.ethnicity),
    "vital_status": AttributeMapping("demographic.vital_status", "demographic", DB.vitalStatus),
    "primary_diagnosis": AttributeMapping("diagnoses.primary_diagnosis", "diagnosis", DB.primaryDiagnosisLabel),
    "age_at_diagnosis": AttributeMapping("diagnoses.age_at_diagnosis", "diagnosis", DB.ageAtDiagnosis, XSD.integer),
    "morphology": AttributeMapping("diagnoses.morphology", "diagnosis", DB.morphology),
    "site_of_resection_or_biopsy": AttributeMapping(
        "diagnoses.site_of_resection_or_biopsy", "diagnosis", DB.siteOfResectionOrBiopsy
    ),
    # Oviedo-Attributname "tumor_stage" <-> GDC-Feld "ajcc_pathologic_stage"
    # (GDCs älteres "tumor_stage" existiert im aktuellen Schema nicht, siehe
    # wissensnetz/prototype/mp_lite/HANDOFF.md).
    # EN: Oviedo attribute name "tumor_stage" <-> GDC field
    # "ajcc_pathologic_stage" (GDC's older "tumor_stage" does not exist in
    # the current schema, see wissensnetz/prototype/mp_lite/HANDOFF.md).
    "tumor_stage": AttributeMapping("diagnoses.ajcc_pathologic_stage", "diagnosis", DB.tumorStage),
    "has_metastasis": AttributeMapping("diagnoses.metastasis_at_diagnosis", "diagnosis", DB.metastasisAtDiagnosis),
    "sample_type": AttributeMapping("samples.sample_type", "sample", DB.sampleType),
}

# Alte UI-Attributnamen, die weiterhin akzeptiert werden. Bewusst NICHT in
# KNOWN_ATTRIBUTES: sonst stünden sie doppelt in DEFAULT_ATTRIBUTES und das
# zugehörige GDC-Feld würde zweimal angefragt. Ohne diese Tabelle würde ein
# Aufrufer mit "gender" still auf `diagnoses.gender` umgebogen (siehe
# `resolve_attribute`, dynamischer Pfad) — also falsch statt fehlerhaft.
# EN: Old UI attribute names that are still accepted. Deliberately NOT in
# KNOWN_ATTRIBUTES: otherwise they would appear twice in DEFAULT_ATTRIBUTES
# and the associated GDC field would be requested twice. Without this table,
# a caller using "gender" would be silently bent onto `diagnoses.gender`
# (see `resolve_attribute`, dynamic path) — i.e. wrong instead of erroring.
LEGACY_ATTRIBUTE_ALIASES: dict[str, str] = {
    "gender": "sex_at_birth",
}

# Rückwärtskompatibler Default für Aufrufer, die kein `attributes` angeben
# (z. B. bestehendes POST /transform) — identisch zum bisherigen, fest
# ausprogrammierten Feldumfang.
# EN: Backwards-compatible default for callers that don't specify
# `attributes` (e.g. the existing POST /transform) — identical to the
# previous, fixed hardcoded field scope.
DEFAULT_ATTRIBUTES: list[str] = list(KNOWN_ATTRIBUTES)

_ENTITY_BY_GDC_PREFIX = {
    "demographic": "demographic",
    "diagnoses": "diagnosis",
    "samples": "sample",
    "project": "project",
}
_CLASS_BY_ENTITY = {
    "case": DB.Case,
    "project": DB.Project,
    "demographic": DB.Demographic,
    "diagnosis": DB.Diagnosis,
    "sample": DB.Sample,
}
_CAMEL_CASE_RE = re.compile(r"_([a-zA-Z0-9])")


def _to_camel_case(name: str) -> str:
    """'prior_malignancy' -> 'priorMalignancy' (für dynamisch erzeugte Property-Namen).

    English: 'prior_malignancy' -> 'priorMalignancy' (for dynamically generated property names).
    """
    return _CAMEL_CASE_RE.sub(lambda m: m.group(1).upper(), name)


def _leaf_key(gdc_field: str) -> str:
    """Letztes Pfadsegment eines GDC-Feldpfads, z. B. 'demographic.race' -> 'race'.

    English: Last path segment of a GDC field path, e.g. 'demographic.race' -> 'race'.
    """
    return gdc_field.rsplit(".", 1)[-1]


def resolve_attribute(attribute: str) -> AttributeMapping:
    """Löst ein UI-Attribut (Obj-Trigger) auf ein `AttributeMapping` auf.

    Bekannte Attribute (`KNOWN_ATTRIBUTES`) nutzen ihre feste, in
    databridge-core.ttl deklarierte db:-Property. Veraltete Namen aus
    `LEGACY_ATTRIBUTE_ALIASES` werden vorher umgeschrieben (z. B. "gender" ->
    "sex_at_birth"). Für unbekannte Attribute
    gilt laut Entscheidung 7.5 (Umsetzungsplan_UI-gesteuerte-Akquise.pdf,
    Abschnitt 7.5: "dynamisch anlegen"): das Attribut wird als GDC-Feldpfad
    interpretiert (z. B. "diagnoses.prior_malignancy"; ohne Punkt wird
    "diagnoses.<attribut>" angenommen — die meisten neuen Oviedo-Obj-Felder
    sind klinische Diagnose-Attribute, siehe KNOWN_ATTRIBUTES). Das letzte
    Pfadsegment liefert camelCase den Property-Namen; die Property wird NICHT
    in wissensnetz/ontology/databridge-core.ttl nachgetragen (Wissensnetz
    bleibt Besitzer der kuratierten Basis-Ontologie, siehe wissensnetz/CLAUDE.md),
    sondern inline in der jeweiligen Transform-Ausgabe deklariert (siehe
    `_declare_dynamic_property`), damit der erzeugte Graph für sich genommen
    gültig/selbstbeschreibend bleibt.

    English: Resolves a UI attribute (Obj trigger) to an `AttributeMapping`.

    Known attributes (`KNOWN_ATTRIBUTES`) use their fixed db: property
    declared in databridge-core.ttl. Deprecated names from
    `LEGACY_ATTRIBUTE_ALIASES` are rewritten beforehand (e.g. "gender" ->
    "sex_at_birth"). For unknown attributes, per decision 7.5
    (Umsetzungsplan_UI-gesteuerte-Akquise.pdf, section 7.5: "create
    dynamically"): the attribute is interpreted as a GDC field path (e.g.
    "diagnoses.prior_malignancy"; without a dot, "diagnoses.<attribute>" is
    assumed — most new Oviedo Obj fields are clinical diagnosis attributes,
    see KNOWN_ATTRIBUTES). The last path segment supplies the property name
    in camelCase; the property is NOT added to
    wissensnetz/ontology/databridge-core.ttl (the wissensnetz remains owner
    of the curated base ontology, see wissensnetz/CLAUDE.md), but declared
    inline in the respective transform output (see
    `_declare_dynamic_property`), so the generated graph stays valid/
    self-describing on its own.
    """
    attribute = LEGACY_ATTRIBUTE_ALIASES.get(attribute, attribute)
    known = KNOWN_ATTRIBUTES.get(attribute)
    if known:
        return known
    field = attribute if "." in attribute else f"diagnoses.{attribute}"
    prefix, _, leaf = field.rpartition(".")
    entity = _ENTITY_BY_GDC_PREFIX.get(prefix, "case")
    return AttributeMapping(field, entity, DB[_to_camel_case(leaf)])


def _declare_dynamic_property(graph: Graph, mapping: AttributeMapping, declared: set[str]) -> None:
    """Deklariert eine zur Laufzeit erzeugte Property inline als owl:DatatypeProperty
    (Entscheidung 7.5) — einmal pro Property und erzeugtem Graphen.

    English: Declares a runtime-generated property inline as
    owl:DatatypeProperty (decision 7.5) — once per property and generated graph.
    """
    local_name = str(mapping.property_uri).rsplit("#", 1)[-1]
    if local_name in declared:
        return
    declared.add(local_name)
    graph.add((mapping.property_uri, RDF.type, OWL.DatatypeProperty))
    graph.add((mapping.property_uri, RDFS.label, Literal(local_name)))
    graph.add((mapping.property_uri, RDFS.domain, _CLASS_BY_ENTITY[mapping.entity]))
    graph.add((mapping.property_uri, RDFS.range, mapping.datatype))
    graph.add(
        (
            mapping.property_uri,
            RDFS.comment,
            Literal(
                f"Dynamisch erzeugt aus UI-Attribut (GDC-Feld '{mapping.gdc_field}'), "
                "nicht in wissensnetz/ontology/databridge-core.ttl deklariert."
            ),
        )
    )


def _apply_attributes(
    graph: Graph,
    entity_iri: URIRef,
    source: dict[str, Any],
    mappings: list[tuple[str, AttributeMapping]],
    declared_dynamic: set[str],
) -> None:
    """Schreibt alle für eine Entity-Instanz zuständigen Attribute generisch
    als Literal-Tripel (M5) — ersetzt die frühere if-Kaskade pro Feld.

    English: Writes all attributes responsible for an entity instance
    generically as literal triples (M5) — replaces the former per-field
    if-cascade.
    """
    for attr, mapping in mappings:
        value = source.get(_leaf_key(mapping.gdc_field))
        if value is None or value == "":
            continue
        if attr not in KNOWN_ATTRIBUTES:
            _declare_dynamic_property(graph, mapping, declared_dynamic)
        if mapping.datatype == XSD.integer:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        graph.add((entity_iri, mapping.property_uri, Literal(value, datatype=mapping.datatype)))


def load_alignment_table(path: str | Path) -> dict[str, str]:
    """Lädt die Enum->NCIt-Alignment-Tabelle.

    Fehlt die Datei (z. B. noch nicht befüllt/nicht gemountet), wird eine
    leere Tabelle zurückgegeben — Alignment ist optional, der Fallback auf
    Literal-Text greift dann für alle Werte (siehe cases_to_graph).

    English: Loads the enum -> NCIt alignment table.

    If the file is missing (e.g. not yet populated/mounted), an empty table
    is returned — alignment is optional, the fallback to literal text then
    applies to all values (see cases_to_graph).
    """
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _slug(value: str) -> str:
    """Instanz-IRI-taugliches Fragment aus einem beliebigen Bezeichner (z. B. TCGA-Barcode, UUID).

    English: Instance-IRI-suitable fragment from an arbitrary identifier (e.g. TCGA barcode, UUID).
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"


def _bind_prefixes(graph: Graph) -> None:
    graph.bind("db", DB)
    graph.bind("ncit", NCIT)
    graph.bind("prov", PROV)


def cases_to_graph(
    cases: list[dict[str, Any]],
    *,
    alignment: dict[str, str] | None = None,
    attributes: list[str] | None = None,
) -> tuple[Graph, list[StarAnnotation]]:
    """Übersetzt GDC-`cases`-Treffer in RDF-Tripel (case/project/demographic/diagnoses/samples).

    Erwartet die verschachtelte Form, wie sie GDCWrapper.search("cases",
    fields=[...]) liefert. Welche Attribute (über die Case-/Projekt-Identität
    hinaus) als Tripel geschrieben werden, bestimmt `attributes` — eine Liste
    von UI-Attributnamen (Obj-Trigger, siehe
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf), aufgelöst über
    `resolve_attribute()`. Ohne Angabe gilt `DEFAULT_ATTRIBUTES`
    (rückwärtskompatibel zum bisherigen, fest ausprogrammierten Feldumfang).

    Gibt den Haupt-Graphen sowie eine Liste offener RDF-star-Annotationen
    zurück (Provenienz/Konfidenz für erfolgreiche NCIt-Alignments) — diese
    hängt serialize_with_provenance an die Turtle-Ausgabe an.

    English: Translates GDC `cases` hits into RDF triples
    (case/project/demographic/diagnoses/samples).

    Expects the nested form as delivered by GDCWrapper.search("cases",
    fields=[...]). Which attributes (beyond the case/project identity) are
    written as triples is determined by `attributes` — a list of UI
    attribute names (Obj triggers, see
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf), resolved via
    `resolve_attribute()`. Without one, `DEFAULT_ATTRIBUTES` applies
    (backwards-compatible with the former, fixed hardcoded field scope).

    Returns the main graph as well as a list of open RDF-star annotations
    (provenance/confidence for successful NCIt alignments) — these are
    appended to the Turtle output by serialize_with_provenance.
    """
    alignment = alignment or {}
    attributes = list(attributes) if attributes is not None else DEFAULT_ATTRIBUTES
    graph = Graph()
    _bind_prefixes(graph)
    star_annotations: list[StarAnnotation] = []
    seen_projects: set[str] = set()
    declared_dynamic: set[str] = set()

    # primary_diagnosis bleibt Sonderfall (Alignment + Label-Fallback + RDF-star,
    # siehe unten) — aus der generischen Mapping-Schleife ausgenommen.
    # EN: primary_diagnosis remains a special case (alignment + label
    # fallback + RDF-star, see below) — excluded from the generic mapping loop.
    resolved_by_entity: dict[str, list[tuple[str, AttributeMapping]]] = {}
    for attr in attributes:
        if attr == "primary_diagnosis":
            continue
        mapping = resolve_attribute(attr)
        resolved_by_entity.setdefault(mapping.entity, []).append((attr, mapping))
    include_primary_diagnosis = "primary_diagnosis" in attributes

    for case in cases:
        case_id = case.get("case_id") or case.get("submitter_id")
        if not case_id:
            continue
        case_iri = URIRef(f"{INSTANCE_BASE}case/{_slug(case_id)}")
        graph.add((case_iri, RDF.type, DB.Case))
        graph.add((case_iri, DB.caseId, Literal(case_id, datatype=XSD.string)))
        if case.get("submitter_id"):
            graph.add((case_iri, DB.submitterId, Literal(case["submitter_id"], datatype=XSD.string)))
        _apply_attributes(graph, case_iri, case, resolved_by_entity.get("case", []), declared_dynamic)

        project = case.get("project") or {}
        project_id = project.get("project_id")
        if project_id:
            project_iri = URIRef(f"{INSTANCE_BASE}project/{_slug(project_id)}")
            if project_id not in seen_projects:
                graph.add((project_iri, RDF.type, DB.Project))
                graph.add((project_iri, DB.projectId, Literal(project_id, datatype=XSD.string)))
                _apply_attributes(
                    graph, project_iri, project, resolved_by_entity.get("project", []), declared_dynamic
                )
                seen_projects.add(project_id)
            graph.add((case_iri, DB.belongsToProject, project_iri))
            graph.add((project_iri, DB.hasCase, case_iri))

        demographic = case.get("demographic") or {}
        if demographic:
            demo_iri = URIRef(f"{INSTANCE_BASE}demographic/{_slug(case_id)}")
            graph.add((demo_iri, RDF.type, DB.Demographic))
            _apply_attributes(
                graph, demo_iri, demographic, resolved_by_entity.get("demographic", []), declared_dynamic
            )
            graph.add((case_iri, DB.hasDemographic, demo_iri))
            graph.add((demo_iri, DB.isDemographicOf, case_iri))

        for idx, sample in enumerate(case.get("samples") or []):
            sample_key = sample.get("sample_id") or f"{case_id}-sample{idx}"
            sample_iri = URIRef(f"{INSTANCE_BASE}sample/{_slug(sample_key)}")
            graph.add((sample_iri, RDF.type, DB.Sample))
            _apply_attributes(graph, sample_iri, sample, resolved_by_entity.get("sample", []), declared_dynamic)
            graph.add((case_iri, DB.hasSample, sample_iri))
            graph.add((sample_iri, DB.isSampleOf, case_iri))

        for idx, diagnosis in enumerate(case.get("diagnoses") or []):
            diag_key = diagnosis.get("diagnosis_id") or f"{case_id}-diag{idx}"
            diag_iri = URIRef(f"{INSTANCE_BASE}diagnosis/{_slug(diag_key)}")
            graph.add((diag_iri, RDF.type, DB.Diagnosis))
            graph.add((diag_iri, DB.describesCase, case_iri))
            graph.add((case_iri, DB.hasDiagnosis, diag_iri))
            _apply_attributes(graph, diag_iri, diagnosis, resolved_by_entity.get("diagnosis", []), declared_dynamic)

            if include_primary_diagnosis:
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

    return graph, star_annotations


def serialize_with_provenance(graph: Graph, star_annotations: list[StarAnnotation]) -> str:
    """Serialisiert den Graphen nach Turtle und hängt RDF-star-Provenienz-Blöcke an.

    RDF-star wird hier bewusst als Text angehängt statt über eine
    rdflib-interne Quoted-Triple-API erzeugt — die Turtle-Star-Unterstützung
    unterscheidet sich je rdflib-Version, während dieses Textformat exakt dem
    Beispiel aus wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL entspricht und
    damit garantiert spezifikationskonform bleibt:
        << s p o >> prov:wasDerivedFrom gdc:submission ; db:confidence 1.0 .

    English: Serializes the graph to Turtle and appends RDF-star provenance
    blocks.

    RDF-star is deliberately appended here as text instead of generated via
    an rdflib-internal quoted-triple API — Turtle-star support differs per
    rdflib version, while this text format matches exactly the example from
    wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL and thus stays guaranteed
    spec-compliant:
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
