"""
Cache-Grundgerüst für die drei Cache-Tiers des Mediator-Wrapper-Musters.

Aktuell eine einfache Datei-basierte Implementierung (JSON-Dateien unter
einem konfigurierbaren Cache-Verzeichnis). Das Interface ist bewusst schmal
gehalten, damit ein späterer Backend-Wechsel (z. B. Redis, Objektspeicher)
keine Aufrufer im Wrapper oder Mediator anfassen muss.

Tiers:
    1. Recipes      – Query-Spezifikationen, leichtgewichtig, immer gecacht.
    2. Materialized – Referenzen auf transformierte anndata-Objekte, nach
       der ersten Transformation gecacht (Transformation selbst passiert
       außerhalb dieses Wrappers, siehe client.py-Modul-Docstring).
    3. Raw          – Rohdaten (FASTQ/BAM etc.), nur transient, danach
       wieder gelöscht (`RawDataCache.purge`).

English: Cache skeleton for the three cache tiers of the mediator-wrapper
pattern.

Currently a simple file-based implementation (JSON files under a
configurable cache directory). The interface is deliberately kept narrow so
a later backend change (e.g. Redis, object storage) does not need to touch
any callers in the wrapper or mediator.

Tiers:
    1. Recipes      – query specifications, lightweight, always cached.
    2. Materialized – references to transformed anndata objects, cached
       after the first transformation (the transformation itself happens
       outside this wrapper, see the client.py module docstring).
    3. Raw          – raw data (FASTQ/BAM etc.), transient only, deleted
       again afterward (`RawDataCache.purge`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional


def _hash_key(payload: Any) -> str:
    """Deterministischer Kurz-Hash für ein JSON-serialisierbares Objekt (z. B. eine Recipe).

    English: Deterministic short hash for a JSON-serializable object (e.g. a recipe).
    """
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


class _FileBackedCache:
    """Gemeinsame Basis: Werte als JSON-Dateien in einem Tier-Unterordner ablegen.

    English: Shared base: store values as JSON files in a tier subfolder.
    """

    def __init__(self, cache_dir: Path, tier: str) -> None:
        self.dir = cache_dir / tier
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, key: str, value: Any) -> str:
        self._path(key).write_text(json.dumps(value, default=str), encoding="utf-8")
        return key

    def has(self, key: str) -> bool:
        return self._path(key).exists()


class RecipeCache(_FileBackedCache):
    """Tier 1: Query-Spezifikationen ("Recipes"). Klein, immer gecacht.

    English: Tier 1: query specifications ("recipes"). Small, always cached.
    """

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir, "recipes")

    def key_for(self, recipe: dict) -> str:
        return _hash_key(recipe)


class MaterializedCache(_FileBackedCache):
    """Tier 2: Referenzen auf materialisierte anndata-Objekte.

    Die .h5ad-Datei selbst entsteht in einem separaten Transformationsschritt
    außerhalb dieses Wrappers; hier wird nur die Zuordnung
    Recipe-Key -> Speicherort/Metadaten vorgehalten, damit dieser Schritt
    später nicht doppelt läuft.

    English: Tier 2: references to materialized anndata objects.

    The .h5ad file itself is produced in a separate transformation step
    outside this wrapper; only the mapping recipe-key -> storage
    location/metadata is kept here, so that this step does not run twice
    later.
    """

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir, "materialized")


class RawDataCache:
    """Tier 3: Rohdaten (FASTQ/BAM). Nur transient — nach Verarbeitung löschen.

    English: Tier 3: raw data (FASTQ/BAM). Transient only — delete after processing.
    """

    def __init__(self, cache_dir: Path) -> None:
        self.dir = cache_dir / "raw"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        """Liefert (und legt bei Bedarf an) das Arbeitsverzeichnis für einen Rohdaten-Schlüssel.

        English: Returns (and creates if needed) the working directory for a raw-data key.
        """
        path = self.dir / key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def purge(self, key: str) -> None:
        """Löscht die transienten Rohdaten für einen Schlüssel wieder (Tier 3 ist nicht dauerhaft).

        English: Deletes the transient raw data for a key again (tier 3 is not persistent).
        """
        path = self.dir / key
        if path.exists():
            shutil.rmtree(path)


class WrapperCache:
    """Bündelt alle drei Tiers hinter einem Zugriffspunkt je Wrapper-Instanz.

    English: Bundles all three tiers behind a single access point per wrapper instance.
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        base = Path(cache_dir or os.environ.get("DATABRIDGE_CACHE_DIR", ".cache/databridge"))
        self.recipes = RecipeCache(base)
        self.materialized = MaterializedCache(base)
        self.raw = RawDataCache(base)
