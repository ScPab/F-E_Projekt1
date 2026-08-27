#!/usr/bin/env python3
"""Hilfsskript: echte GDC/TCGA-Fälle über den Mediator abrufen und ins
Wissensnetz (Fuseki) laden — ein Befehl statt PowerShell-Einzeiler.

    python scripts/load_gdc.py --project TCGA-BRCA --size 50

Ablauf:
    1. POST <mediator>/transform  (GDC-JSON -> RDF/Turtle; Kollege B)
    2. graphstore.load_turtle()   (Turtle -> Fuseki; Wissensnetz)

Bewusst ein PROJEKT-Skript (nicht im wissensnetz-Paket): das Paket bleibt
„nur graph-db", dieses Skript orchestriert Mediator (HTTP) + Wissensnetz.
Konfiguration: --mediator-url oder ENV MEDIATOR_URL (Default http://localhost:8000);
Fuseki-Verbindung wie im Paket (ENV GRAPH_DB_URL/GRAPH_DB_DATASET, siehe .env.example).
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

from wissensnetz import GraphStore
from wissensnetz.cohorts import COHORT_PROJECT_IDS

DB = "http://databridge.hka/onto#"


def _load_one(base: str, store: GraphStore, project: str, *, size: int,
              access: str, graph: str | None) -> tuple[bool, int, str]:
    """Ein Projekt über ``<mediator>/transform`` holen und in Fuseki laden.

    Rückgabe ``(ok, triple_count, message)``. Wirft **nicht** — Fehler werden als
    ``(False, 0, grund)`` zurückgegeben, damit der Pancancer-Loop weiterlaufen kann.
    """
    body = {"source": "gdc", "project_id": project, "access": access, "size": size}
    try:
        resp = requests.post(f"{base}/transform", json=body, timeout=180)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return False, 0, f"Transform-Fehler: {exc}"

    try:
        data = resp.json()
    except ValueError:
        return False, 0, "ungültige JSON-Antwort vom Mediator"
    turtle = data.get("turtle", "") or ""
    triple_count = data.get("triple_count", 0)
    if not turtle.strip() or not triple_count:
        return False, 0, "leeres Ergebnis (keine Tripel)"

    try:
        store.load_turtle(turtle, graph=graph)
    except Exception as exc:  # noqa: BLE001 (Loader: einzelnes Projekt darf scheitern)
        return False, 0, f"Load-Fehler: {exc}"
    return True, int(triple_count), "ok"


def _resolve_projects(args: argparse.Namespace) -> list[str]:
    """Zielprojekte aus den (sich ausschließenden) CLI-Optionen bestimmen."""
    if args.pancancer:
        return list(COHORT_PROJECT_IDS)
    if args.projects:
        return [p.strip() for p in args.projects.split(",") if p.strip()]
    return [args.project]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="GDC/TCGA-Fälle über den Mediator ins Wissensnetz laden "
                    "(Einzelprojekt oder alle Oviedo-Kohorten)."
    )
    p.add_argument("--project", default="TCGA-BRCA", help="GDC project_id (Default: TCGA-BRCA)")
    p.add_argument("--projects", default=None,
                   help="explizite Liste, kommagetrennt (z. B. TCGA-ACC,TCGA-BRCA)")
    p.add_argument("--pancancer", action="store_true",
                   help="alle 32 Oviedo-Kohorten laden (OVIEDO_COHORTS)")
    p.add_argument("--size", type=int, default=50,
                   help="Anzahl Fälle PRO Projekt (Default: 50)")
    p.add_argument("--access", default="open", help="Access-Level (Default: open)")
    p.add_argument("--mediator-url", default=os.environ.get("MEDIATOR_URL", "http://localhost:8000"),
                   help="Basis-URL des Mediators (Default: http://localhost:8000)")
    p.add_argument("--graph", default=None, help="optionaler Named Graph (Default: Default-Graph)")
    args = p.parse_args(argv)

    base = args.mediator_url.rstrip("/")
    projects = _resolve_projects(args)

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

    where = f"Named Graph <{args.graph}>" if args.graph else "Default-Graph"
    print(f"Lade {len(projects)} Projekt(e) (size={args.size} je Projekt) → {where} "
          f"über {base}/transform …")

    # 3) Projekt für Projekt laden — robust: Fehler eines Projekts stoppen NICHT.
    loaded: list[tuple[str, int]] = []
    skipped: list[tuple[str, str]] = []
    for project in projects:
        print(f"  · {project} …", end=" ", flush=True)
        ok, triples, msg = _load_one(base, store, project, size=args.size,
                                     access=args.access, graph=args.graph)
        if ok:
            loaded.append((project, triples))
            print(f"OK ({triples} Tripel)")
        else:
            skipped.append((project, msg))
            print(f"übersprungen — {msg}", file=sys.stderr)

    # 4) Zusammenfassung
    print("\n=== Zusammenfassung ===")
    print(f"Geladen:      {len(loaded)}/{len(projects)}"
          + (f"  ({sum(t for _, t in loaded)} Tripel gesamt)" if loaded else ""))
    if skipped:
        print(f"Übersprungen: {len(skipped)}")
        for project, msg in skipped:
            print(f"    - {project}: {msg}")

    rows = store.query(f"PREFIX db: <{DB}> SELECT (COUNT(?c) AS ?n) WHERE {{ ?c a db:Case }}")
    if rows:
        print(f"Cases im Store gesamt: {rows[0].get('n')}")

    # Erfolg, sobald mindestens ein Projekt geladen wurde.
    return 0 if loaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
