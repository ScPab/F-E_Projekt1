#!/usr/bin/env python3
"""Interaktive Visualisierung des Wissensnetzes (pyvis) aus dem laufenden Fuseki.

    python scripts/graph_view.py                 # graph_view.html erzeugen und oeffnen
    python scripts/graph_view.py --limit 800 --no-open

Zieht per SPARQL Tripel aus Default- UND Named-Graphs, baut daraus ein
interaktives HTML-Netz und faerbt die Knoten nach Bereich:
  * Schema (TBox/Vokabular)      - blau
  * TCGA-Instanzen (Faelle etc.) - gruen
  * Rueckkanal (Annotationen)    - rot
  * Externe Konzepte (NCIt ...)  - lila
Zweck: ein Gefuehl, wie das Netz waechst. Einfach erneut ausfuehren zum Aktualisieren.

Projekt-Skript (nutzt nur wissensnetz.GraphStore ueber SPARQL; keine Kopplung an
mediator/wrappers). Zusatz-Abhaengigkeit: pyvis.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from wissensnetz import GraphStore

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
ONTO = "http://databridge.hka/onto#"
INSTANCE = "http://databridge.hka/instance/"
ANNO = "http://databridge.hka/instance/annotation/"
USERGRAPH = "http://databridge.hka/graph/user/"

COLORS = {
    "schema":   "#2E74B5",   # TBox / Vokabular
    "instanz":  "#2E7D32",   # TCGA-Instanzen
    "feedback": "#C0504D",   # Rueckkanal / Annotationen
    "extern":   "#7B4FA3",   # NCIt & andere externe Konzepte
    "other":    "#999999",
}


def localname(iri: str) -> str:
    s = iri.rstrip("/#")
    for sep in ("#", "/"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s or iri


def region(iri: str, node_type: str | None) -> str:
    if iri.startswith(ANNO) or iri.startswith(USERGRAPH):
        return "feedback"
    if node_type in {"ExpertFinding", "Annotation", "Reclassification"}:
        return "feedback"
    if iri.startswith(ONTO) or iri.startswith("http://www.w3.org/"):
        return "schema"
    if "obolibrary.org" in iri or iri.startswith("http://purl.") or "NCIT_" in iri:
        return "extern"
    if iri.startswith(INSTANCE):
        return "instanz"
    return "other"


def _q_iri_iri(store: GraphStore, limit: int) -> list[dict]:
    return store.query(
        "SELECT ?s ?p ?o WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } "
        f"FILTER(isIRI(?s) && isIRI(?o)) }} LIMIT {limit}"
    )


def _q_iri_literal(store: GraphStore, limit: int) -> list[dict]:
    return store.query(
        "SELECT ?s ?p ?o WHERE { { ?s ?p ?o } UNION { GRAPH ?g { ?s ?p ?o } } "
        f"FILTER(isIRI(?s) && isLiteral(?o)) }} LIMIT {limit}"
    )


def build(store: GraphStore, limit: int, output: str) -> tuple[int, int]:
    edges = _q_iri_iri(store, limit)
    lits = _q_iri_literal(store, limit)

    # rdf:type je Knoten (fuer Faerbung)
    node_type: dict[str, str] = {}
    for r in edges:
        if r.get("p") == RDF_TYPE and r.get("s") and r.get("o"):
            node_type[r["s"]] = localname(r["o"])

    # Literale als Tooltip-Text je Knoten sammeln
    tips: dict[str, list[str]] = {}
    for r in lits:
        s, p, o = r.get("s"), r.get("p"), r.get("o")
        if s and p is not None and o is not None:
            tips.setdefault(s, []).append(f"{localname(p)}: {o}")

    # Knoten einsammeln
    node_ids: set[str] = set()
    for r in edges:
        if r.get("s"):
            node_ids.add(r["s"])
        if r.get("o"):
            node_ids.add(r["o"])

    from pyvis.network import Network  # lazy: nur wenn wirklich gerendert wird

    net = Network(height="820px", width="100%", directed=True, bgcolor="#ffffff",
                  font_color="#222222", cdn_resources="remote")
    net.barnes_hut(gravity=-8000, spring_length=120)

    for nid in node_ids:
        typ = node_type.get(nid)
        reg = region(nid, typ)
        label = localname(nid)
        title_lines = [nid]
        if typ:
            title_lines.append(f"Typ: {typ}")
        title_lines += tips.get(nid, [])
        net.add_node(nid, label=label, title="\n".join(title_lines),
                     color=COLORS[reg], shape="dot", size=14)

    edge_count = 0
    for r in edges:
        s, p, o = r.get("s"), r.get("p"), r.get("o")
        if not s or not o:
            continue
        if p == RDF_TYPE:
            net.add_edge(s, o, label="a", color="#CCCCCC", dashes=True, arrows="to")
        else:
            net.add_edge(s, o, label=localname(p) if p else "", color="#8899AA", arrows="to")
        edge_count += 1

    # Standalone-HTML schreiben (ohne Auto-Open durch pyvis)
    try:
        net.write_html(output, open_browser=False, notebook=False)
    except TypeError:
        net.save_graph(output)  # aeltere pyvis-Versionen

    return len(node_ids), edge_count


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Wissensnetz als interaktives HTML (pyvis) visualisieren.")
    p.add_argument("--limit", type=int, default=500, help="max. Tripel je Abfrage (Default: 500)")
    p.add_argument("--output", default="graph_view.html", help="Ausgabedatei (Default: graph_view.html)")
    p.add_argument("--no-open", action="store_true", help="HTML nicht automatisch im Browser oeffnen")
    args = p.parse_args(argv)

    try:
        import pyvis  # noqa: F401
    except ImportError:
        print("pyvis ist nicht installiert - Visualisierung wird uebersprungen.", file=sys.stderr)
        print("Installieren mit:  pip install pyvis   (oder: pip install -r requirements.txt)", file=sys.stderr)
        return 0

    store = GraphStore()
    if not store.is_reachable():
        print(f"Fuseki nicht erreichbar unter {store.settings.base_url}.", file=sys.stderr)
        print("Zuerst starten:  docker compose up -d graph-db  &&  wissensnetz init", file=sys.stderr)
        return 1

    n_nodes, n_edges = build(store, args.limit, args.output)
    if n_nodes == 0:
        print("Der Store ist (noch) leer — nichts zu zeichnen. Erst Daten laden "
              "(wissensnetz load ... oder scripts/load_gdc.py).")
        return 0

    out_abs = os.path.abspath(args.output)
    print(f"OK: {n_nodes} Knoten, {n_edges} Kanten -> {out_abs}")
    if not args.no_open:
        webbrowser.open(f"file:///{out_abs.replace(os.sep, '/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
