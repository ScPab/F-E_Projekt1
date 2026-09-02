"""Pydantic-Modelle für die Mediator-REST-API rund um den GDC-Wrapper.

Bewusst vereinfachte Request-Formen (Projekt-ID, Experimentstrategie,
Access-Level, gewünschte Felder) statt des vollen GDC-`filters`-Schemas —
die Übersetzung in einen validen GDC-Query übernimmt `gdc.client.build_filters`.
"""

from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field

StrOrList = Union[str, list[str]]


class QueryRequest(BaseModel):
    """Suchparameter für POST /query (Metadaten-Tier)."""

    endpoint: str = Field("files", description="GDC-Metadaten-Endpunkt: cases, files, projects, annotations")
    project_id: Optional[StrOrList] = Field(None, description='z. B. "TCGA-BRCA"')
    experimental_strategy: Optional[StrOrList] = Field(None, description='z. B. "RNA-Seq"')
    access: Optional[StrOrList] = Field("open", description="Access-Level, Standard: nur offen zugängliche Daten")
    fields: Optional[list[str]] = Field(None, description="Gewünschte Rückgabefelder (siehe GET /schema/{endpoint})")
    size: int = Field(20, ge=1, le=2000, description="Trefferanzahl pro Seite")
    from_: int = Field(0, ge=0, alias="from", description="Pagination-Offset")

    model_config = {"populate_by_name": True}


class ManifestRequest(BaseModel):
    """Suchparameter für POST /manifest (Bulk-Tier)."""

    project_id: Optional[StrOrList] = None
    experimental_strategy: Optional[StrOrList] = None
    access: Optional[StrOrList] = "open"
    size: int = Field(10000, ge=1, le=100000)


class GeoQueryRequest(BaseModel):
    """Suchparameter für POST /geo/query (Metadaten-Tier, GEOWrapper.search)."""

    accession: Optional[str] = Field(None, description='GEO-Accession, z. B. "GSE68849"')
    organism: Optional[StrOrList] = Field(None, description='z. B. "Homo sapiens"')
    entry_type: Optional[str] = Field("gse", description="gse (Series), gds, gpl oder gsm")
    db: str = Field("gds", description="Entrez-Datenbank, Standard: gds")
    size: int = Field(20, ge=1, le=2000, description="Trefferanzahl pro Seite")
    from_: int = Field(0, ge=0, alias="from", description="Pagination-Offset")

    model_config = {"populate_by_name": True}


class EnaQueryRequest(BaseModel):
    """Suchparameter für POST /ena/query (Metadaten-Tier, ENAWrapper.search)."""

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
    (Bulk-Tier-Äquivalent, CBioPortalWrapper.get_molecular_data)."""

    sample_list_id: str = Field(..., description="ID der Sample-Liste (siehe GET /cbioportal/sample-lists/{study_id})")
    entrez_gene_ids: list[int] = Field(..., description="Entrez-Gen-IDs, für die Werte abgerufen werden sollen")
    projection: str = Field("SUMMARY", description="Detailgrad der Antwort laut cBioPortal-API")


class TransformRequest(BaseModel):
    """Anfrage für POST /transform (GDC-JSON -> RDF/OWL, siehe app/semantic/mapping.py).

    Entweder werden rohe `cases`-Treffer übergeben (z. B. aus einer
    vorherigen POST /query-Antwort), oder sie werden — falls `cases` leer
    ist — live über den GDC-Wrapper geholt.
    """

    source: str = Field("gdc", description="Aktuell nur 'gdc' unterstützt.")
    cases: Optional[list[dict]] = Field(
        None,
        description="Rohe GDC-cases-Treffer (case_id, project.project_id, demographic.gender, "
        "diagnoses[].primary_diagnosis, diagnoses[].age_at_diagnosis). Wenn nicht gesetzt, "
        "wird live über GDCWrapper.search('cases', ...) geholt.",
    )
    project_id: Optional[StrOrList] = Field(None, description='z. B. "TCGA-BRCA" (nur relevant ohne "cases")')
    access: Optional[StrOrList] = Field("open", description="Access-Level für den Live-Abruf")
    size: int = Field(20, ge=1, le=2000, description="Trefferanzahl für den Live-Abruf")
    load: bool = Field(
        False,
        description="Bei true: das erzeugte Turtle zusätzlich direkt per Graph Store "
        "Protocol in graph-db (Fuseki) schreiben, statt es nur als Text zurückzugeben.",
    )
    graph: Optional[str] = Field(
        None, description="Named-Graph-IRI für den Fuseki-Import (nur mit load=true); ohne Angabe Default-Graph."
    )


class AnndataExportRequest(BaseModel):
    """Anfrage für POST /export/anndata (GDC-Expressionsdaten -> anndata/.h5ad,
    Teil 3 aus wissensnetz/HANDOFF_anndata.md).

    Baut aus GDC-Expressions-Rohdateien (Bulk-Tier des GDCWrapper) + den
    klinischen Oviedo-Feldern aus dem Wissensnetz (`enrichment.all_cases`)
    einen `anndata.AnnData`-Container und schreibt ihn als `.h5ad`. Setzt
    einen funktionierenden `gdc-client` im Container voraus (siehe
    GDCWrapper.download_via_gdc_client) — ohne das liefert der Endpoint
    einen klaren 503-Fehler statt einer unvollständigen/erfundenen Matrix.
    """

    project_id: StrOrList = Field(..., description='z. B. "TCGA-BRCA"')
    experimental_strategy: str = Field(
        "RNA-Seq", description='"RNA-Seq" (Gene-Counts) oder "miRNA-Seq" (miRNA-Quantifizierung)'
    )
    data_type: str = Field(
        "Gene Expression Quantification",
        description='GDC files.data_type; bei miRNA-Seq "miRNA Expression Quantification" verwenden.',
    )
    id_column: str = Field("gene_id", description='Spalte mit der Feature-ID in der Quantifizierungsdatei.')
    value_column: str = Field(
        "tpm_unstranded",
        description='Spalte mit dem X-Wert; bei miRNA-Seq z. B. "reads_per_million_miRNA_mapped".',
    )
    label_column: Optional[str] = Field(
        "gene_name", description="Optionale Spalte für var['symbol'] (z. B. Gene-Symbol); ohne Treffer bleibt None."
    )
    size: int = Field(
        5,
        ge=1,
        le=200,
        description="Anzahl Expressions-Dateien (~Proben). Bei einem einzelnen project_id: Gesamtzahl. "
        "Bei project_id als Liste (Pancancer/Multi-Kohorten): Anzahl PRO Kohorte, sofern per_project_size "
        "nicht gesetzt ist — sonst gilt dieses Feld nur als Fallback-Wert. Klein halten (Bulk-Download je Aufruf).",
    )
    per_project_size: Optional[int] = Field(
        None,
        ge=1,
        le=200,
        description="Anzahl Expressions-Dateien PRO Projekt/Kohorte, explizit getrennt von 'size' gehalten. "
        "Nur relevant, wenn project_id eine Liste ist — verhindert, dass ein Multi-Kohorten-Export alle "
        "Proben aus derselben (in GDCs Default-Reihenfolge zuerst gelisteten) Kohorte zieht, siehe "
        "wissensnetz/HANDOFF_export_stratified.md. Gesamtzahl = per_project_size × Anzahl Kohorten — bei "
        "vielen Kohorten (z. B. Pancancer, 32) daher klein halten (z. B. 5).",
    )
    gene_ids: Optional[list[str]] = Field(
        None, description="Optionale Whitelist (Genumfang einschränken); ohne Angabe alle in den Dateien gefundenen."
    )
    compute_tsne: bool = Field(
        False,
        description="Optional: 2D-tSNE (scikit-learn) berechnen und als obsm['X_tsne_genes'] ablegen "
        "(siehe HANDOFF_anndata.md, Offener Punkt 2). Bei <=3 Proben automatisch übersprungen.",
    )
    filename: Optional[str] = Field(
        None, description="Ziel-Dateiname (.h5ad, nur Basisname); ohne Angabe automatisch aus project_id generiert."
    )
