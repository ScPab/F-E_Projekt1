# Cleanup-Log: unbenutzte Mediator-Endpunkte entfernt

**Datum:** 2026-09-25
**Betrifft:** `mediator/app/main.py`, `mediator/app/schemas.py`
**Warum:** Repo-weite Durchsicht des Mediator-Teils im Systemzusammenhang
(Frontend, Scripts, Wissensnetz, Tests, Docker) ergab, dass 13 von 22
REST-Endpunkten von **niemandem im Repo aufgerufen werden** — auch nicht vom
mediator-eigenen Smoke-Test (`mediator/scripts/check_mediator.py`). Es sind
generische 1:1-Durchreichen zu den Wrappern (GEO/ENA/cBioPortal), die beim
Hinzufügen dieser Wrapper mitgebaut, aber nie an eine Oberfläche
angeschlossen wurden. Der Modul-Docstring von `main.py` sagte selbst, wofür
sie gedacht waren: *"...bilden die Schnittstelle, über die **spätere**
Aufrufer (Frontend, andere Services) ... zugreifen"* — die Oberfläche bekam
stattdessen die `/selection/*`-Pipeline (Back-Mediator, M9).

**Ausdrücklich NICHT angefasst** (siehe Gespräch vom 2026-09-25):
`mediator/app/semantic/mapping_ena.py`, der `ena`-Zweig in `POST /transform`
und `get_ena_wrapper()` — ENA ist in der Auswahl-Pipeline bewusst nicht
angebunden (`_fetch_selection_level`, main.py, dokumentierte
Architekturentscheidung), das wird separat besprochen, ob das als Kommentar/
ADR im Code bleibt statt als totem Codepfad.

## Wie wiederherstellen

Jeder Block unten steht im Originalzustand da — einfach zurückkopieren.
Alternativ, falls seither committet wurde: `git log --oneline -- mediator/app/main.py mediator/app/schemas.py`
und den Commit vor diesem Cleanup auschecken/cherry-picken.

---

## 1. Entfernte Endpunkte aus `mediator/app/main.py`

### `GET /schema/{endpoint}` (war Zeile 331)

```python
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
```

### `POST /manifest` (war Zeile 352)

```python
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
```

### GEO-Sektion (war Zeile 371-424): `POST /geo/query`, `GET /geo/schema`, `GET /geo/ftp-link/{accession}`

```python
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
```

### ENA-Sektion (war Zeile 427-482): `POST /ena/query`, `GET /ena/schema/{result}`, `GET /ena/download-links/{run_accession}`

```python
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
```

*(`get_ena_wrapper()` selbst bleibt im Code — wird weiterhin vom `ena`-Zweig
in `POST /transform` gebraucht, siehe "Ausdrücklich NICHT angefasst" oben.)*

### cBioPortal-Sektion (war Zeile 485-589): alle 6 Endpunkte

```python
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
```

*(`get_cbioportal_wrapper()` selbst bleibt im Code — wird weiterhin von
`_fetch_cbioportal_level` in der `/selection/*`-Pipeline gebraucht.)*

---

## 2. Entfernte Pydantic-Schemas aus `mediator/app/schemas.py`

Nur von den oben entfernten Endpunkten benutzt, sonst nirgendwo im Repo
referenziert.

```python
class ManifestRequest(BaseModel):
    """Suchparameter für POST /manifest (Bulk-Tier).

    English: Search parameters for POST /manifest (bulk tier).
    """

    project_id: Optional[StrOrList] = None
    experimental_strategy: Optional[StrOrList] = None
    access: Optional[StrOrList] = "open"
    size: int = Field(10000, ge=1, le=100000)


class GeoQueryRequest(BaseModel):
    """Suchparameter für POST /geo/query (Metadaten-Tier, GEOWrapper.search).

    English: Search parameters for POST /geo/query (metadata tier, GEOWrapper.search).
    """

    accession: Optional[str] = Field(None, description='GEO-Accession, z. B. "GSE68849"')
    organism: Optional[StrOrList] = Field(None, description='z. B. "Homo sapiens"')
    entry_type: Optional[str] = Field("gse", description="gse (Series), gds, gpl oder gsm")
    db: str = Field("gds", description="Entrez-Datenbank, Standard: gds")
    size: int = Field(20, ge=1, le=2000, description="Trefferanzahl pro Seite")
    from_: int = Field(0, ge=0, alias="from", description="Pagination-Offset")

    model_config = {"populate_by_name": True}


class EnaQueryRequest(BaseModel):
    """Suchparameter für POST /ena/query (Metadaten-Tier, ENAWrapper.search).

    English: Search parameters for POST /ena/query (metadata tier, ENAWrapper.search).
    """

    result: str = Field("read_run", description="ENA-Ergebnistyp, z. B. read_run, study, sample")
    study_accession: Optional[StrOrList] = Field(None, description='z. B. "PRJEB1234"')
    library_strategy: Optional[StrOrList] = Field(None, description='z. B. "RNA-Seq"')
    instrument_platform: Optional[StrOrList] = Field(None, description='z. B. "ILLUMINA"')
    fields: Optional[list[str]] = Field(None, description="Gewünschte Rückgabefelder (siehe GET /ena/schema/{result})")
    size: int = Field(20, ge=1, le=2000, description="Trefferanzahl pro Seite")
    from_: int = Field(0, ge=0, alias="from", description="Pagination-Offset")

    model_config = {"populate_by_name": True}


class CBioMolecularDataRequest(BaseModel):
    """Suchparameter für POST /cbioportal/molecular-data/{molecular_profile_id}
    (Bulk-Tier-Äquivalent, CBioPortalWrapper.get_molecular_data).

    English: Search parameters for POST
    /cbioportal/molecular-data/{molecular_profile_id} (bulk-tier equivalent,
    CBioPortalWrapper.get_molecular_data).
    """

    sample_list_id: str = Field(..., description="ID der Sample-Liste (siehe GET /cbioportal/sample-lists/{study_id})")
    entrez_gene_ids: list[int] = Field(..., description="Entrez-Gen-IDs, für die Werte abgerufen werden sollen")
    projection: str = Field("SUMMARY", description="Detailgrad der Antwort laut cBioPortal-API")
```

---

## 3. Angepasste Imports in `mediator/app/main.py`

Vorher:
```python
from fastapi import FastAPI, HTTPException, Query, Response
...
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
```

Nachher: `Query` entfernt (war nur in den gelöschten cBioPortal-Endpunkten
für `from_: int = Query(0, alias="from")` gebraucht), `CBioMolecularDataRequest`/
`EnaQueryRequest`/`GeoQueryRequest`/`ManifestRequest` aus dem Schema-Import
entfernt. `build_filters`, `geo_build_search_term`, `get_geo_wrapper`,
`get_ena_wrapper`, `get_cbioportal_wrapper`, `QueryRequest`, `CBioPortalWrapper`,
`ENAWrapper`, `GEOWrapper` bleiben — werden anderswo noch gebraucht (siehe
Prüfung unten).

## 4. Angepasster Modul-Docstring in `mediator/app/main.py`

Vorher: *"Die hier exponierten Endpunkte (/query, /schema/{endpoint},
/manifest) bilden die Schnittstelle..."* — jetzt nur noch `/query` genannt,
da `/schema/{endpoint}` und `/manifest` nicht mehr existieren.

---

## 5. Vor der Entfernung geprüft (damit nichts kaputtgeht)

- `build_filters` (aus `gdc`): auch in `resolve_case_fields`-Umfeld (Zeile ~178)
  und `_build_anndata_from_hits` (Zeile ~1478) gebraucht → Import bleibt.
- `geo_build_search_term`: auch in `_build_anndata_from_geo_best_effort`
  (Zeile ~1140) gebraucht → Import bleibt.
- `get_geo_wrapper`/`get_ena_wrapper`/`get_cbioportal_wrapper`: alle drei
  weiterhin von der `/selection/*`-Pipeline (`_fetch_geo_level`,
  `_fetch_cbioportal_level`) bzw. vom `ena`-Zweig in `/transform` gebraucht
  → Getter-Funktionen bleiben unverändert im Code.
- `CBioPortalWrapper`, `ENAWrapper`, `GEOWrapper` (Wrapper-Klassen-Importe):
  bleiben aus demselben Grund.
- `mediator/scripts/check_mediator.py` (Smoke-Test) ruft nur `/health`,
  `/ontology`, `/query`, `/transform` auf — keiner der entfernten Endpunkte
  war dort verdrahtet, Smoke-Test bleibt unverändert lauffähig.
- `frontend/`, `wissensnetz/`, `scripts/` (Repo-Root): keine Treffer für
  irgendeinen der entfernten Pfade (`grep -rl` repo-weit geprüft, siehe
  Analyse vom 2026-09-24/25).

## 6. Was NICHT entfernt wurde (bewusst)

- `POST /query`, `GET /ontology` — nur vom Smoke-Test benutzt, aber
  benutzt; bleiben.
- `mediator/app/semantic/mapping_ena.py`, `ena`-Zweig in `POST /transform`,
  `get_ena_wrapper()` — dokumentierte Architekturentscheidung (ENA bewusst
  nicht an die Auswahl-Pipeline angebunden), wird separat besprochen.
- `mediator/scripts/example_gdc_to_rdf.py`, `example_expression_to_anndata.py`
  — wirken wie Wegwerf-Demos, erzeugen aber Fixtures, die
  `wissensnetz/tests/` und der MP-Lite-Prototyp tatsächlich brauchen.
