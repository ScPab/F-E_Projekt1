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
