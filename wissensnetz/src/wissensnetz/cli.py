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

from . import enrichment, feedback
from .config import INSTANCE, PREFIXES, Settings
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

    # --- Aufgabe 3: Anreicherung (Lesen) ---
    p_hier = sub.add_parser("hierarchy", help="Unter-/Oberklassen via rdfs:subClassOf*")
    p_hier.add_argument("klasse", help="Klasse als CURIE (db:Case) oder volle IRI")
    p_hier.add_argument("--up", action="store_true", help="Oberklassen statt Unterklassen")
    p_hier.add_argument("--no-self", action="store_true", help="die Klasse selbst ausschließen")

    p_ctx = sub.add_parser("context", help="Kontext zu einem Case oder einer Diagnose")
    p_ctx.add_argument(
        "ref",
        help="Case (submitterId oder IRI) oder Diagnose (IRI oder Kennung wie d-11111111)",
    )

    # --- Aufgabe 4: Rückkanal (Schreiben) ---
    p_fb = sub.add_parser("feedback", help="MP-Selektions-Event in den Nutzer-Graph schreiben")
    p_fb.add_argument("event", help="Pfad zu einem selection_event.json")
    p_fb.add_argument("--user", default=None, help="Nutzer-ID überschreiben (sonst aus dem Event)")

    p_find = sub.add_parser("findings", help="Gespeicherte Experten-Erkenntnisse auflisten")
    p_find.add_argument("--user", default=None, help="nur Erkenntnisse dieses Nutzers")

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


def _cmd_hierarchy(store: GraphStore, klasse: str, up: bool, no_self: bool) -> int:
    fn = enrichment.superclasses if up else enrichment.subclasses
    result = fn(store, klasse, include_self=not no_self)
    richtung = "Oberklassen" if up else "Unterklassen"
    print(f"{richtung} von {klasse} (rdfs:subClassOf*):")
    if not result:
        print("  (keine)")
        return 0
    for iri in result:
        print(f"  {iri}")
    print(f"\n{len(result)} Klasse(n)")
    return 0


def _detect_kind(store: GraphStore, ref: str) -> str | None:
    """'case' | 'diagnosis' | None — anhand des Store-Inhalts bestimmt."""
    if enrichment._is_iri(ref):
        term = enrichment._term(ref)
        if store.ask(PREFIXES + f"ASK {{ {term} a db:Case }}"):
            return "case"
        if store.ask(PREFIXES + f"ASK {{ {term} a db:Diagnosis }}"):
            return "diagnosis"
        return None
    lit = enrichment._escape_literal(ref)
    if store.ask(PREFIXES + f'ASK {{ ?c a db:Case ; db:submitterId "{lit}" }}'):
        return "case"
    if store.ask(PREFIXES + f"ASK {{ <{INSTANCE}diagnosis/{ref}> a db:Diagnosis }}"):
        return "diagnosis"
    return None


def _cmd_context(store: GraphStore, ref: str) -> int:
    kind = _detect_kind(store, ref)
    if kind == "case":
        ctx = enrichment.case_context(store, ref)
        print(f"Case:        {ctx['case_iri']}")
        print(f"submitterId: {ctx.get('submitter_id') or '—'}")
        print(f"Projekt:     {ctx.get('project_id') or '—'}")
        print(f"Geschlecht:  {ctx.get('gender') or '—'}")
        diagnoses = ctx.get("diagnoses") or []
        print(f"Diagnosen:   {len(diagnoses)}")
        for d in diagnoses:
            aligned = d.get("aligned_concept") or "— (kein NCIt-Alignment)"
            print(f"  - {d.get('label') or '—'}  "
                  f"(Alter: {d.get('age_at_diagnosis')}, NCIt: {aligned})")
            print(f"    {d['iri']}")
        return 0
    if kind == "diagnosis":
        ctx = enrichment.diagnosis_context(store, ref)
        aligned = ctx.get("aligned_concept") or "— (kein NCIt-Alignment)"
        print(f"Diagnose:    {ctx['diagnosis_iri']}")
        print(f"Label:       {ctx.get('label') or '—'}")
        print(f"Alter:       {ctx.get('age_at_diagnosis')}")
        print(f"NCIt:        {aligned}")
        print(f"Case:        {ctx.get('case_iri') or '—'}")
        print(f"submitterId: {ctx.get('submitter_id') or '—'}")
        return 0
    print(f"Kein Case und keine Diagnose zu '{ref}' gefunden.", file=sys.stderr)
    return 1


def _cmd_feedback(store: GraphStore, event_path: str, user: str | None) -> int:
    path = Path(event_path)
    if not path.exists():
        print(f"Event-Datei nicht gefunden: {path}", file=sys.stderr)
        return 1
    event = feedback.SelectionEvent.from_json_file(path)
    if user:
        event.user = user
    graph_iri = feedback.write_feedback(store, event)
    print(f"Erkenntnis geschrieben für Nutzer '{event.user}'")
    print(f"Named Graph: {graph_iri}")
    print(f"Proben:      {len(event.samples)}  "
          f"(Hypothese {event.hypothesis.from_} -> {event.hypothesis.to})")
    return 0


def _cmd_findings(store: GraphStore, user: str | None) -> int:
    findings = feedback.list_findings(store, user=user)
    if not findings:
        print("(keine Erkenntnisse gefunden)")
        return 0
    recls = feedback.reclassifications(store, user=user)
    by_anno: dict[str, list[dict]] = {}
    for r in recls:
        by_anno.setdefault(r["annotation"], []).append(r)
    for f in findings:
        hyp = f["hypothesis"]
        print(f"- {f['annotation']}")
        print(f"    Nutzer:    {f.get('user') or '—'}   Zeit: {f.get('timestamp') or '—'}")
        print(f"    Sicht:     {f.get('view') or '—'}   morph-t: {f.get('morph_param') or '—'}"
              f"   Konfidenz: {f.get('confidence') or '—'}")
        print(f"    Hypothese: {hyp.get('from') or '—'} -> {hyp.get('to') or '—'}"
              + (f"  ({hyp['note']})" if hyp.get("note") else ""))
        print(f"    Ziele:     {len(f['targets'])} Probe(n)")
        stars = by_anno.get(f["annotation"], [])
        for r in stars:
            print(f"      * {r['sample']}  reclassifiedAs {r['reclassified_as']}"
                  f"  @ {r.get('confidence') or '—'}")
    print(f"\n{len(findings)} Erkenntnis(se)")
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
        if args.command == "hierarchy":
            return _cmd_hierarchy(store, args.klasse, args.up, args.no_self)
        if args.command == "context":
            return _cmd_context(store, args.ref)
        if args.command == "feedback":
            return _cmd_feedback(store, args.event, args.user)
        if args.command == "findings":
            return _cmd_findings(store, args.user)
    except (GraphStoreError, FileNotFoundError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 2  # unbekannter Befehl (argparse fängt das eigentlich vorher ab)


if __name__ == "__main__":
    raise SystemExit(main())
