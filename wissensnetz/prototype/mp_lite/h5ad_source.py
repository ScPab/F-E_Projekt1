"""Lesezugriff auf das Expressions-``.h5ad`` (anndata) für MP-lite (Aufgabe 9).

Das ``.h5ad`` ist ein **Mediator-Artefakt** (``mediator/app/semantic/expression.py``
erzeugt es): eine Expressionsmatrix ``X`` (Proben × Gene, TPM) samt klinischer
``obs``-Metadaten (die volle Oviedo-Feldliste), ``var``-Gensymbolen und
vorberechneten 2D-Layouts in ``obsm`` (tSNE der Gen-/miRNA-Profile). MP-lite liest
daraus — **nur lesen**, nie schreiben; das Modul fasst weder ``mediator/`` noch
``wrappers/`` an, es öffnet lediglich die fertige Datei.

Alle Zugriffe sind **defensiv**: fehlt das Paket ``anndata`` oder die Datei, liefern
die Funktionen ``None``/leer, damit die App sauber auf den Graph-/Synthetik-Pfad
zurückfällt (kein harter Crash — siehe ``app.py`` Datenquellen-Priorität).

Pfad-Auflösung (in dieser Reihenfolge):
1. explizites ``path``-Argument,
2. ENV ``DATABRIDGE_H5AD``,
3. Default: das Referenz-``.h5ad`` unter
   ``<repo>/mediator/sample_data/tcga_brca_sample.h5ad``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # anndata ist eine optionale Prototyp-Abhängigkeit (siehe README/pyproject).
    import anndata as _ad
except Exception:  # noqa: BLE001 (fehlt anndata -> sauberer Fallback, kein Crash)
    _ad = None

try:
    import numpy as _np
except Exception:  # noqa: BLE001 (numpy kommt mit bokeh/anndata; ohne -> None)
    _np = None

# ENV-Variable, mit der ein alternatives ``.h5ad`` (z. B. Pancancer-Export)
# vorgegeben werden kann, ohne Code zu ändern.
ENV_VAR = "DATABRIDGE_H5AD"

# Default-Pfad relativ zum Repo-Wurzelverzeichnis. Diese Datei liegt unter
# ``<repo>/wissensnetz/prototype/mp_lite/h5ad_source.py`` -> parents[3] == <repo>.
_DEFAULT_REL = ("mediator", "sample_data", "tcga_brca_sample.h5ad")

# Oviedo-``obs``-Spalten, die MP-lite für Hover/Färbung erwartet (Reihenfolge egal;
# fehlende Spalten werden zu ``None``). ``submitter_id`` = Case-Barcode (Rückkanal-
# und Kontext-Schlüssel), ``cancer`` = Kohorten-Code (Färbung/Legende).
_OBS_FIELDS = (
    "sample_type", "submitter_id", "project_id", "race", "gender", "ethnicity",
    "vital_status", "tumor_stage", "morphology", "site_of_resection_or_biopsy",
    "has_metastasis", "primary_diagnosis", "age_at_diagnosis", "cancer",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_h5ad_path() -> Path:
    """Referenz-``.h5ad`` unter ``<repo>/mediator/sample_data/tcga_brca_sample.h5ad``."""
    return _repo_root().joinpath(*_DEFAULT_REL)


def resolve_h5ad_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Pfad auflösen: explizites ``path`` > ENV ``DATABRIDGE_H5AD`` > Default."""
    if path:
        return Path(path)
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env)
    return default_h5ad_path()


def load_h5ad(path: str | os.PathLike[str] | None = None) -> Any | None:
    """``AnnData`` laden oder ``None`` (fehlendes ``anndata``, fehlende/kaputte Datei).

    Bewusst tolerant: jeder Fehler führt zu ``None`` statt zu einer Exception, damit
    die aufrufende App auf den nächsten Datenquellen-Pfad zurückfallen kann.
    """
    if _ad is None:
        return None
    p = resolve_h5ad_path(path)
    if not p.exists():
        return None
    try:
        return _ad.read_h5ad(p)
    except Exception:  # noqa: BLE001 (kaputte/inkompatible Datei -> Fallback)
        return None


def _isna(v: object) -> bool:
    """``True`` für ``None``/NaN/pandas-``NA`` — sonst ``False`` (robust ohne harte
    pandas-Abhängigkeit)."""
    if v is None:
        return True
    try:  # pandas ist mit anndata da; NaN/NA sauber erkennen.
        import pandas as pd

        return bool(pd.isna(v))
    except Exception:  # noqa: BLE001
        return isinstance(v, float) and v != v  # NaN != NaN


def _clean(v: object) -> object | None:
    """Rohwert -> Python-Wert oder ``None`` (fehlend). numpy-Skalare -> Python."""
    if _isna(v):
        return None
    if _np is not None and isinstance(v, _np.generic):
        return v.item()
    return v


def points_from_obs(adata: Any) -> list[dict]:
    """Eine Zeile je Sample aus ``obs`` — mit den Oviedo-Hover-Feldern, ``cancer``
    und ``tumor`` (= ``submitter_id``, Case-Barcode; Fallback: ``obs``-Index).

    Rückgabe: Liste von Dicts in ``obs``-Reihenfolge. Fehlende Werte sind ``None``.
    Jede Zeile enthält zusätzlich ``sample_id`` (den ``obs``-Index).
    """
    obs = adata.obs
    cols = set(obs.columns)
    rows: list[dict] = []
    for sample_id, row in obs.iterrows():
        rec: dict[str, object | None] = {"sample_id": str(sample_id)}
        for col in _OBS_FIELDS:
            rec[col] = _clean(row[col]) if col in cols else None
        submitter = rec.get("submitter_id")
        rec["tumor"] = submitter if submitter not in (None, "") else str(sample_id)
        rows.append(rec)
    return rows


def marker_column(adata: Any, symbol: str) -> Any | None:
    """Expressionsspalte eines Gensymbols aus ``X`` — per ``var["symbol"]``-Lookup.

    Rückgabe: 1D-``float``-``np.ndarray`` (Länge = Anzahl Proben) oder ``None``, wenn
    das Symbol nicht in ``var`` vorkommt (bzw. ``numpy``/``var["symbol"]`` fehlt).
    """
    if _np is None:
        return None
    var = adata.var
    if "symbol" not in var.columns:
        return None
    mask = (var["symbol"].astype(str).to_numpy() == str(symbol))
    if not mask.any():
        return None
    idx = int(_np.flatnonzero(mask)[0])
    col = adata.X[:, idx]
    try:  # sparse-Matrix -> dichtes 1D-Array
        col = col.toarray()
    except Exception:  # noqa: BLE001 (schon dicht)
        pass
    return _np.asarray(col, dtype=float).ravel()


def layout(adata: Any, key: str) -> Any | None:
    """Vorberechnetes 2D-Layout aus ``obsm[key]`` (z. B. ``"X_tsne_genes"``).

    Rückgabe: ``(n, 2)``-``float``-``np.ndarray`` oder ``None``, wenn der Key fehlt
    oder das Array nicht mindestens zweidimensional ist.
    """
    if _np is None:
        return None
    if key not in adata.obsm:
        return None
    arr = _np.asarray(adata.obsm[key], dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        return None
    return arr[:, :2]
