#!/usr/bin/env python3
"""Pancancer-Expressions-`.h5ad` live über den Mediator abrufen und für MP-Lite
ablegen (Aufgabe 10).

    python scripts/fetch_pancancer_h5ad.py --size 160
    python scripts/fetch_pancancer_h5ad.py --balanced --per-cohort-size 5

Ablauf (Phase 1, Default — EIN Aufruf):
    1. POST <mediator>/export/anndata  mit project_id = Liste aller TCGA-Kohorten,
       size, compute_tsne=true  (Pablos Endpoint baut X/obs/var + globale tSNE).
    2. GET  <mediator><download_url>   -> Datei nach --out (Default
       wissensnetz/data/pancancer.h5ad) schreiben.
MP-Lite (Aufgabe 9/10) bevorzugt eine vorhandene ``pancancer.h5ad`` automatisch —
nach dem Abruf einfach ``bokeh serve`` neu laden.

Phase 2 (``--balanced``, optional — gleichmäßige Kohorten, Oviedo-treu):
    pro Projekt ein Aufruf mit ``compute_tsne=false`` und fixierten ``gene_ids``
    (aus dem ersten Kohorten-Ergebnis), jedes Teil-`.h5ad` herunterladen, mit
    ``anndata.concat(join="inner")`` zusammenführen, danach EINE globale 2D-tSNE
    (scikit-learn, hier im Skript) rechnen und als ``obsm["X_tsne_genes"]`` ablegen.
    Kostet mehr Downloads, verteilt die Proben aber gleichmäßig über die Kohorten.

Bewusst ein PROJEKT-Skript (nicht im wissensnetz-Paket): es orchestriert nur den
Mediator per HTTP. ``mediator/``/``wrappers/`` werden NICHT angefasst; das `.h5ad`
wird nur heruntergeladen/gelesen. Konfiguration: --mediator-url oder ENV MEDIATOR_URL
(Default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

from wissensnetz.cohorts import COHORT_PROJECT_IDS

DEFAULT_OUT = "wissensnetz/data/pancancer.h5ad"
SIZE_MAX = 200  # harte Obergrenze des Endpoints (AnndataExportRequest.size)

# Default-Ablageort, den MP-Lite automatisch bevorzugt (h5ad_source.pancancer_*).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PANCANCER_DEFAULT = (_REPO_ROOT / "wissensnetz" / "data" / "pancancer.h5ad").resolve()


class ExportError(RuntimeError):
    """Fehler beim Export/Download — trägt eine benutzerlesbare Meldung."""


def _err(*args: object) -> None:
    print(*args, file=sys.stderr)


def _http_detail(resp: requests.Response) -> str:
    """``detail`` aus einer FastAPI-Fehlerantwort ziehen (JSON-Dict/-String oder Text)."""
    try:
        data = resp.json()
    except ValueError:
        return resp.text.strip() or "(kein Body)"
    if isinstance(data, dict):
        return str(data.get("detail", data))
    return str(data)


def _post_export(base: str, *, project_id, size: int, strategy: str, data_type: str,
                 compute_tsne: bool, gene_ids: list[str] | None = None,
                 timeout: int = 1800) -> dict:
    """``POST /export/anndata`` und Antwort-Metadaten (Dict) zurückgeben.

    Bei non-2xx eine ``ExportError`` mit Statuscode + ``detail`` (bei 503 mit
    explizitem Hinweis auf ``gdc-client``/Fuseki, wie im Endpoint-Detail)."""
    body: dict = {
        "project_id": project_id,
        "experimental_strategy": strategy,
        "data_type": data_type,
        "size": size,
        "compute_tsne": compute_tsne,
    }
    if gene_ids is not None:
        body["gene_ids"] = gene_ids
    try:
        resp = requests.post(f"{base}/export/anndata", json=body, timeout=timeout)
    except requests.RequestException as exc:
        raise ExportError(f"Mediator nicht erreichbar: {exc}") from exc
    if not resp.ok:
        msg = f"HTTP {resp.status_code}: {_http_detail(resp)}"
        if resp.status_code == 503:
            msg += ("\n  → 503 heißt hier meist: `gdc-client` fehlt im Mediator-Container "
                    "ODER Fuseki ist nicht erreichbar/gefüllt (siehe RUNBOOK).")
        raise ExportError(msg)
    try:
        return resp.json()
    except ValueError as exc:
        raise ExportError("ungültige JSON-Antwort vom Mediator") from exc


def _download(base: str, download_url: str, out_path: Path, *, timeout: int = 900) -> Path:
    """Datei über ``GET {base}{download_url}`` streamen und nach ``out_path`` schreiben.

    Bewusst über den Download-Endpoint (nicht ``path`` aus der Antwort direkt lesen)
    — der vereinbarte Übergabeweg (HANDOFF_anndata.md, Offener Punkt 4)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(f"{base}{download_url}", stream=True, timeout=timeout) as r:
            if not r.ok:
                raise ExportError(f"Download HTTP {r.status_code}: {_http_detail(r)}")
            with open(out_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
    except requests.RequestException as exc:
        raise ExportError(f"Download fehlgeschlagen: {exc}") from exc
    return out_path


def _resolve_projects(projects_arg: str | None) -> list[str]:
    """Zielprojekte: ``--projects`` (Komma-Liste) oder alle Oviedo-Kohorten."""
    if projects_arg:
        return [p.strip() for p in projects_arg.split(",") if p.strip()]
    return list(COHORT_PROJECT_IDS)


# --------------------------------------------------------------------------
# Phase 2: balancierter Pancancer-Merge (pro Kohorte ein Abruf, globale tSNE)
# --------------------------------------------------------------------------
def _run_balanced(base: str, projects: list[str], *, per_cohort_size: int,
                  strategy: str, data_type: str, out_path: Path) -> dict:
    try:
        import numpy as np
        import anndata as ad
    except Exception as exc:  # noqa: BLE001
        raise ExportError(f"--balanced braucht 'anndata'/'numpy': {exc}") from exc
    try:
        from sklearn.manifold import TSNE
    except Exception as exc:  # noqa: BLE001
        raise ExportError(f"--balanced braucht 'scikit-learn': {exc}") from exc

    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="pancancer_"))
    parts: list = []
    gene_ids: list[str] | None = None  # nach der ersten Kohorte fixiert -> gleiche var-Achse
    skipped: list[tuple[str, str]] = []

    print(f"Balancierter Modus: {len(projects)} Kohorte(n) × size={per_cohort_size} "
          f"(compute_tsne=false, gene_ids nach erster Kohorte fixiert)")
    for proj in projects:
        print(f"  · {proj} …", end=" ", flush=True)
        try:
            meta = _post_export(base, project_id=proj, size=per_cohort_size,
                                strategy=strategy, data_type=data_type,
                                compute_tsne=False, gene_ids=gene_ids)
            f = _download(base, meta["download_url"], tmpdir / meta["filename"])
        except ExportError as exc:
            reason = "; ".join(l.strip() for l in str(exc).splitlines() if l.strip())
            skipped.append((proj, reason))
            print(f"übersprungen — {reason}")
            continue
        a = ad.read_h5ad(f)
        if gene_ids is None and a.n_vars:
            gene_ids = [str(x) for x in a.var.index]  # var-Achse für die restlichen Kohorten fixieren
        parts.append(a)
        print(f"OK ({a.n_obs} Proben, {a.n_vars} Gene)")

    if not parts:
        raise ExportError("Keine Kohorte erfolgreich geladen — Abbruch.")

    combined = ad.concat(parts, join="inner")
    X = combined.X
    X = X.toarray() if hasattr(X, "toarray") else np.asarray(X)
    n = int(X.shape[0])
    if n > 3:
        perplexity = min(30.0, max(5.0, (n - 1) / 3.0))
        print(f"Globale tSNE über {n} Proben (perplexity={perplexity:.0f}) …")
        tsne = TSNE(n_components=2, perplexity=perplexity, init="pca", random_state=42)
        combined.obsm["X_tsne_genes"] = tsne.fit_transform(X)
    else:
        print(f"  (nur {n} Proben — tSNE übersprungen, wie im Mediator bei ≤3)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.write_h5ad(out_path)
    if skipped:
        print(f"Übersprungen: {len(skipped)} Kohorte(n) — "
              + ", ".join(f"{p} ({m})" for p, m in skipped))
    return {
        "n_obs": int(combined.n_obs),
        "n_vars": int(combined.n_vars),
        "obsm_keys": list(combined.obsm.keys()),
    }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def _report(out_path: Path, meta: dict) -> None:
    print("\n=== Pancancer-`.h5ad` erstellt ===")
    print(f"Datei:      {out_path}")
    print(f"n_obs:      {meta.get('n_obs')}   ·   n_vars: {meta.get('n_vars')}")
    print(f"obsm_keys:  {meta.get('obsm_keys')}")

    # Kohorten-Aufschlüsselung aus der Datei (braucht anndata; sonst überspringen).
    try:
        import anndata as ad

        a = ad.read_h5ad(out_path)
        for col in ("cancer", "project_id"):
            if col in a.obs.columns:
                vc = a.obs[col].value_counts()
                print(f"Kohorten (obs['{col}'], {len(vc)}): "
                      + ", ".join(f"{k}={int(v)}" for k, v in vc.items()))
                break
    except Exception as exc:  # noqa: BLE001 (nur Report — Fehler nicht fatal)
        print(f"(Kohorten-Aufschlüsselung übersprungen: {exc})")

    # Hinweis, wie MP-Lite die Datei findet.
    if out_path.resolve() == _PANCANCER_DEFAULT:
        print("\nMP-Lite erkennt diese Datei automatisch (Default-Pfad) — kein ENV nötig.")
        print("Nur `bokeh serve --show wissensnetz/prototype/mp_lite/app.py` neu laden.")
    else:
        print("\nDamit MP-Lite diese Datei nutzt, DATABRIDGE_H5AD setzen (PowerShell):")
        print(f'  $env:DATABRIDGE_H5AD = "{out_path.resolve()}"')


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Pancancer-Expressions-.h5ad über den Mediator-Export abrufen "
                    "und für MP-Lite ablegen (Aufgabe 10).",
    )
    p.add_argument("--mediator-url", default=os.environ.get("MEDIATOR_URL", "http://localhost:8000"),
                   help="Basis-URL des Mediators (Default: ENV MEDIATOR_URL / http://localhost:8000)")
    p.add_argument("--out", default=DEFAULT_OUT,
                   help=f"Zieldatei (Default: {DEFAULT_OUT})")
    p.add_argument("--size", type=int, default=160,
                   help=f"Anzahl Expressions-Dateien (~Proben), 1..{SIZE_MAX} (Default: 160)")
    p.add_argument("--projects", default=None,
                   help="Komma-Liste von project_ids (Default: alle Oviedo-Kohorten)")
    p.add_argument("--strategy", default="RNA-Seq",
                   help="experimental_strategy (Default: RNA-Seq)")
    p.add_argument("--data-type", default="Gene Expression Quantification",
                   help="data_type (Default: Gene Expression Quantification)")
    p.add_argument("--balanced", action="store_true",
                   help="pro Kohorte ein Aufruf + globale tSNE im Skript (gleichmäßig, mehr Downloads)")
    p.add_argument("--per-cohort-size", type=int, default=5,
                   help="Proben pro Kohorte im --balanced-Modus (Default: 5)")
    args = p.parse_args(argv)

    base = args.mediator_url.rstrip("/")
    out_path = Path(args.out)
    projects = _resolve_projects(args.projects)

    # size-Grenzen prüfen (Endpoint erzwingt 1..200; hier vorab klar melden).
    size_to_check = args.per_cohort_size if args.balanced else args.size
    if not (1 <= size_to_check <= SIZE_MAX):
        _err(f"Fehler: size muss zwischen 1 und {SIZE_MAX} liegen (war {size_to_check}).")
        return 2

    # Mediator erreichbar?
    try:
        requests.get(f"{base}/health", timeout=10).raise_for_status()
    except requests.RequestException:
        _err(f"Mediator nicht erreichbar unter {base}.")
        _err("Zuerst starten:  cd mediator  &&  uvicorn app.main:app --port 8000")
        _err("(Für echte Downloads braucht der Container `gdc-client` + gefülltes Fuseki.)")
        return 1

    try:
        if args.balanced:
            meta = _run_balanced(base, projects, per_cohort_size=args.per_cohort_size,
                                 strategy=args.strategy, data_type=args.data_type,
                                 out_path=out_path)
        else:
            print(f"Export: {len(projects)} Kohorte(n) in EINEM Aufruf (size={args.size}, "
                  f"compute_tsne=true) über {base}/export/anndata …")
            meta = _post_export(base, project_id=projects, size=args.size,
                                strategy=args.strategy, data_type=args.data_type,
                                compute_tsne=True)
            _download(base, meta["download_url"], out_path)
    except ExportError as exc:
        _err(f"\nAbbruch: {exc}")
        return 1

    _report(out_path, meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
