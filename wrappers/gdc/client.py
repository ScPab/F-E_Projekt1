"""
Wrapper für die GDC (Genomic Data Commons) Developer API — Testfall TCGA.

Dies ist bewusst nur ein Grundgerüst (Boilerplate) im Sinne des
Mediator-Wrapper-Musters: Der Wrapper kapselt später den Zugriff auf eine
konkrete Datenquelle (hier: GDC-REST-API) und liefert Daten in einer vom
Mediator erwarteten Zwischenform. Die eigentliche Abfrage- und
Transformationslogik (inkl. Export nach anndata/.h5ad) folgt in späteren
Schritten.
"""

from __future__ import annotations


class GDCWrapper:
    """Platzhalter-Schnittstelle für den Zugriff auf die GDC Developer API.

    Basis-URL laut GDC-Dokumentation: https://api.gdc.cancer.gov
    (wird über Umgebungsvariable GDC_API_BASE_URL konfigurierbar gehalten,
    siehe .env.example.)
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def fetch(self, query: dict) -> None:
        """Fragt Daten von der GDC-API ab (noch nicht implementiert)."""
        raise NotImplementedError("Datenabfrage folgt in einem späteren Schritt.")

    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine GDC-Antwort in das Zielformat anndata/.h5ad (noch nicht implementiert)."""
        raise NotImplementedError("Transformation nach anndata folgt in einem späteren Schritt.")
