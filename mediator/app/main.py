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

Die eigentliche Transformationslogik nach anndata/.h5ad (Messmatrizen) folgt
in späteren Schritten. Die semantische Transformation (GDC-JSON -> RDF/OWL)
für den Kern-Ausschnitt case/project/demographic/diagnosis ist über
POST /transform bereits angebunden (siehe app/semantic/mapping.py sowie
wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL für das zugrundeliegende Konzept).
"""

import os

from cbioportal import CBioPortalWrapper
from ena import ENAWrapper
from fastapi import FastAPI, HTTPException, Query, Response
from gdc import GDCWrapper, build_filters
from geo import GEOWrapper
from requests import RequestException
from wissensnetz import GraphStore, GraphStoreError

from .schemas import (
    CBioMolecularDataRequest,
    EnaQueryRequest,
    GeoQueryRequest,
    ManifestRequest,
    QueryRequest,
    TransformRequest,
)
from .semantic import mapping as semantic_mapping
from .semantic.paths import alignment_path, ontology_path

# Felder für den Live-Abruf von POST /transform (Kern-Ausschnitt
# case/project/demographic/diagnosis, siehe app/semantic/mapping.py).
TRANSFORM_CASE_FIELDS = [
    "case_id",
    "submitter_id",
    "project.project_id",
    "demographic.gender",
    "diagnoses.primary_diagnosis",
    "diagnoses.age_at_diagnosis",
]

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
    """GDC-Cases -> RDF/OWL-Tripel (Turtle), gemäß wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL.

    Nimmt entweder rohe `cases`-Treffer entgegen oder holt sie live über den
    GDC-Wrapper. Ausgabe ist immer der erzeugte Turtle-Text; bei `load=true`
    wird er zusätzlich direkt per Graph Store Protocol in graph-db (Fuseki)
    geschrieben (siehe `wissensnetz.GraphStore.load_turtle`, ADR-0002) — die
    Turtle-Ausgabe bleibt roh erhalten, damit die angehängten RDF-star-Blöcke
    (Provenienz/Konfidenz) nicht durch einen rdflib-Roundtrip verloren gehen.
    """
    if request.source != "gdc":
        raise HTTPException(status_code=400, detail=f"Unbekannte Quelle: {request.source!r} (aktuell nur 'gdc')")

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
