#!/usr/bin/env python3
"""Ein erzeugtes `.h5ad` inhaltlich pruefen — nicht nur "laesst es sich oeffnen".

    python scripts/check_h5ad.py                      # neueste .h5ad im Projekt
    python scripts/check_h5ad.py pfad/zur/datei.h5ad
    python scripts/check_h5ad.py datei.h5ad --strict  # Warnungen zaehlen als Fehler

Gedacht als Kontrolle nach jedem `Generieren` (Oberflaeche, `run_selection.py
--generate` oder `/export/anndata`): welche `obs`-Klinikfelder sind tatsaechlich
angekommen, ist die Matrix brauchbar, gibt es die tSNE-Einbettung?

Warum nicht einfach ein HDF5-Viewer: der zeigt, dass eine Spalte **existiert**,
nicht ob sie **Werte** enthaelt. Genau dort sitzen die bekannten Luecken
(Klinikfelder aus dem Store, siehe wissensnetz/Tasks Archiv/
HANDOFF_pablo_store_waechst.md, P3).

Bewusst ein PROJEKT-Skript (nicht im wissensnetz-Paket): es liest nur eine
Datei, spricht weder mit dem Mediator noch mit Fuseki. `anndata` ist eine
Prototyp-/Mediator-Abhaengigkeit, das Kernpaket bleibt anndata-frei
(wissensnetz/CLAUDE.md).

Rueckgabewert: 0 = in Ordnung, 1 = harter Fehler (unlesbar, NaN/Inf in X,
doppelte Schluessel, leere Achse). Mit `--strict` fuehren auch Warnungen
(leere obs-Spalten, fehlende Einbettung, leere Zeilen) zu 1 — brauchbar, um in
einem Skript abzubrechen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Projekt-Wurzel: diese Datei liegt unter <repo>/scripts/.
_REPO_ROOT = Path(__file__).resolve().parents[1]

# Spalten, die MP-Lite fuer Hover und Faerbung erwartet (Oviedo-Feldliste,
# siehe wissensnetz/prototype/mp_lite/h5ad_source.py::_OBS_FIELDS). Fehlen sie
# ganz, ist das ein anderer Fall als "vorhanden, aber leer" — deshalb getrennt
# gemeldet.
_ERWARTETE_OBS = (
    "sample_type", "submitter_id", "project_id", "race", "sex_at_birth", "ethnicity",
    "vital_status", "tumor_stage", "morphology", "site_of_resection_or_biopsy",
    "has_metastasis", "primary_diagnosis", "age_at_diagnosis", "cancer",
)

# Einbettung, aus der MP-Lite die Genexpressions-Karte zeichnet.
_TSNE_KEY = "X_tsne_genes"

# Werte, die pandas beim Lesen fuer "nicht gesetzt" liefern kann.
_LEER = {"", "nan", "None", "<NA>", "NaN"}


def _err(*args: object) -> None:
    print(*args, file=sys.stderr)


def find_latest(root: Path) -> Path | None:
    """Neueste `.h5ad` unterhalb von ``root`` (nach Aenderungszeit)."""
    dateien = [p for p in root.rglob("*.h5ad") if p.is_file()]
    if not dateien:
        return None
    return max(dateien, key=lambda p: p.stat().st_mtime)


def _fill_state(series) -> tuple[int, list[str]]:
    """``(gefuellte Werte, bis zu drei Beispiele)`` einer obs-Spalte."""
    werte = [str(v) for v in series.tolist()]
    gefuellt = [v for v in werte if v not in _LEER]
    return len(gefuellt), gefuellt[:3]


def check(path: Path) -> tuple[list[str], list[str]]:
    """Datei pruefen und berichten. Gibt ``(fehler, warnungen)`` zurueck."""
    import anndata as ad
    import numpy as np

    fehler: list[str] = []
    warnungen: list[str] = []

    print(f"Datei:  {path}")
    print(f"Groesse: {path.stat().st_size / (1024 * 1024):.2f} MB\n")

    adata = ad.read_h5ad(path)
    print(f"Form:   n_obs={adata.n_obs} (Proben)  x  n_vars={adata.n_vars} (Gene)\n")
    if adata.n_obs == 0:
        fehler.append("keine einzige Probe (n_obs = 0)")
    if adata.n_vars == 0:
        fehler.append("keine einzige Gen-Spalte (n_vars = 0)")

    # --- obs: die eigentliche Frage, welche Klinikfelder ankamen -----------
    print("--- obs (Klinikfelder je Probe) ---")
    leere_spalten: list[str] = []
    for spalte in adata.obs.columns:
        gefuellt, beispiele = _fill_state(adata.obs[spalte])
        marker = "    " if gefuellt else " !  "
        if not gefuellt:
            leere_spalten.append(spalte)
        print(f"{marker}{spalte:32s} {gefuellt:5d}/{adata.n_obs:<5d}  {beispiele}")
    if leere_spalten:
        warnungen.append(f"{len(leere_spalten)} obs-Spalte(n) komplett leer: "
                         + ", ".join(leere_spalten))

    fehlende = [f for f in _ERWARTETE_OBS if f not in adata.obs.columns]
    if fehlende:
        warnungen.append("obs-Spalte(n) fehlen ganz (MP-Lite erwartet sie): "
                         + ", ".join(fehlende))

    # --- Schluessel -------------------------------------------------------
    print("\n--- Schluessel ---")
    print(f"    obs_names: {list(adata.obs_names[:3])}  eindeutig={adata.obs_names.is_unique}")
    print(f"    var_names: {list(adata.var_names[:3])}  eindeutig={adata.var_names.is_unique}")
    print(f"    var-Spalten: {list(adata.var.columns)}")
    if not adata.obs_names.is_unique:
        fehler.append("obs_names sind nicht eindeutig (doppelte Proben)")
    if not adata.var_names.is_unique:
        fehler.append("var_names sind nicht eindeutig (doppelte Gene)")

    # --- X ----------------------------------------------------------------
    print("\n--- X (Matrix) ---")
    X = adata.X
    dicht = X.toarray() if hasattr(X, "toarray") else np.asarray(X)
    n_nan, n_inf = int(np.isnan(dicht).sum()), int(np.isinf(dicht).sum())
    print(f"    Typ:     {type(X).__name__}, dtype={dicht.dtype}, shape={dicht.shape}")
    print(f"    NaN={n_nan}   Inf={n_inf}")
    if dicht.size:
        print(f"    Bereich: min={dicht.min():.4g}  max={dicht.max():.4g}  "
              f"Mittel={dicht.mean():.4g}")
        leere_zeilen = int((dicht.sum(axis=1) == 0).sum())
        print(f"    Proben ohne einen einzigen Wert: {leere_zeilen}")
        if leere_zeilen == adata.n_obs:
            fehler.append("die Matrix ist komplett leer (jede Probe nur Nullen)")
        elif leere_zeilen:
            warnungen.append(f"{leere_zeilen} Probe(n) haben nur Nullen")
    if n_nan:
        fehler.append(f"{n_nan} NaN in X")
    if n_inf:
        fehler.append(f"{n_inf} Inf in X")

    # --- obsm -------------------------------------------------------------
    print("\n--- obsm (Einbettungen) ---")
    if len(adata.obsm):
        for key in adata.obsm:
            arr = np.asarray(adata.obsm[key])
            nan = int(np.isnan(arr).sum())
            print(f"    {key:18s} shape={arr.shape}  NaN={nan}")
            if nan:
                fehler.append(f"{nan} NaN in obsm['{key}']")
    else:
        print("    (keine)")
    if _TSNE_KEY not in adata.obsm:
        warnungen.append(f"'{_TSNE_KEY}' fehlt — MP-Lite kann daraus keine Karte "
                         "zeichnen (compute_tsne=true setzen)")

    print(f"\n--- uns: {list(adata.uns.keys())}   layers: {list(adata.layers.keys())}")
    return fehler, warnungen


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Ein .h5ad inhaltlich pruefen: welche obs-Klinikfelder sind "
                    "gefuellt, ist die Matrix brauchbar, gibt es die tSNE-Einbettung?",
    )
    p.add_argument("datei", nargs="?", default=None,
                   help="Pfad zur .h5ad (Default: die neueste im Projekt)")
    p.add_argument("--strict", action="store_true",
                   help="Warnungen (leere obs-Spalten, fehlende Einbettung) als Fehler werten")
    args = p.parse_args(argv)

    try:
        import anndata  # noqa: F401
    except ImportError:
        _err("anndata ist nicht installiert - Pruefung nicht moeglich.")
        _err("Installieren mit:  pip install anndata   (oder: pip install -r requirements.txt)")
        _err("Ueber Conda oft robuster:  conda install -c conda-forge anndata")
        return 1

    if args.datei:
        path = Path(args.datei)
    else:
        path = find_latest(_REPO_ROOT)
        if path is None:
            _err(f"Keine .h5ad unterhalb von {_REPO_ROOT} gefunden.")
            _err("Erst eine erzeugen:  .\\start_all.ps1 -DemoGenerate")
            return 1
        print("(keine Datei angegeben - nehme die neueste im Projekt)\n")

    if not path.exists():
        _err(f"Datei nicht gefunden: {path}")
        return 1

    try:
        fehler, warnungen = check(path)
    except Exception as exc:  # noqa: BLE001 (jede Lesefehlerart ist hier ein Befund)
        _err(f"\nDatei nicht lesbar: {type(exc).__name__}: {exc}")
        return 1

    print("\n=== Befund ===")
    for f in fehler:
        print(f"  FEHLER:  {f}")
    for w in warnungen:
        print(f"  Hinweis: {w}")
    if not fehler and not warnungen:
        print("  Alles in Ordnung.")
        return 0
    if fehler:
        print(f"\n{len(fehler)} Fehler, {len(warnungen)} Hinweis(e).")
        return 1
    print(f"\nKeine Fehler, {len(warnungen)} Hinweis(e).")
    if args.strict:
        print("(--strict: Hinweise zaehlen als Fehler)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
