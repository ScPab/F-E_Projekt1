"""
DataBridge Mediator – FastAPI-Grundgerüst.

Der Mediator ist der zentrale Einstiegspunkt der Mediator-Wrapper-Architektur:
Er nimmt Anfragen entgegen und delegiert sie an die passenden Wrapper-Module
(aktuell: wrappers/gdc, als Python-Package im selben Container installiert,
siehe docs/adr/0001-wrapper-als-python-package.md) für die eigentliche
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

from fastapi import FastAPI, HTTPException, Response
from gdc import GDCWrapper, build_filters
from requests import RequestException
from wissensnetz import GraphStore, GraphStoreError

from .schemas import ManifestRequest, QueryRequest, TransformRequest
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
