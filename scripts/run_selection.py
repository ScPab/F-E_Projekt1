#!/usr/bin/env python3
"""Hilfsskript: eine Auswahl (selection.json) durch den Mediator schicken und
das Ergebnis im Wissensnetz anzeigen — die Kette ohne Oberfläche.

    python scripts/run_selection.py selection.json
    python scripts/run_selection.py selection.json --generate

Ablauf:
    1. POST <mediator>/selection/preview  bzw.  /selection/generate
       (UI-Auswahl -> Abruf -> Übersetzung -> Laden; Kollege B)
    2. `wissensnetz selection <recipe_key>` je Ebene (Wissensnetz)

Bewusst ein PROJEKT-Skript (nicht im wissensnetz-Paket), Muster wie
scripts/load_gdc.py: das Paket bleibt „nur graph-db", dieses Skript
orchestriert Mediator (HTTP) + Wissensnetz. Kein GDC-Zugriff.

Voraussetzung für Schritt 2 ist, dass der Mediator das Manifest schreibt
(``wissensnetz.selection.write_selection``, siehe
wissensnetz/HANDOFF_pablo_store_waechst.md, P1/P2). Solange das noch nicht
umgesetzt ist, meldet das Skript „keine Auswahl im Store" und zeigt nur die
Antwort des Mediators — das ist der erwartete Zwischenstand, kein Fehler des
Wissensnetzes.

Konfiguration: --mediator-url oder ENV MEDIATOR_URL (Default http://localhost:8000);
Fuseki-Verbindung wie im Paket (ENV GRAPH_DB_URL/GRAPH_DB_DATASET, siehe .env.example).

Format der selection.json (= mediator/app/schemas.py::SelectionRequest):

    {
      "levels": [
        {"source": "gdc", "cohorts": ["TCGA-BRCA"],
         "modality": "gene_expression", "attributes": ["gender", "tumor_stage"]}
      ],
      "size": 20
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

from wissensnetz import GraphStore
from wissensnetz.cli import main as wissensnetz_cli
from wissensnetz.selection import list_selections, selection_exists


def _post_selection(base: str, payload: dict, *, generate: bool, timeout: float) -> dict | None:
    """Die Auswahl an den Mediator schicken. ``None`` bei einem HTTP-Fehler."""
    endpoint = "/selection/generate" if generate else "/selection/preview"
    try:
        resp = requests.post(f"{base}{endpoint}", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        print(f"{endpoint} fehlgeschlagen: {exc}", file=sys.stderr)
        return None
    except ValueError:
        print(f"{endpoint}: ungültige JSON-Antwort vom Mediator", file=sys.stderr)
        return None


def _print_level(level: dict) -> str | None:
    """Eine Ebene der Mediator-Antwort ausgeben; gibt den recipe_key zurück."""
    sel = level.get("selection") or {}
    key = level.get("recipe_key")
    status = level.get("status", "?")
    cohorts = ", ".join(sel.get("cohorts") or []) or "—"
    print(f"\n=== Ebene {cohorts} / {sel.get('modality') or '—'} ===")
    print(f"recipe_key:  {key or '—'}")
    print(f"Status:      {status}"
          + (f"  ({level['error']})" if level.get("error") else ""))
    if level.get("failed_cohorts"):
        print(f"Fehlerhafte Kohorten: {', '.join(level['failed_cohorts'])}")
    print(f"Tripel:      {level.get('triple_count') if level.get('triple_count') is not None else '—'}")
    anndata = level.get("anndata") or {}
    if anndata:
        print(f"anndata:     n_obs={anndata.get('n_obs')} n_vars={anndata.get('n_vars')} "
              f"{anndata.get('download_url') or ''}")
    return key if status == "ok" else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Eine Auswahl (selection.json) über den Mediator laufen lassen "
                    "und die entstandene Auswahl im Wissensnetz anzeigen."
    )
    p.add_argument("selection", help="Pfad zu einer selection.json (SelectionRequest)")
    p.add_argument("--generate", action="store_true",
                   help="POST /selection/generate statt /selection/preview (teuer: mit .h5ad)")
    p.add_argument("--mediator-url", default=os.environ.get("MEDIATOR_URL", "http://localhost:8000"),
                   help="Basis-URL des Mediators (Default: http://localhost:8000)")
    p.add_argument("--timeout", type=float, default=600.0,
                   help="HTTP-Timeout in Sekunden (Default: 600 — /selection/generate lädt herunter)")
    args = p.parse_args(argv)

    path = Path(args.selection)
    if not path.exists():
        print(f"Auswahl-Datei nicht gefunden: {path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{path} ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 1

    base = args.mediator_url.rstrip("/")

    # 1) Mediator erreichbar?
    try:
        requests.get(f"{base}/health", timeout=10).raise_for_status()
    except requests.RequestException:
        print(f"Mediator nicht erreichbar unter {base}.", file=sys.stderr)
        print("Zuerst starten:  cd mediator  &&  uvicorn app.main:app --port 8000", file=sys.stderr)
        return 1

    # 2) Fuseki erreichbar?
    store = GraphStore()
    if not store.is_reachable():
        print(f"Fuseki nicht erreichbar unter {store.settings.base_url}.", file=sys.stderr)
        print("Zuerst starten:  docker compose up -d graph-db  &&  wissensnetz init", file=sys.stderr)
        return 1

    mode = "generate" if args.generate else "preview"
    print(f"Schicke {path} an {base}/selection/{mode} …")
    data = _post_selection(base, payload, generate=args.generate, timeout=args.timeout)
    if data is None:
        return 1

    levels = data.get("levels") or []
    if not levels:
        print("Der Mediator hat keine Ebenen zurückgegeben.", file=sys.stderr)
        return 1

    keys = [k for k in (_print_level(level) for level in levels) if k]

    # 3) Ergebnis im Wissensnetz — dieselbe Ausgabe wie `wissensnetz selection <id>`.
    known = {e.get("selection_id") for e in list_selections(store)}
    for key in keys:
        print(f"\n--- wissensnetz selection {key} ---")
        if key not in known and not selection_exists(store, key):
            print("(keine Auswahl im Store — schreibt der Mediator das Manifest schon? "
                  "siehe wissensnetz/HANDOFF_pablo_store_waechst.md, P1/P2)")
            continue
        wissensnetz_cli(["selection", key])  # öffentlicher CLI-Einstieg

    return 0 if keys else 1


if __name__ == "__main__":
    raise SystemExit(main())
