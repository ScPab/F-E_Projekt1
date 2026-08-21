"""Smoke-Test: prüft die Mediator-REST-Schicht End-to-End — Übertragung
(Weiterreichen einer Anfrage an die GDC-API über POST /query) und
Übersetzung (GDC-Cases -> RDF/OWL über POST /transform, siehe
app/semantic/mapping.py und wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL).

Lädt die FastAPI-App direkt in-process (fastapi.testclient.TestClient) statt
einen eigenen Prozess zu starten — kein `docker compose up` oder laufender
`uvicorn` nötig. Macht echte Netzwerk-Requests gegen die reale GDC-API (kein
Mocking), prüft also den kompletten Pfad Mediator -> GDC-Wrapper -> GDC-API
-> Mapping -> Turtle.

Aufruf (aus dem Verzeichnis mediator/, mit installierten Dependencies:
fastapi, httpx, requests, rdflib sowie dem lokalen gdc-Package, z. B. via
`pip install -e ../wrappers`):
    python scripts/check_mediator.py

Exit-Code 0, wenn alle Checks erfolgreich sind, sonst 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

MEDIATOR_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEDIATOR_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from rdflib import RDF, Graph, Namespace  # noqa: E402

from app.main import app  # noqa: E402

DB = Namespace("http://databridge.hka/onto#")

client = TestClient(app)


def check_health() -> bool:
    r = client.get("/health")
    ok = r.status_code == 200 and r.json().get("status") == "ok"
    print(f"[health]     {'OK' if ok else 'FEHLER'} -- {r.status_code} {r.text}")
    return ok


def check_ontology() -> bool:
    r = client.get("/ontology")
    ok = r.status_code == 200 and "db:Case" in r.text
    print(f"[ontology]   {'OK' if ok else 'FEHLER'} -- {r.status_code}, {len(r.text)} Zeichen, TBox geladen: {'db:Case' in r.text}")
    return ok


def check_query_transfer() -> bool:
    """Übertragung: POST /query muss die Anfrage an die echte GDC-API weiterreichen und Treffer liefern."""
    r = client.post(
        "/query",
        json={
            "endpoint": "files",
            "project_id": "TCGA-BRCA",
            "experimental_strategy": "RNA-Seq",
            "fields": ["file_id", "file_name"],
            "size": 3,
        },
    )
    if r.status_code != 200:
        print(f"[query]      FEHLER -- Status {r.status_code}: {r.text}")
        return False
    body = r.json()
    hits = body.get("results", [])
    total = body.get("pagination", {}).get("total", 0)
    ok = bool(hits) and total > 0
    print(f"[query]      {'OK' if ok else 'FEHLER'} -- {len(hits)} Treffer, total={total}")
    return ok


def check_transform_translation() -> bool:
    """Übersetzung: POST /transform muss GDC-Cases live abrufen und als RDF/OWL (Turtle) übersetzen."""
    r = client.post("/transform", json={"source": "gdc", "project_id": "TCGA-BRCA", "size": 3})
    if r.status_code != 200:
        print(f"[transform]  FEHLER -- Status {r.status_code}: {r.text}")
        return False

    body = r.json()
    turtle = body.get("turtle", "")
    triple_count = body.get("triple_count", 0)
    if triple_count == 0 or not turtle:
        print("[transform]  FEHLER -- keine Tripel erzeugt.")
        return False

    # Nur der Turtle-Hauptteil ist mit rdflib direkt parsebar; ein etwaiger
    # RDF-star-Anhang (Provenienz/Konfidenz) folgt eigener Grammatik, siehe
    # app/semantic/mapping.py (serialize_with_provenance) und
    # docs/adding_new_sources.md, Abschnitt 4.
    main_part = turtle.split("# RDF-star:")[0]
    try:
        g = Graph()
        g.parse(data=main_part, format="turtle")
    except Exception as exc:  # noqa: BLE001
        print(f"[transform]  FEHLER -- erzeugtes Turtle ist nicht parsebar: {exc}")
        return False

    has_case = (None, RDF.type, DB.Case) in g
    ok = triple_count > 0 and has_case
    print(f"[transform]  {'OK' if ok else 'FEHLER'} -- {triple_count} Tripel gesamt, "
          f"{len(g)} im Hauptteil parsebar, db:Case-Instanz vorhanden: {has_case}")
    return ok


def main() -> int:
    checks = {
        "health": check_health(),
        "ontology": check_ontology(),
        "query (Übertragung)": check_query_transfer(),
        "transform (Übersetzung)": check_transform_translation(),
    }
    if all(checks.values()):
        print("\nMediator-Übertragung und -Übersetzung funktionieren.")
        return 0

    failed = [name for name, ok in checks.items() if not ok]
    print(f"\nFehlgeschlagen: {', '.join(failed)} -- siehe Ausgabe oben.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
