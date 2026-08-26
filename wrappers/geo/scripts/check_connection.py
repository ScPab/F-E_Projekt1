"""Smoke-Test: prüft, ob der GEO-Wrapper tatsächlich gegen die echte NCBI-E-utilities-API sprechen kann.

Kein Unit-Test (kein Mocking, echter Netzwerk-Request) — bewusst ein
einfaches, eigenständiges Skript für den schnellen manuellen/CI-Check
"funktioniert die Verbindung zu GEO/NCBI gerade", analog zu
wrappers/gdc/scripts/check_connection.py. Prüft nacheinander Metadaten-Suche
(GEOWrapper.search) und Schema-Introspektion (GEOWrapper.get_schema), siehe
wrappers/geo/client.py.

Aufruf:
    python wrappers/geo/scripts/check_connection.py

Nutzt GEO_API_BASE_URL aus der Umgebung, falls gesetzt, sonst den
NCBI-Standard https://eutils.ncbi.nlm.nih.gov/entrez/eutils.

Exit-Code 0 bei Erfolg, 1 bei Fehler (z. B. für CI/Cron nutzbar).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Läuft auch ohne vorherige `pip install -e ./wrappers` — wrappers/ wird
# direkt auf den Pfad gelegt, damit `import geo` funktioniert.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from geo import GEOWrapper  # noqa: E402
from requests import RequestException  # noqa: E402


def main() -> int:
    base_url = os.environ.get("GEO_API_BASE_URL", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
    wrapper = GEOWrapper(base_url)

    print(f"Teste Verbindung zu {base_url} ...")
    try:
        result = wrapper.search(organism="Homo sapiens", entry_type="gse", size=1)
    except RequestException as exc:
        print(f"FEHLER: NCBI-API nicht erreichbar oder Fehler: {exc}")
        return 1

    pagination = result.get("pagination", {})
    hits = result.get("results", [])
    if not pagination.get("total") or not hits:
        print("FEHLER: Antwort kam an, enthält aber keine erwarteten Daten (Pagination/Treffer fehlen).")
        print(result)
        return 1
    print(
        f"OK: {pagination['total']} Treffer insgesamt für Homo sapiens/Series, "
        f"Beispiel-Accession: {hits[0].get('accession')}"
    )

    print("Prüfe Schema-Introspektion (einfo) ...")
    try:
        fields = wrapper.get_schema()
    except RequestException as exc:
        print(f"FEHLER: Schema-Abfrage fehlgeschlagen: {exc}")
        return 1
    if not fields:
        print("FEHLER: Schema-Antwort war leer.")
        return 1
    print(f"OK: {len(fields)} Such-Feld-Tags für Datenbank 'gds' verfügbar (z. B. {fields[:3]}).")

    print("\nVerbindung zu GEO/NCBI funktioniert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
