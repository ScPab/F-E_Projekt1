#!/usr/bin/env python3
"""Hilfsskript: echte GDC/TCGA-Fälle über den Mediator abrufen und ins
Wissensnetz (Fuseki) laden — ein Befehl statt PowerShell-Einzeiler.

    python scripts/load_gdc.py --project TCGA-BRCA --size 50

Ablauf:
    1. POST <mediator>/transform  (GDC-JSON -> RDF/Turtle; Kollege B)
    2. graphstore.load_turtle()   (Turtle -> Fuseki; Wissensnetz)

ALTWEG (Stand vor ADR-0003): ``--pancancer`` fuellt den Store **global** mit allen
32 Kohorten. Seit ADR-0003 waechst der Store mit den Aufrufen, der regulaere Weg
ist ``scripts/run_selection.py`` (POST /selection/preview). Dieses Skript bleibt
fuer Vergleichsmessungen und den Bericht erhalten.

Bewusst ein PROJEKT-Skript (nicht im wissensnetz-Paket): das Paket bleibt
„nur graph-db", dieses Skript orchestriert Mediator (HTTP) + Wissensnetz.
Konfiguration: --mediator-url oder ENV MEDIATOR_URL (Default http://localhost:8000);
Fuseki-Verbindung wie im Paket (ENV GRAPH_DB_URL/GRAPH_DB_DATASET, siehe .env.example).

English: Helper script: fetch real GDC/TCGA cases via the mediator and
load them into the knowledge graph (Fuseki) — one command instead of
PowerShell one-liners.

    python scripts/load_gdc.py --project TCGA-BRCA --size 50

Flow:
    1. POST <mediator>/transform  (GDC JSON -> RDF/Turtle; colleague B)
    2. graphstore.load_turtle()   (Turtle -> Fuseki; wissensnetz)

OLD PATH (as of before ADR-0003): ``--pancancer`` fills the store
**globally** with all 32 cohorts. Since ADR-0003 the store grows with
each call; the regular path is ``scripts/run_selection.py`` (POST
/selection/preview). This script is kept for comparison measurements
and the report.

Deliberately a PROJECT script (not inside the wissensnetz package): the
package stays "graph-db only", this script orchestrates mediator (HTTP)
+ wissensnetz. Configuration: --mediator-url or ENV MEDIATOR_URL
(default http://localhost:8000); Fuseki connection as in the package
(ENV GRAPH_DB_URL/GRAPH_DB_DATASET, see .env.example).
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

    English: Fetches one project via ``<mediator>/transform`` and loads
    it into Fuseki.

    Returns ``(ok, triple_count, message)``. **Does not raise** — errors
    are returned as ``(False, 0, reason)`` so the pancancer loop can keep
    going.
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
    """Zielprojekte aus den (sich ausschließenden) CLI-Optionen bestimmen.

    English: Determines target projects from the (mutually exclusive)
    CLI options.
    """
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
                   help="ALTWEG (vor ADR-0003): alle 32 Oviedo-Kohorten laden (OVIEDO_COHORTS) "
                        "und damit den Store global fuellen. Regulaer: scripts/run_selection.py")
    p.add_argument("--size", type=int, default=50,
                   help="Anzahl Fälle PRO Projekt (Default: 50)")
    p.add_argument("--access", default="open", help="Access-Level (Default: open)")
    p.add_argument("--mediator-url", default=os.environ.get("MEDIATOR_URL", "http://localhost:8000"),
                   help="Basis-URL des Mediators (Default: http://localhost:8000)")
    p.add_argument("--graph", default=None, help="optionaler Named Graph (Default: Default-Graph)")
    args = p.parse_args(argv)

    base = args.mediator_url.rstrip("/")
    projects = _resolve_projects(args)

    if args.pancancer:
        print("Hinweis: --pancancer fuellt den Store GLOBAL (Stand vor ADR-0003). "
              "Der regulaere Weg ist scripts/run_selection.py (ein Scope je Aufruf).",
              file=sys.stderr)

    # 1) Mediator erreichbar?
    # EN: 1) Mediator reachable?
    try:
        requests.get(f"{base}/health", timeout=10).raise_for_status()
    except requests.RequestException:
        print(f"Mediator nicht erreichbar unter {base}.", file=sys.stderr)
        print("Zuerst starten:  cd mediator  &&  uvicorn app.main:app --port 8000", file=sys.stderr)
        return 1

    # 2) Fuseki erreichbar?
    # EN: 2) Fuseki reachable?
    store = GraphStore()
    if not store.is_reachable():
        print(f"Fuseki nicht erreichbar unter {store.settings.base_url}.", file=sys.stderr)
        print("Zuerst starten:  docker compose up -d graph-db  &&  wissensnetz init", file=sys.stderr)
        return 1

    where = f"Named Graph <{args.graph}>" if args.graph else "Default-Graph"
    print(f"Lade {len(projects)} Projekt(e) (size={args.size} je Projekt) → {where} "
          f"über {base}/transform …")

    # 3) Projekt für Projekt laden — robust: Fehler eines Projekts stoppen NICHT.
    # EN: 3) Load project by project — robust: one project's failure does NOT stop it.
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
    # EN: 4) Summary
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
    # EN: Success as soon as at least one project has been loaded.
    return 0 if loaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
