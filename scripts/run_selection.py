#!/usr/bin/env python3
"""Hilfsskript: eine Auswahl (selection.json) durch den Mediator schicken und
das Ergebnis im Wissensnetz anzeigen — die Kette ohne Oberfläche.

    python scripts/run_selection.py selection.json
    python scripts/run_selection.py selection.json --generate
    python scripts/run_selection.py selection.json --generate --out wissensnetz/data/selection_demo.h5ad

Ablauf:
    1. POST <mediator>/selection/preview  bzw.  /selection/generate
       (UI-Auswahl -> Abruf -> Übersetzung -> Laden; Kollege B)
    2. mit --out: das erzeugte `.h5ad` über GET <mediator><download_url> holen
       (sonst bleibt es im Mediator-Container und MP-Lite findet es nicht)
    3. `wissensnetz selection <recipe_key>` je Ebene (Wissensnetz)

Dies ist der reguläre Weg nach ADR-0003: **ein** Scope statt eines globalen
Vorladens. scripts/selection_demo.json ist die versionierte Referenz-Auswahl.

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
         "modality": "gene_expression",
         "attributes": ["sex_at_birth", "tumor_stage"]}
      ],
      "size": 20
    }

English: Helper script: send a selection (selection.json) through the
mediator and display the result in the knowledge graph — the chain
without a UI.

    python scripts/run_selection.py selection.json
    python scripts/run_selection.py selection.json --generate
    python scripts/run_selection.py selection.json --generate --out wissensnetz/data/selection_demo.h5ad

Flow:
    1. POST <mediator>/selection/preview  or  /selection/generate
       (UI selection -> fetch -> translation -> load; colleague B)
    2. with --out: fetch the generated `.h5ad` via GET <mediator><download_url>
       (otherwise it stays in the mediator container and MP-Lite cannot find it)
    3. `wissensnetz selection <recipe_key>` per level (wissensnetz)

This is the regular path since ADR-0003: **one** scope instead of a
global preload. scripts/selection_demo.json is the versioned reference
selection.

Deliberately a PROJECT script (not in the wissensnetz package), pattern
like scripts/load_gdc.py: the package stays "graph-db only", this
script orchestrates mediator (HTTP) + wissensnetz. No GDC access.

A precondition for step 2 is that the mediator writes the manifest
(``wissensnetz.selection.write_selection``, see
wissensnetz/HANDOFF_pablo_store_waechst.md, P1/P2). As long as that is
not yet implemented, the script reports "no selection in the store" and
shows only the mediator's response — that is the expected interim
state, not a wissensnetz bug.

Configuration: --mediator-url or ENV MEDIATOR_URL (default
http://localhost:8000); Fuseki connection as in the package (ENV
GRAPH_DB_URL/GRAPH_DB_DATASET, see .env.example).

Format of selection.json (= mediator/app/schemas.py::SelectionRequest):

    {
      "levels": [
        {"source": "gdc", "cohorts": ["TCGA-BRCA"],
         "modality": "gene_expression",
         "attributes": ["sex_at_birth", "tumor_stage"]}
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
    """Die Auswahl an den Mediator schicken. ``None`` bei einem HTTP-Fehler.

    English: Sends the selection to the mediator. ``None`` on an HTTP
    error.
    """
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


def _download(base: str, download_url: str, out_path: Path, *, timeout: float = 900.0) -> Path:
    """Datei über ``GET {base}{download_url}`` streamen und nach ``out_path``
    schreiben (Muster: ``_download()`` in ``scripts/fetch_pancancer_h5ad.py``).

    Bewusst über den Download-Endpoint statt über den ``path`` aus der Antwort:
    das `.h5ad` liegt im Mediator-**Container**, der Host sieht den Pfad nicht.

    English: Streams the file via ``GET {base}{download_url}`` and
    writes it to ``out_path`` (pattern: ``_download()`` in
    ``scripts/fetch_pancancer_h5ad.py``).

    Deliberately via the download endpoint instead of the ``path`` from
    the response: the `.h5ad` lives inside the mediator **container**,
    the host cannot see that path.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(f"{base}{download_url}", stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
    return out_path


def _print_level(level: dict) -> str | None:
    """Eine Ebene der Mediator-Antwort ausgeben; gibt den recipe_key zurück.

    English: Prints one level of the mediator response; returns the
    recipe_key.
    """
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
    p.add_argument("--out", default=None,
                   help="Zieldatei für das .h5ad aus --generate (nur damit wirksam). "
                        "Bei mehreren Ebenen wird die Datei der ERSTEN Ebene mit status='ok' "
                        "geschrieben. Ohne --out bleibt das .h5ad im Mediator-Container.")
    args = p.parse_args(argv)

    path = Path(args.selection)
    if not path.exists():
        print(f"Auswahl-Datei nicht gefunden: {path}", file=sys.stderr)
        return 1
    try:
        # utf-8-sig: Windows-Werkzeuge (PowerShell `Out-File -Encoding utf8`)
        # schreiben ein BOM; utf-8-sig liest BOM-behaftetes UND BOM-freies UTF-8.
        # EN: utf-8-sig: Windows tools (PowerShell `Out-File -Encoding
        # utf8`) write a BOM; utf-8-sig reads BOM-prefixed AND BOM-free
        # UTF-8.
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        print(f"{path} ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 1

    base = args.mediator_url.rstrip("/")

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

    # 3) Optional: das .h5ad der ersten erfolgreichen Ebene herunterladen.
    # EN: 3) Optional: download the .h5ad of the first successful level.
    if args.out:
        if not args.generate:
            print("--out wirkt nur zusammen mit --generate (die Vorschau erzeugt kein .h5ad).",
                  file=sys.stderr)
        else:
            url = next(
                (lvl["anndata"]["download_url"] for lvl in levels
                 if lvl.get("status") == "ok" and (lvl.get("anndata") or {}).get("download_url")),
                None,
            )
            if not url:
                print("Keine Ebene hat ein .h5ad geliefert — nichts herunterzuladen.",
                      file=sys.stderr)
            else:
                try:
                    out_path = _download(base, url, Path(args.out), timeout=args.timeout)
                    print(f"\n.h5ad geschrieben: {out_path.resolve()}")
                except (requests.RequestException, OSError) as exc:
                    print(f"Download fehlgeschlagen: {exc}", file=sys.stderr)

    # 4) Ergebnis im Wissensnetz — dieselbe Ausgabe wie `wissensnetz selection <id>`.
    # EN: 4) Result in the knowledge graph — same output as `wissensnetz selection <id>`.
    known = {e.get("selection_id") for e in list_selections(store)}
    for key in keys:
        print(f"\n--- wissensnetz selection {key} ---")
        if key not in known and not selection_exists(store, key):
            print("(keine Auswahl im Store — schreibt der Mediator das Manifest schon? "
                  "siehe wissensnetz/HANDOFF_pablo_store_waechst.md, P1/P2)")
            continue
        wissensnetz_cli(["selection", key])  # öffentlicher CLI-Einstieg / EN: public CLI entry point

    return 0 if keys else 1


if __name__ == "__main__":
    raise SystemExit(main())
