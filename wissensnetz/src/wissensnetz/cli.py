"""CLI-Einstieg für das Wissensnetz (``wissensnetz ...``).

Aktuell umgesetzt (Aufgabe 1 + 2):

    wissensnetz status                 Erreichbarkeit + Dataset/TBox prüfen
    wissensnetz init [--force]         Dataset sicherstellen + TBox laden
    wissensnetz load <datei.ttl|->     Turtle laden (Default- oder Named Graph)
    wissensnetz query "<SPARQL>"       SELECT/ASK ausführen (Tabellen-Ausgabe)

Die Unterbefehle für Anreicherung (Aufgabe 3) und Rückkanal (Aufgabe 4)
folgen in eigenen Modulen und werden hier ergänzt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import PREFIXES, Settings
from .graphstore import GraphStore, GraphStoreError
from .init import initialize, tbox_loaded


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wissensnetz",
        description="RDF-Store-Werkzeuge des DataBridge-Wissensnetzes (Fuseki/SPARQL).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Erreichbarkeit, Dataset und TBox prüfen")

    p_init = sub.add_parser("init", help="Dataset sicherstellen und TBox laden")
    p_init.add_argument("--force", action="store_true", help="TBox neu laden, auch wenn vorhanden")

    p_load = sub.add_parser("load", help="Turtle-Datei laden ('-' = stdin)")
    p_load.add_argument("source", help="Pfad zur .ttl-Datei oder '-' für stdin")
    p_load.add_argument("--graph", default=None, help="IRI eines Named Graph (Default: Default-Graph)")

    p_query = sub.add_parser("query", help="SPARQL SELECT/ASK ausführen")
    p_query.add_argument("sparql", help="SPARQL-Abfrage; Standard-PREFIXE werden vorangestellt")
    p_query.add_argument(
        "--raw",
        action="store_true",
        help="Abfrage unverändert senden (keine PREFIXE voranstellen)",
    )

    return parser


def _cmd_status(store: GraphStore) -> int:
    s = store.settings
    print(f"Fuseki:  {s.base_url}  (Dataset '{s.dataset}')")
    if not store.is_reachable():
        print("Status:  NICHT erreichbar — läuft 'docker compose up graph-db'?")
        return 1
    print("Status:  erreichbar")
    try:
        exists = store.dataset_exists()
    except GraphStoreError as exc:
        print(f"Dataset: unbekannt ({exc})")
        return 1
    print(f"Dataset: {'vorhanden' if exists else 'FEHLT (init ausführen)'}")
    if exists:
        print(f"TBox:    {'geladen' if tbox_loaded(store) else 'nicht geladen (init ausführen)'}")
    return 0


def _cmd_init(store: GraphStore, force: bool) -> int:
    report = initialize(store, force=force)
    print(f"Dataset '{report['dataset']}': "
          f"{'neu angelegt' if report['dataset_created'] else 'bereits vorhanden'}")
    print(f"TBox:    {report['tbox']}")
    print(f"Klassen: {report['owl_classes']} owl:Class im Store")
    return 0


def _cmd_load(store: GraphStore, source: str, graph: str | None) -> int:
    if source == "-":
        turtle = sys.stdin.read()
        store.load_turtle(turtle, graph=graph)
        origin = "stdin"
    else:
        path = Path(source)
        if not path.exists():
            print(f"Datei nicht gefunden: {path}", file=sys.stderr)
            return 1
        store.load_turtle(path, graph=graph)
        origin = str(path)
    target = f"Named Graph <{graph}>" if graph else "Default-Graph"
    print(f"Geladen: {origin} -> {target}")
    return 0


def _cmd_query(store: GraphStore, sparql: str, raw: bool) -> int:
    full = sparql if raw else PREFIXES + sparql
    rows = store.query(full)
    if not rows:
        print("(keine Ergebnisse)")
        return 0
    columns = list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    print("  ".join("-" * widths[c] for c in columns))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))
    print(f"\n{len(rows)} Zeile(n)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    store = GraphStore(Settings.from_env())
    try:
        if args.command == "status":
            return _cmd_status(store)
        if args.command == "init":
            return _cmd_init(store, args.force)
        if args.command == "load":
            return _cmd_load(store, args.source, args.graph)
        if args.command == "query":
            return _cmd_query(store, args.sparql, args.raw)
    except (GraphStoreError, FileNotFoundError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 2  # unbekannter Befehl (argparse fängt das eigentlich vorher ab)


if __name__ == "__main__":
    raise SystemExit(main())
