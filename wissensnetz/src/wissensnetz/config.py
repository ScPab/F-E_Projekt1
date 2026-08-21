"""Konfiguration des Wissensnetz-Clients (Fuseki-Anbindung + Namespaces).

Alles wird aus Umgebungsvariablen gelesen (Muster wie ``.env.example`` im
Repo-Root). Innerhalb von Docker Compose zeigt ``GRAPH_DB_URL`` auf
``http://graph-db:3030`` (Service-Name), außerhalb auf ``localhost``.

Komponentengrenze: Dieses Paket spricht ausschließlich per HTTP/SPARQL gegen
den ``graph-db``-Service (Apache Jena Fuseki). Es importiert keinen Code aus
``mediator/`` oder ``wrappers/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# --- Namespaces (identisch zur TBox databridge-core.ttl / Mediator-Mapping) ---
DB = "http://databridge.hka/onto#"
INSTANCE = "http://databridge.hka/instance/"
NCIT = "http://purl.obolibrary.org/obo/NCIT_"
PROV = "http://www.w3.org/ns/prov#"
OA = "http://www.w3.org/ns/oa#"

# Für SPARQL-Abfragen wiederverwendbarer PREFIX-Block.
PREFIXES = f"""\
PREFIX db:   <{DB}>
PREFIX ncit: <{NCIT}>
PREFIX prov: <{PROV}>
PREFIX oa:   <{OA}>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
"""


def _default_base_url() -> str:
    """Basis-URL aus ``GRAPH_DB_URL`` oder aus Host/Port zusammengesetzt."""
    explicit = os.environ.get("GRAPH_DB_URL")
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("GRAPH_DB_HOST", "localhost")
    port = os.environ.get("GRAPH_DB_PORT", "3030")
    return f"http://{host}:{port}"


@dataclass(frozen=True)
class Settings:
    """Verbindungsparameter für den Fuseki-Store."""

    base_url: str
    dataset: str
    admin_user: str
    admin_password: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            base_url=_default_base_url(),
            dataset=os.environ.get("GRAPH_DB_DATASET", "databridge"),
            admin_user=os.environ.get("GRAPH_DB_ADMIN_USER", "admin"),
            admin_password=os.environ.get("GRAPH_DB_ADMIN_PASSWORD", "admin"),
        )

    # --- abgeleitete Endpunkt-URLs (Fuseki-Konvention) ---
    @property
    def query_url(self) -> str:
        return f"{self.base_url}/{self.dataset}/query"

    @property
    def update_url(self) -> str:
        return f"{self.base_url}/{self.dataset}/update"

    @property
    def gsp_url(self) -> str:
        """Graph Store Protocol-Endpunkt (Laden von Turtle)."""
        return f"{self.base_url}/{self.dataset}/data"

    @property
    def admin_datasets_url(self) -> str:
        return f"{self.base_url}/$/datasets"

    @property
    def ping_url(self) -> str:
        return f"{self.base_url}/$/ping"
