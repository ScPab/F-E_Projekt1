"""Pfad-Auflösung für Ontologie-/Alignment-Dateien sowie anndata-Exporte.

Gleiches Muster wie DATABRIDGE_CACHE_DIR in wrappers/gdc/cache.py: über
Umgebungsvariable konfigurierbar (im Container gesetzt auf /ontology, siehe
mediator/Dockerfile), mit lokalem Fallback relativ zum Repo, damit der Code
auch außerhalb von Docker (z. B. für scripts/example_gdc_to_rdf.py) läuft.

English: Path resolution for ontology/alignment files as well as anndata
exports.

Same pattern as DATABRIDGE_CACHE_DIR in wrappers/gdc/cache.py: configurable
via environment variable (set to /ontology in the container, see
mediator/Dockerfile), with a local fallback relative to the repo so the code
also runs outside Docker (e.g. for scripts/example_gdc_to_rdf.py).
"""

from __future__ import annotations

import os
from pathlib import Path

# mediator/app/semantic/paths.py -> parents[3] == Repo-Root
# EN: mediator/app/semantic/paths.py -> parents[3] == repo root
_MEDIATOR_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_FALLBACK = Path(__file__).resolve().parents[3] / "wissensnetz" / "ontology"


def ontology_dir() -> Path:
    configured = os.environ.get("DATABRIDGE_ONTOLOGY_DIR")
    return Path(configured) if configured else _LOCAL_FALLBACK


def ontology_path() -> Path:
    return ontology_dir() / "databridge-core.ttl"


def alignment_path(name: str) -> Path:
    return ontology_dir() / "alignment" / name


def export_dir() -> Path:
    """Zielverzeichnis für POST /export/anndata (siehe app/semantic/expression.py).

    Über DATABRIDGE_EXPORT_DIR konfigurierbar; lokaler Fallback analog zu
    scripts/example_gdc_to_rdf.py's scripts/output/-Konvention.

    English: Target directory for POST /export/anndata (see
    app/semantic/expression.py). Configurable via DATABRIDGE_EXPORT_DIR;
    local fallback analogous to scripts/example_gdc_to_rdf.py's
    scripts/output/ convention.
    """
    configured = os.environ.get("DATABRIDGE_EXPORT_DIR")
    path = Path(configured) if configured else _MEDIATOR_ROOT / "scripts" / "output" / "anndata"
    path.mkdir(parents=True, exist_ok=True)
    return path
