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

DB = "http://databridge.hka/onto#"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="GDC/TCGA-Fälle über den Mediator ins Wissensnetz laden."
    )
    p.add_argument("--project", default="TCGA-BRCA", help="GDC project_id (Default: TCGA-BRCA)")
    p.add_argument("--size", type=int, default=50, help="Anzahl Fälle (Default: 50)")
    p.add_argument("--access", default="open", help="Access-Level (Default: open)")
    p.add_argument("--mediator-url", default=os.environ.get("MEDIATOR_URL", "http://localhost:8000"),
                   help="Basis-URL des Mediators (Default: http://localhost:8000)")
    p.add_argument("--graph", default=None, help="optionaler Named Graph (Default: Default-Graph)")
    args = p.parse_args(argv)

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

    # 3) Transform anfragen (GDC -> Turtle)
    body = {"source": "gdc", "project_id": args.project, "access": args.access, "size": args.size}
    print(f"Abruf {args.project} (size={args.size}) über {base}/transform …")
    try:
        resp = requests.post(f"{base}/transform", json=body, timeout=180)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Transform fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    data = resp.json()
    turtle = data.get("turtle", "") or ""
    triple_count = data.get("triple_count", 0)
    if not turtle.strip() or not triple_count:
        print("Keine Tripel erhalten (leeres Ergebnis) — Projekt/Filter prüfen.", file=sys.stderr)
        return 1

    # 4) In Fuseki laden
    store.load_turtle(turtle, graph=args.graph)
    where = f"Named Graph <{args.graph}>" if args.graph else "Default-Graph"
    print(f"OK: {triple_count} Tripel für {args.project} in {where} geladen "
          f"(Dataset '{store.settings.dataset}').")

    # 5) Kleine Kontrolle
    rows = store.query(f"PREFIX db: <{DB}> SELECT (COUNT(?c) AS ?n) WHERE {{ ?c a db:Case }}")
    if rows:
        print(f"Cases im Store gesamt: {rows[0].get('n')}")
    print("Tipp:  wissensnetz query \"SELECT ?sid WHERE { ?c a db:Case ; "
          "db:submitterId ?sid } LIMIT 5\"   dann:  wissensnetz context <submitterId>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
