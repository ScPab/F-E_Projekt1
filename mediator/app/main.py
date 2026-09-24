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

English: DataBridge Mediator – FastAPI skeleton.

The mediator is the central entry point of the mediator-wrapper architecture:
it accepts requests and delegates them to the matching wrapper modules
(wrappers/gdc, wrappers/geo, wrappers/ena, wrappers/cbioportal, installed as a
Python package in the same container, see
docs/adr/0001-wrapper-als-python-package.md) for the actual data acquisition.

The endpoints exposed here (/query, /schema/{endpoint}, /manifest) form the
interface through which later callers (frontend, other services) access the
GDC wrapper — without the GDC wrapper having to be its own network service.

The semantic transformation (GDC JSON -> RDF/OWL) for the
case/project/demographic/diagnosis/samples slice is wired up via POST
/transform (see app/semantic/mapping.py). The transformation into
anndata/.h5ad (expression matrices, part 3 of wissensnetz/HANDOFF_anndata.md)
is wired up via POST /export/anndata (see app/semantic/expression.py).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
from cbioportal import CBioPortalWrapper
from ena import ENAWrapper
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from gdc import GDCWrapper, build_filters
from geo import GEOWrapper, build_search_term as geo_build_search_term
from rdflib import Graph
from requests import RequestException
from wissensnetz import GraphStore, GraphStoreError, all_cases
from wissensnetz.cohorts import cancer_code

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
from .semantic import cancer_types
from .semantic import expression as expression_export
from .semantic import mapping as semantic_mapping
from .semantic import mapping_cbioportal, mapping_ena, mapping_geo
from .semantic.paths import alignment_path, export_dir, ontology_path

# Felder, die für JEDE Case-Abfrage strukturell nötig sind (Identität/
# Join-Schlüssel bzw. Instanz-IRI-Bildung, siehe cases_to_graph) — unabhängig
# davon, welche Attribute die UI zusätzlich anfordert.
# EN: Fields structurally required for EVERY case query (identity/join key
# or instance-IRI formation, see cases_to_graph) — regardless of which
# attributes the UI additionally requests.
BASE_CASE_FIELDS = ["case_id", "submitter_id", "project.project_id", "samples.sample_id"]


def resolve_case_fields(attributes: list[str]) -> list[str]:
    """Leitet die bei GDC anzufragenden Felder aus UI-Attributen ab (M4, siehe
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, Abschnitt 3: "TRANSFORM_CASE_FIELDS
    von Konstante zu abgeleitet ... Kern der Trigger-Idee").

    `BASE_CASE_FIELDS` sind immer dabei; für jedes Attribut kommt das über
    `semantic_mapping.resolve_attribute` aufgelöste GDC-Feld hinzu — bekannte
    Oviedo-Attributnamen (KNOWN_ATTRIBUTES) ebenso wie neue, deren Property
    laut Entscheidung 7.5 dynamisch entsteht.

    English: Derives the GDC fields to request from UI attributes (M4, see
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, section 3:
    "TRANSFORM_CASE_FIELDS from constant to derived ... core of the trigger
    idea"). `BASE_CASE_FIELDS` are always included; for every attribute the
    GDC field resolved via `semantic_mapping.resolve_attribute` is added —
    known Oviedo attribute names (KNOWN_ATTRIBUTES) as well as new ones whose
    property is created dynamically per decision 7.5.
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
# EN: Backwards-compatible default for POST /transform (unchanged behavior:
# the same field scope as the former fixed constant — DEFAULT_ATTRIBUTES
# covers exactly the same 11 attributes, see app/semantic/mapping.py).
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

    English: The shared fetch step (M3, see
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf, section 1b/3): ONE
    files query per cohort delivers both the file/sample mapping (basis for
    anndata, see `_build_anndata_from_hits`) AND the embedded case objects
    (basis for `cases_to_graph`) at the same time — for `cases.<field>`
    fields, GDC returns the same nested case structure as the standalone
    `/cases` endpoint directly alongside the file hits (verified live).
    Replaces the two previously independent fetches (`/transform`'s own
    `search("cases", ...)` and `/export/anndata`'s `query("files", ...)` with
    a smaller field list, see module docstring section 1b of the plan) with a
    single fetch, stratified per cohort (see
    wissensnetz/HANDOFF_export_stratified.md).

    Returns `(hits, cases, failed_cohorts)`: `hits` raw (file hits, for the
    file/sample mapping and the manifest), `cases` deduplicated by
    `case_id`/`submitter_id` (directly `cases_to_graph`-compatible, no
    reshaping needed — same nested form as GDC's `/cases`), `failed_cohorts`
    for cohorts whose query failed (does not kill the whole fetch, see
    wissensnetz/HANDOFF_export_stratified.md).
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
            # EN: an empty/broken cohort should not kill the whole fetch
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
# EN: Single, reused wrapper instance (holds, among other things, the
# requests.Session and the cache access point, see wrappers/gdc/cache.py).
_gdc_wrapper: GDCWrapper | None = None

# Analog wiederverwendete Instanzen für die weiteren Wrapper (siehe
# wrappers/geo, wrappers/ena, wrappers/cbioportal).
# EN: Analogously reused instances for the other wrappers (see wrappers/geo,
# wrappers/ena, wrappers/cbioportal).
_geo_wrapper: GEOWrapper | None = None
_ena_wrapper: ENAWrapper | None = None
_cbioportal_wrapper: CBioPortalWrapper | None = None

# Einzelne, wiederverwendete GraphStore-Instanz (Fuseki-Anbindung für
# POST /transform mit load=true). Verbindung wird aus ENV gelesen
# (GRAPH_DB_URL/GRAPH_DB_DATASET/..., siehe wissensnetz/src/wissensnetz/config.py
# und docker-compose.yml für den Compose-internen Wert).
# EN: Single, reused GraphStore instance (Fuseki connection for POST
# /transform with load=true). Connection is read from ENV
# (GRAPH_DB_URL/GRAPH_DB_DATASET/..., see
# wissensnetz/src/wissensnetz/config.py and docker-compose.yml for the
# compose-internal value).
_graph_store: GraphStore | None = None


def get_gdc_wrapper() -> GDCWrapper:
    """Liefert eine lazily initialisierte, geteilte GDCWrapper-Instanz.

    English: Returns a lazily initialized, shared GDCWrapper instance.
    """
    global _gdc_wrapper
    if _gdc_wrapper is None:
        base_url = os.environ.get("GDC_API_BASE_URL", "https://api.gdc.cancer.gov")
        _gdc_wrapper = GDCWrapper(base_url)
    return _gdc_wrapper


def get_geo_wrapper() -> GEOWrapper:
    """Liefert eine lazily initialisierte, geteilte GEOWrapper-Instanz.

    English: Returns a lazily initialized, shared GEOWrapper instance.
    """
    global _geo_wrapper
    if _geo_wrapper is None:
        base_url = os.environ.get("GEO_API_BASE_URL", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
        _geo_wrapper = GEOWrapper(base_url)
    return _geo_wrapper


def get_ena_wrapper() -> ENAWrapper:
    """Liefert eine lazily initialisierte, geteilte ENAWrapper-Instanz.

    English: Returns a lazily initialized, shared ENAWrapper instance.
    """
    global _ena_wrapper
    if _ena_wrapper is None:
        base_url = os.environ.get("ENA_API_BASE_URL", "https://www.ebi.ac.uk/ena/portal/api")
        _ena_wrapper = ENAWrapper(base_url)
    return _ena_wrapper


def get_cbioportal_wrapper() -> CBioPortalWrapper:
    """Liefert eine lazily initialisierte, geteilte CBioPortalWrapper-Instanz.

    English: Returns a lazily initialized, shared CBioPortalWrapper instance.
    """
    global _cbioportal_wrapper
    if _cbioportal_wrapper is None:
        base_url = os.environ.get("CBIOPORTAL_API_BASE_URL", "https://www.cbioportal.org/api")
        _cbioportal_wrapper = CBioPortalWrapper(base_url)
    return _cbioportal_wrapper


def get_graph_store() -> GraphStore:
    """Liefert eine lazily initialisierte, geteilte GraphStore-Instanz.

    English: Returns a lazily initialized, shared GraphStore instance.
    """
    global _graph_store
    if _graph_store is None:
        _graph_store = GraphStore()
    return _graph_store


@app.get("/health")
async def health() -> dict[str, str]:
    """Einfacher Health-Check, damit Orchestrierung (z. B. Docker Compose) den Service prüfen kann.

    English: Simple health check so orchestration (e.g. Docker Compose) can probe the service.
    """
    return {"status": "ok"}


@app.post("/query")
async def query(request: QueryRequest) -> dict:
    """Metadaten-Suche gegen GDC (Testfall: TCGA-BRCA / RNA-Seq / open).

    Delegiert an GDCWrapper.search — vereinfachte Suchparameter werden dort
    in einen validen GDC-`filters`-Query übersetzt.

    English: Metadata search against GDC (test case: TCGA-BRCA / RNA-Seq /
    open). Delegates to GDCWrapper.search — simplified search parameters are
    translated there into a valid GDC `filters` query.
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

    English: Available fields of a GDC endpoint (cases/files/projects/annotations).
    Preparation for the later ontology/mapping layer, see wrappers/gdc/client.py
    (module docstring, `get_schema`).
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
    """Manifest (Bulk-Tier) für eine Files-Query erzeugen, zur Übergabe an gdc-client.

    English: Generate a manifest (bulk tier) for a files query, to pass to gdc-client.
    """
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
# EN: GEO (Gene Expression Omnibus), see wrappers/geo/client.py
# ----------------------------------------------------------------------


@app.post("/geo/query")
async def geo_query(request: GeoQueryRequest) -> dict:
    """Metadaten-Suche gegen GEO (esearch+esummary), analog zu POST /query.

    English: Metadata search against GEO (esearch+esummary), analogous to POST /query.
    """
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
    """Verfügbare Such-Feld-Tags einer GEO/Entrez-Datenbank (einfo), analog zu GET /schema/{endpoint}.

    English: Available search field tags of a GEO/Entrez database (einfo), analogous to GET /schema/{endpoint}.
    """
    wrapper = get_geo_wrapper()
    try:
        fields = wrapper.get_schema(db)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GEO-API nicht erreichbar oder Fehler: {exc}") from exc
    return {"db": db, "fields": fields}


@app.get("/geo/ftp-link/{accession}")
async def geo_ftp_link(accession: str) -> dict:
    """FTP-Verzeichnislink einer GEO-Accession (Bulk-Tier-Äquivalent zu POST /manifest).

    English: FTP directory link of a GEO accession (bulk-tier equivalent to POST /manifest).
    """
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
# EN: ENA (European Nucleotide Archive), see wrappers/ena/client.py
# ----------------------------------------------------------------------


@app.post("/ena/query")
async def ena_query(request: EnaQueryRequest) -> dict:
    """Metadaten-Suche gegen ENA (/search), analog zu POST /query.

    English: Metadata search against ENA (/search), analogous to POST /query.
    """
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
    """Verfügbare Feldnamen eines ENA-Ergebnistyps (/returnFields), analog zu GET /schema/{endpoint}.

    English: Available field names of an ENA result type (/returnFields), analogous to GET /schema/{endpoint}.
    """
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
    """FASTQ-Download-URLs eines Read-Runs (Bulk-Tier-Äquivalent zu POST /manifest).

    English: FASTQ download URLs of a read run (bulk-tier equivalent to POST /manifest).
    """
    wrapper = get_ena_wrapper()
    try:
        return wrapper.get_download_links(run_accession)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ENA-API nicht erreichbar oder Fehler: {exc}") from exc


# ----------------------------------------------------------------------
# cBioPortal, siehe wrappers/cbioportal/client.py
# EN: cBioPortal, see wrappers/cbioportal/client.py
# ----------------------------------------------------------------------


@app.get("/cbioportal/studies")
async def cbioportal_studies(
    keyword: str | None = None,
    size: int = 20,
    from_: int = Query(0, alias="from"),
) -> dict:
    """Studien-Suche gegen cBioPortal (/studies), analog zu POST /query.

    English: Study search against cBioPortal (/studies), analogous to POST /query.
    """
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.list_studies(keyword=keyword, size=size, from_=from_)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/cbioportal/schema/{study_id}")
async def cbioportal_schema(study_id: str) -> dict:
    """Klinische Attribut-IDs einer Studie, analog zu GET /schema/{endpoint}.

    English: Clinical attribute IDs of a study, analogous to GET /schema/{endpoint}.
    """
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
    """Klinische Datenpunkte (Attribut/Wert je Patient oder Sample) einer Studie.

    English: Clinical data points (attribute/value per patient or sample) of a study.
    """
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
    """Verfügbare molekulare Profile einer Studie (Vorbereitung für /cbioportal/molecular-data).

    English: Available molecular profiles of a study (preparation for /cbioportal/molecular-data).
    """
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.list_molecular_profiles(study_id)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.get("/cbioportal/sample-lists/{study_id}")
async def cbioportal_sample_lists(study_id: str) -> list[dict]:
    """Vordefinierte Sample-Listen einer Studie (Vorbereitung für /cbioportal/molecular-data).

    English: Predefined sample lists of a study (preparation for /cbioportal/molecular-data).
    """
    wrapper = get_cbioportal_wrapper()
    try:
        return wrapper.list_sample_lists(study_id)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"cBioPortal-API nicht erreichbar oder Fehler: {exc}") from exc


@app.post("/cbioportal/molecular-data/{molecular_profile_id}")
async def cbioportal_molecular_data(
    molecular_profile_id: str, request: CBioMolecularDataRequest
) -> dict:
    """Genomische Profildaten für eine Gen-/Sample-Auswahl (Bulk-Tier-Äquivalent zu POST /manifest).

    English: Genomic profile data for a gene/sample selection (bulk-tier equivalent to POST /manifest).
    """
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

    English: Source JSON -> RDF/OWL triples (Turtle), via a dedicated mapping
    module per `source`.

    - `gdc`: GDC cases -> RDF/OWL, per
      wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL (`app/semantic/mapping.py`)
      — including NCIt alignment with RDF-star provenance.
    - `geo`: GEO series -> RDF/OWL (`app/semantic/mapping_geo.py`).
    - `ena`: ENA runs -> RDF/OWL (`app/semantic/mapping_ena.py`).
    - `cbioportal`: cBioPortal clinical data of a study -> RDF/OWL
      (`app/semantic/mapping_cbioportal.py`), requires `study_id`.

    Accepts either raw hits per source, or fetches them live via the
    matching wrapper (see the TransformRequest field descriptions). Output is
    always the generated Turtle text; with `load=true` it is additionally
    written directly via Graph Store Protocol into graph-db (Fuseki) (see
    `wissensnetz.GraphStore.load_turtle`, ADR-0002) — the Turtle output stays
    raw so that, for `gdc`, the appended RDF-star blocks (provenance/
    confidence) are not lost through an rdflib round-trip.
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

    English: Returns the current base ontology (TBox) for inspection.
    Source: wissensnetz/ontology/databridge-core.ttl (see app/semantic/paths.py
    for path resolution via DATABRIDGE_ONTOLOGY_DIR).
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
#
# EN: UI-driven acquisition (M1/M2), see
# recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf. Accepts the selection
# JSON from the planned frontend panel and passes it through to the wrapper
# — the mediator deliberately does NOT decide on content here (section 1a:
# "It takes the JSON, calls the wrapper function, and the intelligence lives
# in the JSON, not in it").
# ----------------------------------------------------------------------


def _selection_recipe_key(level: SingleSelection, request: SelectionRequest) -> str:
    """Recipe-Key als Auswahl-Identität (M7): dieselbe Auswahl liefert denselben
    Schlüssel unabhängig davon, ob sie über /selection/preview oder
    /selection/generate angefragt wird — Grundlage für Named Graph und
    .h5ad-Dateiname. Nutzt denselben Cache-Mechanismus wie POST /export/anndata
    (wrapper.cache.recipes.key_for). Fachlicher Join-Schlüssel über RDF und
    anndata hinweg bleibt `db:submitterId` (siehe `_build_anndata_from_hits`/
    `cases_to_graph`), dieser recipe_key ist nur die Anfrage-Identität.

    English: Recipe key as selection identity (M7): the same selection yields
    the same key regardless of whether it is requested via
    /selection/preview or /selection/generate — basis for the named graph and
    the .h5ad filename. Uses the same cache mechanism as POST /export/anndata
    (wrapper.cache.recipes.key_for). The domain join key across RDF and
    anndata remains `db:submitterId` (see `_build_anndata_from_hits`/
    `cases_to_graph`); this recipe_key is only the request identity.
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


@dataclass
class SelectionFetchResult:
    """Ergebnis des quellen-abhängigen Abrufs+Übersetzung einer Auswahl-Ebene
    (Back-Mediator, M9, siehe recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf) —
    gemeinsame Form für beide Endpunkte: `graph`/`star_annotations` (RDF,
    immer gebraucht) und ein lazy `build_anndata`-Callback, das NUR
    `/selection/generate` aufruft, damit `/selection/preview` keine teuren
    Downloads/Matrixaufbauten auslöst (Entscheidung 7.3).

    English: Result of the source-dependent fetch+translation of a selection
    level (back-mediator, M9, see
    recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf) — shared shape for
    both endpoints: `graph`/`star_annotations` (RDF, always needed) and a
    lazy `build_anndata` callback that ONLY `/selection/generate` calls, so
    that `/selection/preview` does not trigger expensive downloads/matrix
    builds (decision 7.3).
    """

    graph: Graph
    build_anndata: Callable[[], dict]
    star_annotations: list = field(default_factory=list)
    failed_cohorts: list[str] = field(default_factory=list)


def _fetch_selection_level(
    level: SingleSelection, request: SelectionRequest, recipe_key: str, alignment: dict[str, str]
) -> SelectionFetchResult:
    """Back-Mediator-Dispatcher (M9): übersetzt eine generische Auswahl-Ebene
    (Kohorte/Modalität/Attribute/Datenquelle aus dem UI-Panel) in die jeweils
    native Anfrageform der gewählten Datenquelle.

    `gdc` und `cbioportal` sind für preview UND generate angebunden, `geo`
    nur für preview real (generate best-effort, siehe
    `_build_anndata_from_geo_best_effort`) — beide Endpunkte behandeln eine
    fehlschlagende Ebene unabhängig von den anderen (Entscheidung 7.2).

    English: Back-mediator dispatcher (M9): translates a generic selection
    level (cohort/modality/attributes/source from the UI panel) into the
    respective native request form of the chosen data source.

    `gdc` and `cbioportal` are wired up for both preview AND generate, `geo`
    only genuinely for preview (generate is best-effort, see
    `_build_anndata_from_geo_best_effort`) — both endpoints handle a failing
    level independently of the others (decision 7.2).
    """
    if level.modality != "gene_expression":
        raise ValueError(f"Modalität {level.modality!r} noch nicht angebunden (siehe Umsetzungsplan W6).")

    if level.source == "gdc":
        return _fetch_gdc_level(level, request, recipe_key, alignment)
    if level.source == "cbioportal":
        return _fetch_cbioportal_level(level, request, recipe_key)
    if level.source == "geo":
        return _fetch_geo_level(level, request, recipe_key)
    if level.source == "ena":
        raise ValueError(
            "Datenquelle 'ena' ist im Back-Mediator (M9) bewusst nicht angebunden: ENA organisiert Daten "
            "nicht nach Krankheits-/Krebsart (allgemeines Rohsequenz-Archiv, kein kuratierter Krebs-"
            "Datenbestand), und der Wrapper hat keine Freitextsuche — eine Kohorten-Anfrage wäre hier "
            "nicht sinnvoll beantwortbar, nicht nur technisch offen."
        )
    raise ValueError(f"Unbekannte Datenquelle {level.source!r}.")


def _fetch_gdc_level(
    level: SingleSelection, request: SelectionRequest, recipe_key: str, alignment: dict[str, str]
) -> SelectionFetchResult:
    """GDC-Zweig des Back-Mediators — unverändert die bisherige Logik (M3/M4),
    nur um das gemeinsame `SelectionFetchResult` herum verpackt.

    English: GDC branch of the back-mediator — the previous logic (M3/M4)
    unchanged, just wrapped in the shared `SelectionFetchResult`.
    """
    wrapper = get_gdc_wrapper()
    hits, cases, failed_cohorts = fetch_selection_files(
        wrapper,
        cohorts=level.cohorts,
        attributes=level.attributes,
        experimental_strategy="RNA-Seq",
        data_type="Gene Expression Quantification",
        size=request.size,
        per_cohort_size=request.per_cohort_size,
    )
    if not cases:
        raise ValueError(f"Keine Treffer für Kohorte(n) {level.cohorts!r}.")
    graph, star_annotations = semantic_mapping.cases_to_graph(cases, alignment=alignment, attributes=level.attributes)

    def build_anndata() -> dict:
        if not hits:
            raise ValueError(f"Keine Expressions-Files für Kohorte(n) {level.cohorts!r}.")
        return _build_anndata_from_hits(wrapper, hits, recipe_key, compute_tsne=True)

    return SelectionFetchResult(
        graph=graph, star_annotations=star_annotations, failed_cohorts=failed_cohorts, build_anndata=build_anndata
    )


def _resolve_cbioportal_study(wrapper: CBioPortalWrapper, cohort: str) -> Optional[str]:
    """Back-Mediator-Kern für cBioPortal: Krebsart -> passende Studie.

    `list_studies(keyword=...)` sucht per Stichwort (siehe
    `cancer_types.cancer_name`); die Treffer-Reihenfolge von cBioPortal ist
    keine Qualitäts-/Vollständigkeitsordnung (live beobachtet z. B. für
    "brca": eine kleine HTAN-Teilstudie vor der etablierten TCGA-
    PanCancer-Atlas-Referenzstudie) — deshalb eine gestufte Präferenz statt
    des ersten Treffers: zuerst eine Studie, deren `studyId` den
    Kohorten-Code UND "tcga_pan_can_atlas" enthält (breites, gepflegtes
    mRNA-Profil), sonst Code+"tcga", sonst nur der Code, sonst der erste
    Treffer der Stichwortsuche. `None`, wenn keine Studie gefunden wurde oder
    die Anfrage fehlschlägt.

    English: Back-mediator core for cBioPortal: cancer type -> matching study.

    `list_studies(keyword=...)` searches by keyword (see
    `cancer_types.cancer_name`); cBioPortal's hit order is not a quality/
    completeness ordering (observed live e.g. for "brca": a small HTAN
    sub-study ranked before the established TCGA PanCancer Atlas reference
    study) — hence a tiered preference instead of the first hit: first a
    study whose `studyId` contains both the cohort code AND
    "tcga_pan_can_atlas" (broad, curated mRNA profile), else code+"tcga",
    else just the code, else the first hit of the keyword search. `None` if
    no study was found or the request fails.
    """
    keyword = cancer_types.cancer_name(cohort)
    code = (cancer_code(cohort) or cohort).lower()
    try:
        result = wrapper.list_studies(keyword=keyword, size=50)
    except RequestException:
        return None
    studies = result.get("results") or []
    if not studies:
        return None

    def _find(predicate: Callable[[str], bool]) -> Optional[dict]:
        return next((s for s in studies if predicate((s.get("studyId") or "").lower())), None)

    study = (
        _find(lambda sid: code in sid and "tcga_pan_can_atlas" in sid)
        or _find(lambda sid: code in sid and "tcga" in sid)
        or _find(lambda sid: code in sid)
        or studies[0]
    )
    return study.get("studyId")


def _pick_cbioportal_profile(wrapper: CBioPortalWrapper, study_id: str) -> Optional[str]:
    """Wählt ein mRNA-Expressionsprofil einer Studie (Heuristik: `molecularProfileId`
    enthält "mrna" oder `molecularAlterationType` ist "MRNA_EXPRESSION") — für
    `get_molecular_data()`, das `_build_anndata_from_cbioportal` braucht.

    English: Picks an mRNA expression profile of a study (heuristic:
    `molecularProfileId` contains "mrna" or `molecularAlterationType` is
    "MRNA_EXPRESSION") — for `get_molecular_data()`, needed by
    `_build_anndata_from_cbioportal`.
    """
    try:
        profiles = wrapper.list_molecular_profiles(study_id)
    except RequestException:
        return None
    candidates = [
        p
        for p in profiles
        if "mrna" in (p.get("molecularProfileId") or "").lower()
        or (p.get("molecularAlterationType") or "").upper() == "MRNA_EXPRESSION"
    ]
    return candidates[0].get("molecularProfileId") if candidates else None


def _pick_cbioportal_sample_list(wrapper: CBioPortalWrapper, study_id: str) -> Optional[str]:
    """Wählt eine Sample-Liste einer Studie (bevorzugt eine, deren ID auf
    "_all" endet, sonst die größte) — für `get_molecular_data()`.

    English: Picks a sample list of a study (prefers one whose ID ends in
    "_all", otherwise the largest) — for `get_molecular_data()`.
    """
    try:
        sample_lists = wrapper.list_sample_lists(study_id)
    except RequestException:
        return None
    if not sample_lists:
        return None
    preferred = next((sl for sl in sample_lists if (sl.get("sampleListId") or "").endswith("_all")), None)
    if preferred:
        return preferred.get("sampleListId")
    largest = max(sample_lists, key=lambda sl: len(sl.get("sampleIds") or []))
    return largest.get("sampleListId")


def _fetch_cbioportal_level(level: SingleSelection, request: SelectionRequest, recipe_key: str) -> SelectionFetchResult:
    """cBioPortal-Zweig des Back-Mediators (M9): jede Kohorte wird über
    `_resolve_cbioportal_study` auf eine Studie abgebildet, deren
    Klinikdaten real geholt und via `mapping_cbioportal.clinical_data_to_graph`
    (unverändert wiederverwendet) übersetzt werden. Mehrere `level.cohorts`
    ergeben mehrere Studien, deren Graphen vereinigt werden (analog zu GDCs
    Multi-Kohorten-Support).

    English: cBioPortal branch of the back-mediator (M9): each cohort is
    mapped to a study via `_resolve_cbioportal_study`, whose clinical data is
    genuinely fetched and translated via
    `mapping_cbioportal.clinical_data_to_graph` (reused unchanged). Multiple
    `level.cohorts` yield multiple studies whose graphs are unioned (analogous
    to GDC's multi-cohort support).
    """
    wrapper = get_cbioportal_wrapper()
    n_each = request.per_cohort_size or request.size
    combined = Graph()
    combined.bind("db", semantic_mapping.DB)
    failed_cohorts: list[str] = []
    resolved: list[tuple[str, list[str]]] = []  # (study_id, sample_ids)
    # EN: (study_id, sample_ids)

    for cohort in level.cohorts:
        study_id = _resolve_cbioportal_study(wrapper, cohort)
        if not study_id:
            failed_cohorts.append(cohort)
            continue
        try:
            patient_rows = wrapper.get_clinical_data(study_id, clinical_data_type="PATIENT", size=2000)["results"]
            sample_rows = wrapper.get_clinical_data(study_id, clinical_data_type="SAMPLE", size=2000)["results"]
        except RequestException:
            failed_cohorts.append(cohort)
            continue
        graph, _stars = mapping_cbioportal.clinical_data_to_graph(patient_rows, sample_rows, study_id=study_id)
        combined += graph
        sample_ids = sorted({row.get("sampleId") for row in sample_rows if row.get("sampleId")})[:n_each]
        if sample_ids:
            resolved.append((study_id, sample_ids))

    def build_anndata() -> dict:
        if not resolved:
            raise ValueError(f"Keine cBioPortal-Studie mit Proben gefunden für Kohorte(n) {level.cohorts!r}.")
        return _build_anndata_from_cbioportal(wrapper, resolved, recipe_key, compute_tsne=True)

    return SelectionFetchResult(graph=combined, failed_cohorts=failed_cohorts, build_anndata=build_anndata)


def _build_anndata_from_cbioportal(
    wrapper: CBioPortalWrapper,
    resolved: list[tuple[str, list[str]]],
    recipe_key: str,
    *,
    compute_tsne: bool = False,
) -> dict:
    """Baut ein `.h5ad` aus cBioPortals `get_molecular_data()` (Back-Mediator M9).

    Anders als GDC liefert cBioPortal bereits fertige, tabellarische Werte
    (kein Rohdaten-Download/gdc-client nötig) — `get_molecular_data()`
    verlangt aber eine explizite `entrezGeneIds`-Liste, dafür das kleine,
    live verifizierte `cancer_types.DEMO_GENE_PANEL` (siehe dort). Je
    resolvierter Studie wird ein mRNA-Profil + eine Sample-Liste gewählt
    (siehe `_pick_cbioportal_profile`/`_pick_cbioportal_sample_list`); fehlt
    eines davon, wird nur diese Studie übersprungen, nicht die ganze Ebene.

    English: Builds a `.h5ad` from cBioPortal's `get_molecular_data()`
    (back-mediator M9).

    Unlike GDC, cBioPortal already delivers finished, tabular values (no raw
    download/gdc-client needed) — `get_molecular_data()` does, however,
    require an explicit `entrezGeneIds` list, for which the small,
    live-verified `cancer_types.DEMO_GENE_PANEL` is used (see there). For
    each resolved study, an mRNA profile + a sample list is chosen (see
    `_pick_cbioportal_profile`/`_pick_cbioportal_sample_list`); if either is
    missing, only that study is skipped, not the whole level.
    """
    gene_ids_str = [str(g) for g in cancer_types.DEMO_GENE_PANEL.values()]
    gene_labels = {str(entrez_id): symbol for symbol, entrez_id in cancer_types.DEMO_GENE_PANEL.items()}
    entrez_ids = list(cancer_types.DEMO_GENE_PANEL.values())

    values: dict[str, dict[str, float]] = {}
    for study_id, sample_ids in resolved:
        profile_id = _pick_cbioportal_profile(wrapper, study_id)
        sample_list_id = _pick_cbioportal_sample_list(wrapper, study_id)
        if not profile_id or not sample_list_id:
            continue
        try:
            result = wrapper.get_molecular_data(profile_id, sample_list_id=sample_list_id, entrez_gene_ids=entrez_ids)
        except RequestException:
            continue
        wanted = set(sample_ids)
        for row in result.get("results") or []:
            sample_id = row.get("sampleId")
            entrez_id = row.get("entrezGeneId")
            value = row.get("value")
            if sample_id not in wanted or entrez_id is None or value is None:
                continue
            try:
                values.setdefault(sample_id, {})[str(int(entrez_id))] = float(value)
            except (TypeError, ValueError):
                continue

    if not values:
        raise HTTPException(
            status_code=502,
            detail="cBioPortal lieferte keine molekularen Werte für das Demo-Genpanel "
            "(fehlendes mRNA-Profil, leere Sample-Liste oder unbekanntes Panel für diese Studie(n)).",
        )

    X, sample_ids_out = expression_export.assemble_matrix_from_values(values, gene_ids_str)
    obs = pd.DataFrame(index=pd.Index(sample_ids_out, name="sample_id"))
    var = expression_export.build_var(gene_ids_str, gene_labels)

    obsm: dict[str, Any] = {}
    if compute_tsne:
        tsne = expression_export.compute_tsne(X)
        if tsne is not None:
            obsm["X_tsne_genes"] = tsne

    adata = expression_export.build_anndata(X, obs, var, obsm=obsm or None)
    filename = f"{recipe_key}.h5ad"
    out_path = expression_export.write_h5ad(adata, export_dir() / filename)

    return {
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "obs_columns": list(obs.columns),
        "var_columns": list(var.columns),
        "obsm_keys": list(obsm.keys()),
        "missing_files": [],
        "filename": filename,
        "path": str(out_path),
        "download_url": f"/export/anndata/download/{filename}",
    }


def _fetch_geo_level(level: SingleSelection, request: SelectionRequest, recipe_key: str) -> SelectionFetchResult:
    """GEO-Zweig des Back-Mediators (M9): jede Kohorte wird über
    `cancer_types.cancer_name` auf einen Freitext-Suchbegriff abgebildet und
    per `GEOWrapper.query()` (nicht `.search()`, das kein `extra` durchreicht,
    siehe cancer_types.py-Modul-Docstring) gegen `gds` gesucht. Preview ist
    real (`mapping_geo.series_to_graph`); Generate ist Best-Effort, siehe
    `_build_anndata_from_geo_best_effort`.

    English: GEO branch of the back-mediator (M9): each cohort is mapped to a
    free-text search term via `cancer_types.cancer_name` and searched against
    `gds` via `GEOWrapper.query()` (not `.search()`, which does not pass
    through `extra`, see the cancer_types.py module docstring). Preview is
    genuine (`mapping_geo.series_to_graph`); generate is best-effort, see
    `_build_anndata_from_geo_best_effort`.
    """
    wrapper = get_geo_wrapper()
    n_each = request.per_cohort_size or request.size
    combined = Graph()
    combined.bind("db", semantic_mapping.DB)
    failed_cohorts: list[str] = []
    all_series: list[dict] = []

    for cohort in level.cohorts:
        term = geo_build_search_term(
            organism="Homo sapiens", entry_type="gse", extra=[f'"{cancer_types.cancer_name(cohort)}"']
        )
        try:
            result = wrapper.query(term=term, db="gds", size=n_each)
        except RequestException:
            failed_cohorts.append(cohort)
            continue
        hits = result.get("results") or []
        if not hits:
            failed_cohorts.append(cohort)
            continue
        all_series.extend(hits)

    if all_series:
        graph, _stars = mapping_geo.series_to_graph(all_series)
        combined += graph

    def build_anndata() -> dict:
        return _build_anndata_from_geo_best_effort(wrapper, all_series, recipe_key, compute_tsne=True)

    return SelectionFetchResult(graph=combined, failed_cohorts=failed_cohorts, build_anndata=build_anndata)


# Dateiendungen, die der Best-Effort-GEO-Parser als tabellenartig versucht
# (siehe `_build_anndata_from_geo_best_effort`) — bewusst eng gefasst, damit
# z. B. `.tar`/`.RData`/`.CEL`-Archive gar nicht erst erfolglos geparst werden.
# EN: File extensions the best-effort GEO parser attempts to treat as
# table-like (see `_build_anndata_from_geo_best_effort`) — deliberately kept
# narrow so that e.g. `.tar`/`.RData`/`.CEL` archives are not even attempted.
_GEO_TABLE_SUFFIXES = (".txt", ".tsv", ".csv", ".txt.gz", ".tsv.gz", ".csv.gz")


def _build_anndata_from_geo_best_effort(
    wrapper: GEOWrapper, series_list: list[dict], recipe_key: str, *, compute_tsne: bool = False
) -> dict:
    """Best-Effort-Matrixaufbau aus GEO-Supplementary-Dateien (Back-Mediator M9,
    mit dem Nutzer als "GEO zusätzlich versuchen (best effort)" abgestimmt).

    GEO hat — anders als GDCs einheitliche STAR-Gene-Counts-Dateien — KEIN
    einheitliches Dateiformat über Serien hinweg. Dieser Versuch lädt je
    Serie die erste Datei mit einer tabellenartigen Endung
    (`_GEO_TABLE_SUFFIXES`) und liest sie generisch als ID/Wert-Tabelle
    (erste String-Spalte = ID, erste numerische Spalte = Wert). Scheitert das
    für ALLE Serien, wird ein klarer Fehler geworfen statt einer erfundenen
    Matrix; scheitert es nur für einzelne Serien, werden die übrigen trotzdem
    genutzt.

    English: Best-effort matrix build from GEO supplementary files
    (back-mediator M9, agreed with the user as "also try GEO (best effort)").

    Unlike GDC's uniform STAR gene-counts files, GEO has NO uniform file
    format across series. This attempt loads, per series, the first file
    with a table-like extension (`_GEO_TABLE_SUFFIXES`) and reads it
    generically as an ID/value table (first string column = ID, first
    numeric column = value). If this fails for ALL series, a clear error is
    raised instead of a fabricated matrix; if it only fails for individual
    series, the remaining ones are still used.
    """
    raw_dir = export_dir() / "geo_raw" / recipe_key
    values: dict[str, dict[str, float]] = {}
    feature_ids: list[str] = []
    used_series: list[str] = []

    for series in series_list:
        accession = series.get("accession")
        if not accession:
            continue
        series_dir = raw_dir / accession
        try:
            download = wrapper.download_supplementary_files(accession, str(series_dir))
        except RequestException:
            continue
        if download.get("status") != "completed":
            continue
        candidate_name = next(
            (name for name in download.get("files") or [] if name.lower().endswith(_GEO_TABLE_SUFFIXES)), None
        )
        if not candidate_name:
            continue
        try:
            df = pd.read_csv(series_dir / candidate_name, sep=None, engine="python", comment="#")
        except (OSError, ValueError, UnicodeDecodeError, pd.errors.ParserError):
            continue
        id_col = next((c for c in df.columns if df[c].dtype == object), None)
        numeric_cols = [c for c in df.columns if c != id_col and pd.api.types.is_numeric_dtype(df[c])]
        if id_col is None or not numeric_cols:
            continue
        value_col = numeric_cols[0]
        sample_values: dict[str, float] = {}
        for feature_id, value in zip(df[id_col], df[value_col]):
            if pd.isna(feature_id) or pd.isna(value):
                continue
            fid = str(feature_id)
            sample_values[fid] = float(value)
            if fid not in feature_ids:
                feature_ids.append(fid)
        if sample_values:
            values[accession] = sample_values
            used_series.append(accession)

    if not values:
        raise HTTPException(
            status_code=502,
            detail="Keine der gefundenen GEO-Serien lieferte eine auswertbare Supplementary-Tabelle "
            "(Best-Effort-Parser für .txt/.tsv/.csv — GEO hat kein einheitliches Dateiformat je Serie).",
        )

    X, sample_ids = expression_export.assemble_matrix_from_values(values, feature_ids)
    obs = pd.DataFrame(index=pd.Index(sample_ids, name="accession"))
    var = expression_export.build_var(feature_ids)

    obsm: dict[str, Any] = {}
    if compute_tsne:
        tsne = expression_export.compute_tsne(X)
        if tsne is not None:
            obsm["X_tsne_genes"] = tsne

    adata = expression_export.build_anndata(X, obs, var, obsm=obsm or None)
    filename = f"{recipe_key}.h5ad"
    out_path = expression_export.write_h5ad(adata, export_dir() / filename)

    return {
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "obs_columns": list(obs.columns),
        "var_columns": list(var.columns),
        "obsm_keys": list(obsm.keys()),
        "missing_files": [],
        "used_series": used_series,
        "filename": filename,
        "path": str(out_path),
        "download_url": f"/export/anndata/download/{filename}",
    }


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

    English: Loads the knowledge base of a selection into the default graph
    (P1, see wissensnetz/HANDOFF_pablo_store_waechst.md): the store is empty
    at start and grows with every `/selection/*` call — runs for both
    `preview` AND `generate` (answers decision 7.3: `preview` = fetch +
    translation + load, without raw data/matrix). `load_turtle` sends the
    text raw to Fuseki (no rdflib round-trip), so the appended RDF-star
    blocks survive (see `serialize_with_provenance`, ADR-0002,
    `wissensnetz/CLAUDE.md` "RDF-star trap").

    DELIBERATE, DOCUMENTED TECH DEBT (P4 in the handoff): pure appending, no
    `DELETE WHERE` per case before loading. RDF is a set — identical
    statements (instance IRIs are deterministically formed from `case_id`)
    collapse on their own and do no harm. But if a value for the same case
    changes between two calls (e.g. GDC updates `sex_at_birth`), two values
    for the same property result, until Marcel delivers the replacement
    logic (see handoff, P4) — deliberately not rebuilt here so there is no
    second variant of it.
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

    English: Cheap preview endpoint (decision 7.3: shared fetch without
    matrices, but WITH loading — see `_load_selection_knowledge`/P1).

    ONE files query per level (M3, `fetch_selection_files`), from which
    `cases_to_graph()` -> Turtle -> (if `request.load`) into the store.
    Deliberately builds NO anndata matrix (see `selection_generate` for
    that) — that is the difference between cheap and expensive. A failing
    level returns `status="error"` without affecting the other levels of the
    request.
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
            fetched = _fetch_selection_level(level, request, result.recipe_key, alignment)
            result.failed_cohorts = fetched.failed_cohorts
            result.turtle = semantic_mapping.serialize_with_provenance(fetched.graph, fetched.star_annotations)
            result.triple_count = len(fetched.graph)
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

    English: Expensive generate endpoint: in addition to the Turtle
    serialization/loading (see `selection_preview`), builds a `.h5ad` per
    level, on the same shared sample set (M3+M6). As with
    `selection_preview`, a failing level (e.g. missing `gdc-client` or
    unreachable Fuseki, see `_build_anndata_from_hits`) does not affect the
    other levels of the request.

    P5 (see wissensnetz/HANDOFF_pablo_store_waechst.md): a selection that has
    already been generated (identical `recipe_key`) is neither downloaded nor
    built again — the same cache short-circuit as in POST /export/anndata,
    now here too.
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

            fetched = _fetch_selection_level(level, request, recipe_key, alignment)
            result.failed_cohorts = fetched.failed_cohorts
            result.turtle = semantic_mapping.serialize_with_provenance(fetched.graph, fetched.star_annotations)
            result.triple_count = len(fetched.graph)
            if request.load:
                _load_selection_knowledge(result.turtle)
            anndata_meta = fetched.build_anndata()
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

    English: Builds an anndata/.h5ad from files hits (see
    `fetch_selection_files`, M3) (M6, see wissensnetz/HANDOFF_anndata.md and
    app/semantic/expression.py): download via `gdc-client`, X/var from the
    quantification files, `obs` from the wissensnetz.

    Shared core for POST /export/anndata and POST /selection/generate — works
    on exactly the `hits` the caller determined via `fetch_selection_files()`
    (M3: "one fetch, two serializations"). Aborts with a clear error instead
    of returning an incomplete matrix if `gdc-client` is missing or Fuseki is
    unreachable.
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
    # EN: File -> sample mapping directly from the search hits (same rule as
    # above when building sample_case_map: sample_id, else file_id as fallback).
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
    # EN: Interim solution for P3 (see wissensnetz/HANDOFF_pablo_store_waechst.md):
    # `all_cases(store)` still returns the ENTIRE stock, not scoped to this
    # selection — `wissensnetz.cases_for_selection(store, selection_id)` does
    # not exist yet (Marcel delivers it with P2). Until then, filter to the
    # submitter_ids we already have from the shared fetch (sample_case_map)
    # — same result for now (build_obs accessed it individually via
    # sample_case_map anyway), swappable for cases_for_selection once available.
    selected_submitters = {sub for sub in sample_case_map.values() if sub}
    cases_by_submitter = {
        c["submitter_id"]: c for c in all_cases(store) if c.get("submitter_id") in selected_submitters
    }

    obs = expression_export.build_obs(
        sample_case_map, cases_by_submitter, sample_types=sample_types, gdc_project_by_sample=sample_project_map
    )
    obs = obs.loc[sample_ids]  # dieselbe Zeilenreihenfolge wie X sicherstellen / EN: ensure the same row order as X
    var = expression_export.build_var(gene_ids_out, gene_labels)

    obsm: dict[str, Any] = {}
    if compute_tsne:
        tsne = expression_export.compute_tsne(X)
        if tsne is not None:
            obsm_key = "X_tsne_mirna" if experimental_strategy == "miRNA-Seq" else "X_tsne_genes"
            obsm[obsm_key] = tsne

    adata = expression_export.build_anndata(X, obs, var, obsm=obsm or None)

    out_filename = filename or f"{recipe_key}.h5ad"
    out_filename = Path(out_filename).name  # nur Basisname, keine Pfad-Traversal / EN: basename only, no path traversal
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

    English: GDC expression files -> anndata/.h5ad (part 3, see
    wissensnetz/HANDOFF_anndata.md and app/semantic/expression.py).

    Fetches the matching expression files via the shared fetch step (M3,
    `fetch_selection_files`) and builds the `.h5ad` from them via
    `_build_anndata_from_hits` (M6) — the same core that POST
    /selection/generate also uses. See GET
    /export/anndata/download/{filename} for the actual file download.
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
    # EN: Fetch files PER project instead of a single combined query
    # (stratification, see wissensnetz/HANDOFF_export_stratified.md) —
    # "sample_type" is the only attribute this endpoint traditionally
    # requests (obs column "sample_type"); additional clinical fields will
    # come in future via POST /selection/generate (M6), which knows arbitrary
    # `attributes[]` per level.
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
    """Lädt eine zuvor über POST /export/anndata erzeugte `.h5ad`-Datei herunter.

    English: Downloads a `.h5ad` file previously generated via POST /export/anndata.
    """
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")
    path = export_dir() / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Export nicht gefunden: {safe_name!r}")
    return FileResponse(path, media_type="application/octet-stream", filename=safe_name)
