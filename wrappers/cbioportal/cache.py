"""
Cache-Grundgerüst für die drei Cache-Tiers des Mediator-Wrapper-Musters.

Eigenständige Kopie derselben dateibasierten Implementierung wie
`wrappers/gdc/cache.py` / `wrappers/geo/cache.py` / `wrappers/ena/cache.py`
— bewusst nicht importiert, damit dieser Wrapper unabhängig von den anderen
bleibt (siehe ADR-0001: jede Datenquelle ein eigenes Unterpaket). Das
Interface ist bewusst schmal gehalten, damit ein späterer Backend-Wechsel
(z. B. Redis, Objektspeicher) keine Aufrufer im Wrapper oder Mediator
anfassen muss.

Tiers:
    1. Recipes      – Query-Spezifikationen (hier: Studien-/Klinikdaten-/
       Molekulardaten-Abfragen), leichtgewichtig, immer gecacht.
    2. Materialized – Referenzen auf transformierte anndata-Objekte, nach
       der ersten Transformation gecacht (Transformation selbst passiert
       außerhalb dieses Wrappers, siehe client.py-Modul-Docstring).
    3. Raw          – Rohdaten. Bei cBioPortal in der Praxis kaum relevant,
       da die API selbst schon aufbereitete (nicht rohe) Daten liefert —
       Tier bleibt trotzdem vorhanden, um dieselbe Cache-Schnittstelle wie
       bei den anderen Wrappern zu bieten.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional


def _hash_key(payload: Any) -> str:
    """Deterministischer Kurz-Hash für ein JSON-serialisierbares Objekt (z. B. eine Recipe)."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


class _FileBackedCache:
    """Gemeinsame Basis: Werte als JSON-Dateien in einem Tier-Unterordner ablegen."""

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
    """Tier 1: Query-Spezifikationen ("Recipes"). Klein, immer gecacht."""

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
    """

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir, "materialized")


class RawDataCache:
    """Tier 3: Rohdaten. Nur transient — nach Verarbeitung löschen."""

    def __init__(self, cache_dir: Path) -> None:
        self.dir = cache_dir / "raw"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        """Liefert (und legt bei Bedarf an) das Arbeitsverzeichnis für einen Rohdaten-Schlüssel."""
        path = self.dir / key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def purge(self, key: str) -> None:
        """Löscht die transienten Rohdaten für einen Schlüssel wieder (Tier 3 ist nicht dauerhaft)."""
        path = self.dir / key
        if path.exists():
            shutil.rmtree(path)


class WrapperCache:
    """Bündelt alle drei Tiers hinter einem Zugriffspunkt je Wrapper-Instanz."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        base = Path(cache_dir or os.environ.get("DATABRIDGE_CACHE_DIR", ".cache/databridge"))
        self.recipes = RecipeCache(base)
        self.materialized = MaterializedCache(base)
        self.raw = RawDataCache(base)
