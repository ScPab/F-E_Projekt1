"""Pfad-Auflösung für Ontologie-/Alignment-Dateien.

Gleiches Muster wie DATABRIDGE_CACHE_DIR in wrappers/gdc/cache.py: über
Umgebungsvariable konfigurierbar (im Container gesetzt auf /ontology, siehe
mediator/Dockerfile), mit lokalem Fallback relativ zum Repo, damit der Code
auch außerhalb von Docker (z. B. für scripts/example_gdc_to_rdf.py) läuft.
"""

from __future__ import annotations

import os
from pathlib import Path

# mediator/app/semantic/paths.py -> parents[3] == Repo-Root
_LOCAL_FALLBACK = Path(__file__).resolve().parents[3] / "wissensnetz" / "ontology"


def ontology_dir() -> Path:
    configured = os.environ.get("DATABRIDGE_ONTOLOGY_DIR")
    return Path(configured) if configured else _LOCAL_FALLBACK


def ontology_path() -> Path:
    return ontology_dir() / "databridge-core.ttl"


def alignment_path(name: str) -> Path:
    return ontology_dir() / "alignment" / name
