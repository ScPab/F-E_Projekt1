"""
DataBridge Mediator – FastAPI-Grundgerüst.

Der Mediator ist der zentrale Einstiegspunkt der Mediator-Wrapper-Architektur:
Er nimmt Anfragen entgegen und delegiert sie an die passenden Wrapper-Module
(wrappers/gdc, wrappers/geo, wrappers/ena, wrappers/cbioportal, als
Python-Package im selben Container installiert, siehe
docs/adr/0001-wrapper-als-python-package.md) für die eigentliche
Datenbeschaffung.

Die hier exponierten Endpunkte (/query, /schema/{endpoint}, /manifest)
bilden die Schnittstelle, über die spätere Aufrufer (Frontend, andere
Services) auf den GDC-Wrapper zugreifen — ohne dass der GDC-Wrapper selbst
ein eigener Netzwerk-Service sein muss.

Die semantische Transformation (GDC-JSON -> RDF/OWL) für den Ausschnitt
case/project/demographic/diagnosis/samples ist über POST /transform
angebunden (siehe app/semantic/mapping.py). Die Transformation nach
anndata/.h5ad (Expressionsmatrizen, Teil 3 aus wissensnetz/HANDOFF_anndata.md)
ist über POST /export/anndata angebunden (siehe app/semantic/expression.py).
"""

import os
from pathlib import Path
from typing import Any, Optional

from cbioportal import CBioPortalWrapper
from ena import ENAWrapper
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from gdc import GDCWrapper, build_filters
from geo import GEOWrapper
from requests import RequestException
from wissensnetz import GraphStore, GraphStoreError, all_cases

from .schemas import (
    AnndataExportRequest,
    CBioMolecularDataRequest,
    EnaQueryRequest,
    GeoQueryRequest,
    ManifestRequest,
    QueryRequest,
    SelectionGenerateResponse,
    SelectionLevelResult,
    SelectionPreviewResponse,
    SelectionRequest,
    SingleSelection,
    TransformRequest,
)
from .semantic import expression as expression_export
from .semantic import mapping as semantic_mapping
from .semantic import mapping_cbioportal, mapping_ena, mapping_geo
from .semantic.paths import alignment_path, export_dir, ontology_path

# Felder, die für JEDE Case-Abfrage strukturell nötig sind (Identität/
# Join-Schlüssel bzw. Instanz-IRI-Bildung, siehe cases_to_graph) — unabhängig
# davon, welche Attribute die UI zusätzlich anfordert.
BASE_CASE_FIELDS = ["case_id", "submitter_id", "project.project_id", "samples.sample_id"]


def resolve_case_fields(attributes: list[str]) -> list[str]:
    """Leitet die bei GDC anzufragenden Felder aus UI-Attributen ab (M4, siehe
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, Abschnitt 3: "TRANSFORM_CASE_FIELDS
    von Konstante zu abgeleitet ... Kern der Trigger-Idee").

    `BASE_CASE_FIELDS` sind immer dabei; für jedes Attribut kommt das über
    `semantic_mapping.resolve_attribute` aufgelöste GDC-Feld hinzu — bekannte
    Oviedo-Attributnamen (KNOWN_ATTRIBUTES) ebenso wie neue, deren Property
    laut Entscheidung 7.5 dynamisch entsteht.
    """
    fields = list(BASE_CASE_FIELDS)
    for attr in attributes:
        gdc_field = semantic_mapping.resolve_attribute(attr).gdc_field
        if gdc_field not in fields:
            fields.append(gdc_field)
    return fields


# Rückwärtskompatibler Default für POST /transform (unverändertes Verhalten:
# derselbe Feldumfang wie die frühere feste Konstante — DEFAULT_ATTRIBUTES
# deckt exakt dieselben 11 Attribute ab, siehe app/semantic/mapping.py).
TRANSFORM_CASE_FIELDS = resolve_case_fields(semantic_mapping.DEFAULT_ATTRIBUTES)


def fetch_selection_files(
    wrapper: GDCWrapper,
    *,
    cohorts: list[str],
    attributes: list[str],
    experimental_strategy: str,
    data_type: str,
    size: int,
    per_cohort_size: int | None,
) -> tuple[list[dict], list[dict], list[str]]:
    """Der gemeinsame Abrufschritt (M3, siehe
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, Abschnitt 1b/3):
    EIN Files-Query pro Kohorte liefert gleichzeitig die Datei/Proben-Zuordnung
    (Grundlage für anndata, siehe `_build_anndata_from_hits`) UND die
    eingebetteten Case-Objekte (Grundlage für `cases_to_graph`) — GDC liefert
    bei `cases.<feld>`-Feldern dieselbe verschachtelte Case-Struktur wie der
    eigenständige `/cases`-Endpunkt direkt mit den Datei-Treffern mit (live
    verifiziert). Ersetzt die früher zwei unabhängig gezogenen Stichproben
    (`/transform`s eigener `search("cases", ...)` und `/export/anndata`s
    `query("files", ...)` mit kleinerer Feldliste, siehe Modul-Docstring
    Abschnitt 1b des Plans) durch einen einzigen Abruf, stratifiziert pro
    Kohorte (siehe wissensnetz/HANDOFF_export_stratified.md).

    Gibt `(hits, cases, failed_cohorts)` zurück: `hits` roh (Datei-Treffer,
    für die Datei/Proben-Zuordnung und das Manifest), `cases` nach `case_id`/
    `submitter_id` dedupliziert (direkt `cases_to_graph`-kompatibel, ohne
    Umformung — dieselbe verschachtelte Form wie von GDCs `/cases`),
    `failed_cohorts` für Kohorten, deren Query fehlschlug (killt nicht den
    gesamten Abruf, siehe wissensnetz/HANDOFF_export_stratified.md).
    """
    file_fields = ["file_id", "file_name"] + [f"cases.{f}" for f in resolve_case_fields(attributes)]
    n_each = per_cohort_size or size

    hits: list[dict] = []
    failed_cohorts: list[str] = []
    for cohort in cohorts:
        filters = build_filters(
            project_id=cohort,
            experimental_strategy=experimental_strategy,
            access="open",
            extra=[{"op": "in", "content": {"field": "files.data_type", "value": [data_type]}}],
        )
        try:
            result = wrapper.query("files", filters=filters, fields=file_fields, size=n_each)
        except RequestException:
            # eine leere/kaputte Kohorte soll nicht den ganzen Abruf killen
            failed_cohorts.append(cohort)
            continue
        hits.extend(result["results"])

    cases_by_id: dict[str, dict] = {}
    for hit in hits:
        for case in hit.get("cases") or []:
            case_key = case.get("case_id") or case.get("submitter_id")
            if case_key and case_key not in cases_by_id:
                cases_by_id[case_key] = case

    return hits, list(cases_by_id.values()), failed_cohorts


app = FastAPI(
    title="DataBridge Mediator",
    description="Zentraler Mediator-Service der DataBridge-Architektur (Mediator-Wrapper-Muster).",
    version="0.1.0",
)

# Einzelne, wiederverwendete Wrapper-Instanz (hält u. a. die requests.Session
# und den Cache-Zugriffspunkt, siehe wrappers/gdc/cache.py).
_gdc_wrapper: GDCWrapper | None = None

# Analog wiederverwendete Instanzen für die weiteren Wrapper (siehe
# wrappers/geo, wrappers/ena, wrappers/cbioportal).
_geo_wrapper: GEOWrapper | None = None
_ena_wrapper: ENAWrapper | None = None
_cbioportal_wrapper: CBioPortalWrapper | None = None

# Einzelne, wiederverwendete GraphStore-Instanz (Fuseki-Anbindung für
# POST /transform mit load=true). Verbindung wird aus ENV gelesen
# (GRAPH_DB_URL/GRAPH_DB_DATASET/..., siehe wissensnetz/src/wissensnetz/config.py
# und docker-compose.yml für den Compose-internen Wert).
_graph_store: GraphStore | None = None


def get_gdc_wrapper() -> GDCWrapper:
    """Liefert eine lazily initialisierte, geteilte GDCWrapper-Instanz."""
    global _gdc_wrapper
    if _gdc_wrapper is None:
        base_url = os.environ.get("GDC_API_BASE_URL", "https://api.gdc.cancer.gov")
        _gdc_wrapper = GDCWrapper(base_url)
    return _gdc_wrapper


def get_geo_wrapper() -> GEOWrapper:
    """Liefert eine lazily initialisierte, geteilte GEOWrapper-Instanz."""
    global _geo_wrapper
    if _geo_wrapper is None:
        base_url = os.environ.get("GEO_API_BASE_URL", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
        _geo_wrapper = GEOWrapper(base_url)
    return _geo_wrapper


def get_ena_wrapper() -> ENAWrapper:
    """Liefert eine lazily initialisierte, geteilte ENAWrapper-Instanz."""
    global _ena_wrapper
    if _ena_wrapper is None:
        base_url = os.environ.get("ENA_API_BASE_URL", "https://www.ebi.ac.uk/ena/portal/api")
        _ena_wrapper = ENAWrapper(base_url)
    return _ena_wrapper


def get_cbioportal_wrapper() -> CBioPortalWrapper:
    """Liefert eine lazily initialisierte, geteilte CBioPortalWrapper-Instanz."""
    global _cbioportal_wrapper
    if _cbioportal_wrapper is None:
        base_url = os.environ.get("CBIOPORTAL_API_BASE_URL", "https://www.cbioportal.org/api")
        _cbioportal_wrapper = CBioPortalWrapper(base_url)
    return _cbioportal_wrapper


def get_graph_store() -> GraphStore:
    """Liefert eine lazily initialisierte, geteilte GraphStore-Instanz."""
    global _graph_store
    if _graph_store is None:
        _graph_store = GraphStore()
    return _graph_store


@app.get("/health")
async def health() -> dict[str, str]:
    """Einfacher Health-Check, damit Orchestrierung (z. B. Docker Compose) den Service prüfen kann."""
    return {"status": "ok"}


@app.post("/query")
async def query(request: QueryRequest) -> dict:
    """Metadaten-Suche gegen GDC (Testfall: TCGA-BRCA / RNA-Seq / open).

    Delegiert an GDCWrapper.search — vereinfachte Suchparameter werden dort
    in einen validen GDC-`filters`-Query übersetzt.
    """
    wrapper = get_gdc_wrapper()
    try:
        return wrapper.search(
            request.endpoint,
            project_id=request.project_id,
            experimental_strategy=request.experimental_strategy,
            access=request.access,
            fields=request.fields,
            size=request.size,
            from_=request.from_,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GDC-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/schema/{endpoint}")
async def schema(endpoint: str) -> dict:
    """Verfügbare Felder eines GDC-Endpunkts (cases/files/projects/annotations).

    Vorbereitung für die spätere Ontologie-/Mapping-Schicht, siehe
    wrappers/gdc/client.py (Modul-Docstring, `get_schema`).
    """
    wrapper = get_gdc_wrapper()
    try:
        fields = wrapper.get_schema(endpoint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GDC-API nicht erreichbar oder Fehler: {exc}") from exc
    return {"endpoint": endpoint, "fields": fields}


@app.post("/manifest")
async def manifest(request: ManifestRequest) -> dict:
    """Manifest (Bulk-Tier) für eine Files-Query erzeugen, zur Übergabe an gdc-client."""
    wrapper = get_gdc_wrapper()
    filters = build_filters(
        project_id=request.project_id,
        experimental_strategy=request.experimental_strategy,
        access=request.access,
    )
    try:
        content = wrapper.build_manifest(filters=filters, size=request.size)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GDC-API nicht erreichbar oder Fehler: {exc}") from exc
    return {"manifest": content}


# ----------------------------------------------------------------------
# GEO (Gene Expression Omnibus), siehe wrappers/geo/client.py
# ----------------------------------------------------------------------


@app.post("/geo/query")
async def geo_query(request: GeoQueryRequest) -> dict:
    """Metadaten-Suche gegen GEO (esearch+esummary), analog zu POST /query."""
    wrapper = get_geo_wrapper()
    try:
        return wrapper.search(
            accession=request.accession,
            organism=request.organism,
            entry_type=request.entry_type,
            db=request.db,
            size=request.size,
            from_=request.from_,
        )
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GEO-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/geo/schema")
async def geo_schema(db: str = "gds") -> dict:
    """Verfügbare Such-Feld-Tags einer GEO/Entrez-Datenbank (einfo), analog zu GET /schema/{endpoint}."""
    wrapper = get_geo_wrapper()
    try:
        fields = wrapper.get_schema(db)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GEO-API nicht erreichbar oder Fehler: {exc}") from exc
    return {"db": db, "fields": fields}


@app.get("/geo/ftp-link/{accession}")
async def geo_ftp_link(accession: str) -> dict:
    """FTP-Verzeichnislink einer GEO-Accession (Bulk-Tier-Äquivalent zu POST /manifest)."""
    wrapper = get_geo_wrapper()
    try:
        link = wrapper.get_ftp_link(accession)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GEO-API nicht erreichbar oder Fehler: {exc}") from exc
    if link is None:
        raise HTTPException(status_code=404, detail=f"Keine GEO-Accession gefunden: {accession!r}")
    return {"accession": accession, "ftp_link": link}


# ----------------------------------------------------------------------
# ENA (European Nucleotide Archive), siehe wrappers/ena/client.py
# ----------------------------------------------------------------------


@app.post("/ena/query")
async def ena_query(request: EnaQueryRequest) -> dict:
    """Metadaten-Suche gegen ENA (/search), analog zu POST /query."""
    wrapper = get_ena_wrapper()
    try:
        return wrapper.search(
            result=request.result,
            study_accession=request.study_accession,
            library_strategy=request.library_strategy,
            instrument_platform=request.instrument_platform,
            fields=request.fields,
            size=request.size,
            from_=request.from_,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ENA-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/ena/schema/{result}")
async def ena_schema(result: str) -> dict:
    """Verfügbare Feldnamen eines ENA-Ergebnistyps (/returnFields), analog zu GET /schema/{endpoint}."""
    wrapper = get_ena_wrapper()
    try:
        fields = wrapper.get_schema(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ENA-API nicht erreichbar oder Fehler: {exc}") from exc
    return {"result": result, "fields": fields}


@app.get("/ena/download-links/{run_accession}")
async def ena_download_links(run_accession: str) -> dict:
    """FASTQ-Download-URLs eines Read-Runs (Bulk-Tier-Äquivalent zu POST /manifest)."""
    wrapper = get_ena_wrapper()
    try:
        return wrapper.get_download_links(run_accession)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ENA-API nicht erreichbar oder Fehler: {exc}") from exc


# ----------------------------------------------------------------------
# cBioPortal, siehe wrappers/cbioportal/client.py
# ----------------------------------------------------------------------


@app.get("/cbioportal/studies")
async def cbioportal_studies(
    keyword: str | None = None,
    size: int = 20,
    from_: int = Query(0, alias="from"),
) -> dict:
    """Studien-Suche gegen cBioPortal (/studies), analog zu POST /query."""
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.list_studies(keyword=keyword, size=size, from_=from_)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/cbioportal/schema/{study_id}")
async def cbioportal_schema(study_id: str) -> dict:
    """Klinische Attribut-IDs einer Studie, analog zu GET /schema/{endpoint}."""
    wrapper = get_cbioportal_wrapper()
    try:
        fields = wrapper.get_schema(study_id)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc
    return {"study_id": study_id, "fields": fields}


@app.get("/cbioportal/clinical-data/{study_id}")
async def cbioportal_clinical_data(
    study_id: str,
    clinical_data_type: str = "PATIENT",
    size: int = 20,
    from_: int = Query(0, alias="from"),
) -> dict:
    """Klinische Datenpunkte (Attribut/Wert je Patient oder Sample) einer Studie."""
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.get_clinical_data(
            study_id, clinical_data_type=clinical_data_type, size=size, from_=from_
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/cbioportal/molecular-profiles/{study_id}")
async def cbioportal_molecular_profiles(study_id: str) -> list[dict]:
    """Verfügbare molekulare Profile einer Studie (Vorbereitung für /cbioportal/molecular-data)."""
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.list_molecular_profiles(study_id)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/cbioportal/sample-lists/{study_id}")
async def cbioportal_sample_lists(study_id: str) -> list[dict]:
    """Vordefinierte Sample-Listen einer Studie (Vorbereitung für /cbioportal/molecular-data)."""
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.list_sample_lists(study_id)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.post("/cbioportal/molecular-data/{molecular_profile_id}")
async def cbioportal_molecular_data(
    molecular_profile_id: str, request: CBioMolecularDataRequest
) -> dict:
    """Genomische Profildaten für eine Gen-/Sample-Auswahl (Bulk-Tier-Äquivalent zu POST /manifest)."""
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.get_molecular_data(
            molecular_profile_id,
            sample_list_id=request.sample_list_id,
            entrez_gene_ids=request.entrez_gene_ids,
            projection=request.projection,
        )
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.post("/transform")
async def transform(request: TransformRequest) -> dict:
    """Quell-JSON -> RDF/OWL-Tripel (Turtle), je `source` über ein eigenes Mapping-Modul.

    - `gdc`: GDC-Cases -> RDF/OWL, gemäß wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL
      (`app/semantic/mapping.py`) — inkl. NCIt-Alignment mit RDF-star-Provenienz.
    - `geo`: GEO-Series -> RDF/OWL (`app/semantic/mapping_geo.py`).
    - `ena`: ENA-Runs -> RDF/OWL (`app/semantic/mapping_ena.py`).
    - `cbioportal`: cBioPortal-Klinikdaten einer Studie -> RDF/OWL
      (`app/semantic/mapping_cbioportal.py`), erfordert `study_id`.

    Nimmt je Quelle entweder rohe Treffer entgegen oder holt sie live über
    den passenden Wrapper (siehe TransformRequest-Feldbeschreibungen).
    Ausgabe ist immer der erzeugte Turtle-Text; bei `load=true` wird er
    zusätzlich direkt per Graph Store Protocol in graph-db (Fuseki)
    geschrieben (siehe `wissensnetz.GraphStore.load_turtle`, ADR-0002) — die
    Turtle-Ausgabe bleibt roh erhalten, damit bei `gdc` die angehängten
    RDF-star-Blöcke (Provenienz/Konfidenz) nicht durch einen rdflib-Roundtrip
    verloren gehen.
    """
    if request.source == "gdc":
        if request.cases is not None:
            cases = request.cases
        else:
            wrapper = get_gdc_wrapper()
            try:
                result = wrapper.search(
                    "cases",
                    project_id=request.project_id,
                    access=request.access,
                    fields=TRANSFORM_CASE_FIELDS,
                    size=request.size,
                )
            except RequestException as exc:
                raise HTTPException(status_code=502, detail=f"GDC-API nicht erreichbar oder Fehler: {exc}") from exc
            cases = result["results"]

        alignment = semantic_mapping.load_alignment_table(alignment_path("ncit_primary_diagnosis.json"))
        graph, star_annotations = semantic_mapping.cases_to_graph(cases, alignment=alignment)

    elif request.source == "geo":
        if request.series is not None:
            series = request.series
        else:
            wrapper = get_geo_wrapper()
            try:
                result = wrapper.search(organism=request.organism, entry_type="gse", size=request.size)
            except RequestException as exc:
                raise HTTPException(status_code=502, detail=f"GEO-API nicht erreichbar oder Fehler: {exc}") from exc
            series = result["results"]
        graph, star_annotations = mapping_geo.series_to_graph(series)

    elif request.source == "ena":
        if request.runs is not None:
            runs = request.runs
        else:
            wrapper = get_ena_wrapper()
            try:
                result = wrapper.search(
                    result="read_run",
                    study_accession=request.study_accession,
                    fields=[
                        "run_accession",
                        "study_accession",
                        "description",
                        "library_strategy",
                        "instrument_platform",
                        "scientific_name",
                        "read_count",
                    ],
                    size=request.size,
                )
            except RequestException as exc:
                raise HTTPException(status_code=502, detail=f"ENA-API nicht erreichbar oder Fehler: {exc}") from exc
            runs = result["results"]
        graph, star_annotations = mapping_ena.runs_to_graph(runs)

    elif request.source == "cbioportal":
        if not request.study_id:
            raise HTTPException(status_code=400, detail="source='cbioportal' erfordert 'study_id'.")
        if request.patient_data is not None and request.sample_data is not None:
            patient_data, sample_data = request.patient_data, request.sample_data
        else:
            wrapper = get_cbioportal_wrapper()
            try:
                patient_result = wrapper.get_clinical_data(
                    request.study_id, clinical_data_type="PATIENT", size=request.size
                )
                sample_result = wrapper.get_clinical_data(
                    request.study_id, clinical_data_type="SAMPLE", size=request.size
                )
            except RequestException as exc:
                raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc
            patient_data, sample_data = patient_result["results"], sample_result["results"]
        graph, star_annotations = mapping_cbioportal.clinical_data_to_graph(
            patient_data, sample_data, study_id=request.study_id
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Quelle: {request.source!r} (erwartet: 'gdc', 'geo', 'ena', 'cbioportal')",
        )

    turtle = semantic_mapping.serialize_with_provenance(graph, star_annotations)
    response = {"format": "turtle", "triple_count": len(graph), "turtle": turtle, "loaded": False}

    if request.load:
        store = get_graph_store()
        try:
            store.load_turtle(turtle, graph=request.graph)
        except GraphStoreError as exc:
            raise HTTPException(status_code=502, detail=f"graph-db-Import fehlgeschlagen: {exc}") from exc
        response["loaded"] = True
        response["graph"] = request.graph

    return response


@app.get("/ontology")
async def ontology() -> Response:
    """Liefert die aktuelle Basis-Ontologie (TBox) zur Inspektion.

    Quelle: wissensnetz/ontology/databridge-core.ttl (siehe app/semantic/paths.py
    für die Pfad-Auflösung über DATABRIDGE_ONTOLOGY_DIR).
    """
    path = ontology_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Ontologie-Datei nicht gefunden: {path}")
    return Response(content=path.read_text(encoding="utf-8"), media_type="text/turtle")


# ----------------------------------------------------------------------
# UI-gesteuerte Akquise (M1/M2), siehe
# recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf. Nimmt das
# Auswahl-JSON aus dem geplanten Frontend-Panel entgegen und reicht es an
# den Wrapper durch — der Mediator entscheidet hier bewusst NICHT über
# Inhalte (Abschnitt 1a: "Er nimmt das JSON, ruft die Wrapper-Funktion, und
# die Intelligenz liegt im JSON, nicht in ihm").
# ----------------------------------------------------------------------


def _selection_recipe_key(level: SingleSelection, request: SelectionRequest) -> str:
    """Recipe-Key als Auswahl-Identität (M7): dieselbe Auswahl liefert denselben
    Schlüssel unabhängig davon, ob sie über /selection/preview oder
    /selection/generate angefragt wird — Grundlage für Named Graph und
    .h5ad-Dateiname. Nutzt denselben Cache-Mechanismus wie POST /export/anndata
    (wrapper.cache.recipes.key_for). Fachlicher Join-Schlüssel über RDF und
    anndata hinweg bleibt `db:submitterId` (siehe `_build_anndata_from_hits`/
    `cases_to_graph`), dieser recipe_key ist nur die Anfrage-Identität.
    """
    wrapper = get_gdc_wrapper()
    recipe = {
        "source": level.source,
        "cohorts": sorted(level.cohorts),
        "modality": level.modality,
        "attributes": sorted(level.attributes),
        "size": request.size,
        "per_cohort_size": request.per_cohort_size,
    }
    return wrapper.cache.recipes.key_for(recipe)


def _selection_fetch(level: SingleSelection, request: SelectionRequest) -> tuple[list[dict], list[dict], list[str]]:
    """Ruft `fetch_selection_files` (M3) für eine einzelne Auswahl-Ebene auf.

    Nur `source="gdc"` und `modality="gene_expression"` sind heute angebunden
    (siehe Umsetzungsplan M9 bzw. W6 — beide "Später", nicht Teil dieses
    Durchgangs); andere Werte lösen einen `ValueError` aus, den die Aufrufer
    in einen Level-Fehler übersetzen, statt die ganze Anfrage abzubrechen
    (Entscheidung 7.2: Ebenen sind unabhängig voneinander).
    """
    if level.source != "gdc":
        raise ValueError(f"Datenquelle {level.source!r} noch nicht angebunden (siehe Umsetzungsplan M9).")
    if level.modality != "gene_expression":
        raise ValueError(f"Modalität {level.modality!r} noch nicht angebunden (siehe Umsetzungsplan W6).")
    wrapper = get_gdc_wrapper()
    return fetch_selection_files(
        wrapper,
        cohorts=level.cohorts,
        attributes=level.attributes,
        experimental_strategy="RNA-Seq",
        data_type="Gene Expression Quantification",
        size=request.size,
        per_cohort_size=request.per_cohort_size,
    )


def _load_selection_knowledge(turtle: str) -> None:
    """Lädt den Wissensbestand einer Auswahl in den Default-Graph (P1, siehe
    wissensnetz/HANDOFF_pablo_store_waechst.md): der Store ist leer beim
    Start und wächst mit jedem `/selection/*`-Aufruf — läuft bei `preview`
    UND `generate` (beantwortet Entscheidung 7.3: `preview` = Abruf +
    Übersetzung + Laden, ohne Rohdaten/Matrix). `load_turtle` sendet den
    Text roh an Fuseki (kein rdflib-Roundtrip), damit die angehängten
    RDF-star-Blöcke erhalten bleiben (siehe `serialize_with_provenance`,
    ADR-0002, `wissensnetz/CLAUDE.md` "RDF-star-Falle").

    BEWUSSTE, DOKUMENTIERTE SCHULD (P4 im Handoff): reines Anhängen, kein
    `DELETE WHERE` je Fall vor dem Laden. RDF ist eine Menge — identische
    Aussagen (Instanz-IRIs sind deterministisch aus `case_id` gebildet)
    kollabieren von selbst und richten nichts an. Ändert sich aber ein Wert
    für denselben Fall zwischen zwei Aufrufen (z. B. GDC aktualisiert
    `sex_at_birth`), entstehen zwei Werte für dieselbe Property, bis Marcel die
    Ersetzungslogik liefert (siehe Handoff, P4) — absichtlich noch nicht
    selbst nachgebaut, damit es nicht zwei Varianten davon gibt.
    """
    store = get_graph_store()
    try:
        store.load_turtle(turtle)
    except GraphStoreError as exc:
        raise HTTPException(status_code=502, detail=f"Wissensnetz-Import fehlgeschlagen: {exc}") from exc


@app.post("/selection/preview")
async def selection_preview(request: SelectionRequest) -> SelectionPreviewResponse:
    """Billiger Vorschau-Endpunkt (Entscheidung 7.3: geteilter Abruf ohne Matrizen,
    aber MIT Laden — siehe `_load_selection_knowledge`/P1).

    Pro Ebene EIN Files-Query (M3, `fetch_selection_files`), daraus
    `cases_to_graph()` -> Turtle -> (bei `request.load`) in den Store.
    Baut bewusst KEINE anndata-Matrix (siehe `selection_generate` dafür) —
    das ist der Unterschied zwischen billig und teuer. Eine fehlschlagende
    Ebene liefert `status="error"`, ohne die anderen Ebenen der Anfrage zu
    beeinträchtigen.
    """
    alignment = semantic_mapping.load_alignment_table(alignment_path("ncit_primary_diagnosis.json"))
    levels: list[SelectionLevelResult] = []
    for level in request.levels:
        result = SelectionLevelResult(
            selection=level,
            recipe_key=_selection_recipe_key(level, request),
            requested_fields=resolve_case_fields(level.attributes),
        )
        try:
            _hits, cases, failed_cohorts = _selection_fetch(level, request)
            result.failed_cohorts = failed_cohorts
            if not cases:
                raise ValueError(f"Keine Treffer für Kohorte(n) {level.cohorts!r}.")
            graph, star_annotations = semantic_mapping.cases_to_graph(
                cases, alignment=alignment, attributes=level.attributes
            )
            result.turtle = semantic_mapping.serialize_with_provenance(graph, star_annotations)
            result.triple_count = len(graph)
            if request.load:
                _load_selection_knowledge(result.turtle)
        except (ValueError, HTTPException) as exc:
            result.status = "error"
            result.error = exc.detail if isinstance(exc, HTTPException) else str(exc)
        levels.append(result)
    return SelectionPreviewResponse(levels=levels)


@app.post("/selection/generate")
async def selection_generate(request: SelectionRequest) -> SelectionGenerateResponse:
    """Teurer Generieren-Endpunkt: baut zusätzlich zur Turtle-Serialisierung/dem
    Laden (siehe `selection_preview`) ein `.h5ad` je Ebene, auf demselben
    geteilten Proben-Set (M3+M6). Wie bei `selection_preview` beeinträchtigt
    eine fehlschlagende Ebene (z. B. fehlendes `gdc-client` oder
    unerreichbares Fuseki, siehe `_build_anndata_from_hits`) nicht die
    anderen Ebenen der Anfrage.

    P5 (siehe wissensnetz/HANDOFF_pablo_store_waechst.md): eine bereits
    erzeugte Auswahl (identischer `recipe_key`) wird weder erneut
    heruntergeladen noch erneut gebaut — derselbe Cache-Kurzschluss wie in
    `POST /export/anndata`, jetzt auch hier.
    """
    alignment = semantic_mapping.load_alignment_table(alignment_path("ncit_primary_diagnosis.json"))
    wrapper = get_gdc_wrapper()
    levels: list[SelectionLevelResult] = []
    for level in request.levels:
        recipe_key = _selection_recipe_key(level, request)
        result = SelectionLevelResult(
            selection=level,
            recipe_key=recipe_key,
            requested_fields=resolve_case_fields(level.attributes),
        )
        try:
            cached = wrapper.cache.materialized.get(recipe_key)
            if cached and Path(cached.get("path", "")).exists():
                result.anndata = cached
                levels.append(result)
                continue

            hits, cases, failed_cohorts = _selection_fetch(level, request)
            result.failed_cohorts = failed_cohorts
            if not hits:
                raise ValueError(f"Keine Expressions-Files für Kohorte(n) {level.cohorts!r}.")
            graph, star_annotations = semantic_mapping.cases_to_graph(
                cases, alignment=alignment, attributes=level.attributes
            )
            result.turtle = semantic_mapping.serialize_with_provenance(graph, star_annotations)
            result.triple_count = len(graph)
            if request.load:
                _load_selection_knowledge(result.turtle)
            anndata_meta = _build_anndata_from_hits(wrapper, hits, recipe_key, compute_tsne=True)
            wrapper.cache.materialized.set(recipe_key, anndata_meta)
            result.anndata = anndata_meta
        except (ValueError, HTTPException) as exc:
            result.status = "error"
            result.error = exc.detail if isinstance(exc, HTTPException) else str(exc)
        levels.append(result)
    return SelectionGenerateResponse(levels=levels)


def _build_anndata_from_hits(
    wrapper: GDCWrapper,
    hits: list[dict],
    recipe_key: str,
    *,
    id_column: str = "gene_id",
    value_column: str = "tpm_unstranded",
    label_column: Optional[str] = "gene_name",
    gene_ids: Optional[list[str]] = None,
    compute_tsne: bool = False,
    experimental_strategy: str = "RNA-Seq",
    filename: Optional[str] = None,
) -> dict:
    """Baut aus Files-Treffern (siehe `fetch_selection_files`, M3) ein
    anndata/.h5ad (M6, siehe wissensnetz/HANDOFF_anndata.md und
    app/semantic/expression.py): Download über `gdc-client`, X/var aus den
    Quantifizierungsdateien, `obs` aus dem Wissensnetz.

    Gemeinsamer Kern für POST /export/anndata und POST /selection/generate —
    arbeitet auf genau den `hits`, die der Aufrufer per
    `fetch_selection_files()` ermittelt hat (M3: "ein Abruf, zwei
    Serialisierungen"). Bricht mit einem klaren Fehler ab, statt eine
    unvollständige Matrix zurückzugeben, wenn `gdc-client` fehlt oder Fuseki
    nicht erreichbar ist.
    """
    file_ids: list[str] = []
    sample_case_map: dict[str, str] = {}
    sample_types: dict[str, str] = {}
    sample_project_map: dict[str, str] = {}
    file_names: dict[str, str] = {}
    for hit in hits:
        file_id = hit["file_id"]
        case = (hit.get("cases") or [{}])[0]
        sample = (case.get("samples") or [{}])[0]
        sample_id = sample.get("sample_id") or file_id
        file_ids.append(file_id)
        file_names[file_id] = hit["file_name"]
        sample_case_map[sample_id] = case.get("submitter_id")
        _proj = (case.get("project") or {}).get("project_id")
        if _proj:
            sample_project_map[sample_id] = _proj
        if sample.get("sample_type"):
            sample_types[sample_id] = sample["sample_type"]

    manifest_filters = build_filters(extra=[{"op": "in", "content": {"field": "files.file_id", "value": file_ids}}])
    try:
        manifest = wrapper.build_manifest(filters=manifest_filters, size=len(file_ids))
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GDC-API nicht erreichbar oder Fehler: {exc}") from exc

    raw_dir = wrapper.cache.raw.path_for(recipe_key)
    download_result = wrapper.download_via_gdc_client(manifest, str(raw_dir))
    if download_result["status"] != "completed":
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Download der Expressions-Rohdaten fehlgeschlagen oder gdc-client nicht verfügbar "
                "— es wird keine unvollständige/erfundene Matrix zurückgegeben.",
                "download_result": download_result,
            },
        )

    # Zuordnung Datei -> Probe direkt aus den Suchtreffern (dieselbe Regel wie
    # oben beim Aufbau von sample_case_map: sample_id, sonst file_id als Fallback).
    file_id_to_sample_id = {
        hit["file_id"]: ((hit.get("cases") or [{}])[0].get("samples") or [{}])[0].get("sample_id")
        or hit["file_id"]
        for hit in hits
    }

    sample_files: dict[str, Path] = {}
    missing_files: list[str] = []
    for file_id in file_ids:
        candidate = raw_dir / file_id / file_names[file_id]
        sample_id = file_id_to_sample_id[file_id]
        if candidate.exists():
            sample_files[sample_id] = candidate
        else:
            missing_files.append(file_id)

    if not sample_files:
        raise HTTPException(
            status_code=502,
            detail="gdc-client meldete Erfolg, aber keine der erwarteten Dateien wurde gefunden.",
        )

    sample_case_map = {sid: sub for sid, sub in sample_case_map.items() if sid in sample_files}
    sample_types = {sid: t for sid, t in sample_types.items() if sid in sample_files}
    sample_project_map = {sid: p for sid, p in sample_project_map.items() if sid in sample_files}

    try:
        X, sample_ids, gene_ids_out, gene_labels = expression_export.assemble_matrix(
            sample_files,
            id_column=id_column,
            value_column=value_column,
            label_column=label_column,
            gene_ids=gene_ids,
        )
    except expression_export.ExpressionAssemblyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    store = get_graph_store()
    if not store.is_reachable():
        raise HTTPException(
            status_code=503,
            detail=f"Wissensnetz (Fuseki) nicht erreichbar unter {store.settings.base_url} — "
            "obs kann nicht befüllt werden.",
        )
    # Übergangslösung für P3 (siehe wissensnetz/HANDOFF_pablo_store_waechst.md):
    # `all_cases(store)` liefert noch den GESAMTEN Bestand, nicht auf diese
    # Auswahl begrenzt — `wissensnetz.cases_for_selection(store, selection_id)`
    # existiert noch nicht (Marcel liefert sie mit P2). Bis dahin auf die
    # submitter_ids filtern, die wir aus dem geteilten Abruf ohnehin haben
    # (sample_case_map) — gleiches Ergebnis für den Moment (build_obs griff
    # ohnehin nur einzeln über sample_case_map zu), austauschbar gegen
    # cases_for_selection, sobald verfügbar.
    selected_submitters = {sub for sub in sample_case_map.values() if sub}
    cases_by_submitter = {
        c["submitter_id"]: c for c in all_cases(store) if c.get("submitter_id") in selected_submitters
    }

    obs = expression_export.build_obs(
        sample_case_map, cases_by_submitter, sample_types=sample_types, gdc_project_by_sample=sample_project_map
    )
    obs = obs.loc[sample_ids]  # dieselbe Zeilenreihenfolge wie X sicherstellen
    var = expression_export.build_var(gene_ids_out, gene_labels)

    obsm: dict[str, Any] = {}
    if compute_tsne:
        tsne = expression_export.compute_tsne(X)
        if tsne is not None:
            obsm_key = "X_tsne_mirna" if experimental_strategy == "miRNA-Seq" else "X_tsne_genes"
            obsm[obsm_key] = tsne

    adata = expression_export.build_anndata(X, obs, var, obsm=obsm or None)

    out_filename = filename or f"{recipe_key}.h5ad"
    out_filename = Path(out_filename).name  # nur Basisname, keine Pfad-Traversal
    if not out_filename.endswith(".h5ad"):
        out_filename += ".h5ad"
    out_path = expression_export.write_h5ad(adata, export_dir() / out_filename)

    wrapper.cache.raw.purge(recipe_key)

    return {
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "obs_columns": list(obs.columns),
        "var_columns": list(var.columns),
        "obsm_keys": list(obsm.keys()),
        "missing_files": missing_files,
        "filename": out_filename,
        "path": str(out_path),
        "download_url": f"/export/anndata/download/{out_filename}",
    }


@app.post("/export/anndata")
async def export_anndata(request: AnndataExportRequest) -> dict:
    """GDC-Expressionsdateien -> anndata/.h5ad (Teil 3, siehe
    wissensnetz/HANDOFF_anndata.md und app/semantic/expression.py).

    Holt die passenden Expressions-Files über den gemeinsamen Abrufschritt
    (M3, `fetch_selection_files`) und baut daraus über `_build_anndata_from_hits`
    (M6) das `.h5ad` — derselbe Kern, den auch POST /selection/generate nutzt.
    Siehe GET /export/anndata/download/{filename} für den eigentlichen
    Datei-Download.
    """
    wrapper = get_gdc_wrapper()

    recipe = {
        "project_id": request.project_id,
        "experimental_strategy": request.experimental_strategy,
        "data_type": request.data_type,
        "id_column": request.id_column,
        "value_column": request.value_column,
        "label_column": request.label_column,
        "size": request.size,
        "per_project_size": request.per_project_size,
        "gene_ids": request.gene_ids,
        "compute_tsne": request.compute_tsne,
    }
    recipe_key = wrapper.cache.recipes.key_for(recipe)
    cached = wrapper.cache.materialized.get(recipe_key)
    if cached and Path(cached["path"]).exists():
        return cached

    # Files PRO Projekt holen statt in einem Sammel-Query (Stratifizierung,
    # siehe wissensnetz/HANDOFF_export_stratified.md) — "sample_type" ist das
    # einzige Attribut, das dieser Endpunkt traditionell anfordert (obs-Spalte
    # "sample_type"); zusätzliche Klinikfelder kommen künftig über
    # POST /selection/generate (M6), das beliebige `attributes[]` je Ebene kennt.
    projects = request.project_id if isinstance(request.project_id, list) else [request.project_id]
    hits, _shared_cases, failed_projects = fetch_selection_files(
        wrapper,
        cohorts=projects,
        attributes=["sample_type"],
        experimental_strategy=request.experimental_strategy,
        data_type=request.data_type,
        size=request.size,
        per_cohort_size=request.per_project_size,
    )

    if not hits:
        raise HTTPException(
            status_code=404,
            detail=f"Keine Expressions-Files gefunden für project_id={request.project_id!r} "
            f"(fehlgeschlagene Kohorten: {failed_projects!r}), "
            f"experimental_strategy={request.experimental_strategy!r}, data_type={request.data_type!r}.",
        )

    result = _build_anndata_from_hits(
        wrapper,
        hits,
        recipe_key,
        id_column=request.id_column,
        value_column=request.value_column,
        label_column=request.label_column,
        gene_ids=request.gene_ids,
        compute_tsne=request.compute_tsne,
        experimental_strategy=request.experimental_strategy,
        filename=request.filename,
    )

    metadata = {
        "project_id": request.project_id,
        "experimental_strategy": request.experimental_strategy,
        "failed_projects": failed_projects,
        **result,
    }
    wrapper.cache.materialized.set(recipe_key, metadata)
    return metadata


@app.get("/export/anndata/download/{filename}")
async def export_anndata_download(filename: str) -> FileResponse:
    """Lädt eine zuvor über POST /export/anndata erzeugte `.h5ad`-Datei herunter."""
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")
    path = export_dir() / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Export nicht gefunden: {safe_name!r}")
    return FileResponse(path, media_type="application/octet-stream", filename=safe_name)
