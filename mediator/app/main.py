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
from typing import Any

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
    TransformRequest,
)
from .semantic import expression as expression_export
from .semantic import mapping as semantic_mapping
from .semantic.paths import alignment_path, export_dir, ontology_path

# Felder für den Live-Abruf von POST /transform (Kern-Ausschnitt
# case/project/demographic/diagnosis/samples, siehe app/semantic/mapping.py).
# Erweitert um die volle Oviedo-Hover-Feldliste (siehe
# wissensnetz/prototype/mp_lite/HANDOFF.md, Teil 1/2): race/ethnicity/
# vital_status (demographic), morphology/site_of_resection_or_biopsy/
# ajcc_pathologic_stage/metastasis_at_diagnosis (diagnoses) sowie
# sample_id/sample_type (samples) — live gegen die GDC-API verifiziert
# (siehe HANDOFF.md-Checkliste, 2026-08-28); `diagnoses.tumor_stage`
# existiert dort nicht, daher `diagnoses.ajcc_pathologic_stage`.
TRANSFORM_CASE_FIELDS = [
    "case_id",
    "submitter_id",
    "project.project_id",
    "demographic.gender",
    "demographic.race",
    "demographic.ethnicity",
    "demographic.vital_status",
    "diagnoses.primary_diagnosis",
    "diagnoses.age_at_diagnosis",
    "diagnoses.morphology",
    "diagnoses.site_of_resection_or_biopsy",
    "diagnoses.ajcc_pathologic_stage",
    "diagnoses.metastasis_at_diagnosis",
    "samples.sample_id",
    "samples.sample_type",
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


@app.post("/export/anndata")
async def export_anndata(request: AnndataExportRequest) -> dict:
    """GDC-Expressionsdateien -> anndata/.h5ad (Teil 3, siehe
    wissensnetz/HANDOFF_anndata.md und app/semantic/expression.py).

    Ablauf: (1) passende Expressions-Files über den GDC-Wrapper suchen,
    (2) sie über das bestehende Bulk-Tier (`build_manifest` +
    `download_via_gdc_client`, benötigt `gdc-client` im Container)
    herunterladen, (3) daraus X/var zusammenbauen, (4) `obs` aus dem
    Wissensnetz (`enrichment.all_cases`) anreichern, (5) als `.h5ad`
    schreiben. Bricht mit einem klaren Fehler ab, statt eine unvollständige
    Matrix zurückzugeben, wenn `gdc-client` fehlt oder Fuseki nicht
    erreichbar ist — siehe GET /export/anndata/download/{filename} für den
    eigentlichen Datei-Download (Offener Punkt 4 im Handoff: Download-Endpoint).
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
        "gene_ids": request.gene_ids,
        "compute_tsne": request.compute_tsne,
    }
    recipe_key = wrapper.cache.recipes.key_for(recipe)
    cached = wrapper.cache.materialized.get(recipe_key)
    if cached and Path(cached["path"]).exists():
        return cached

    file_filters = build_filters(
        project_id=request.project_id,
        experimental_strategy=request.experimental_strategy,
        access="open",
        extra=[{"op": "in", "content": {"field": "files.data_type", "value": [request.data_type]}}],
    )
    file_fields = [
        "file_id",
        "file_name",
        "cases.submitter_id",
        "cases.project.project_id",
        "cases.samples.sample_id",
        "cases.samples.sample_type",
    ]
    try:
        result = wrapper.query("files", filters=file_filters, fields=file_fields, size=request.size)
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"GDC-API nicht erreichbar oder Fehler: {exc}") from exc

    hits = result["results"]
    if not hits:
        raise HTTPException(
            status_code=404,
            detail=f"Keine Expressions-Files gefunden für project_id={request.project_id!r}, "
            f"experimental_strategy={request.experimental_strategy!r}, data_type={request.data_type!r}.",
        )

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
        X, sample_ids, gene_ids, gene_labels = expression_export.assemble_matrix(
            sample_files,
            id_column=request.id_column,
            value_column=request.value_column,
            label_column=request.label_column,
            gene_ids=request.gene_ids,
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
    cases_by_submitter = {c["submitter_id"]: c for c in all_cases(store) if c.get("submitter_id")}

    obs = expression_export.build_obs(sample_case_map, cases_by_submitter, sample_types=sample_types, gdc_project_by_sample=sample_project_map)
    obs = obs.loc[sample_ids]  # dieselbe Zeilenreihenfolge wie X sicherstellen
    var = expression_export.build_var(gene_ids, gene_labels)

    obsm: dict[str, Any] = {}
    if request.compute_tsne:
        tsne = expression_export.compute_tsne(X)
        if tsne is not None:
            obsm_key = "X_tsne_mirna" if request.experimental_strategy == "miRNA-Seq" else "X_tsne_genes"
            obsm[obsm_key] = tsne

    adata = expression_export.build_anndata(X, obs, var, obsm=obsm or None)

    filename = request.filename or f"{recipe_key}.h5ad"
    filename = Path(filename).name  # nur Basisname, keine Pfad-Traversal
    if not filename.endswith(".h5ad"):
        filename += ".h5ad"
    out_path = expression_export.write_h5ad(adata, export_dir() / filename)

    wrapper.cache.raw.purge(recipe_key)

    metadata = {
        "project_id": request.project_id,
        "experimental_strategy": request.experimental_strategy,
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "obs_columns": list(obs.columns),
        "var_columns": list(var.columns),
        "obsm_keys": list(obsm.keys()),
        "missing_files": missing_files,
        "filename": filename,
        "path": str(out_path),
        "download_url": f"/export/anndata/download/{filename}",
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
