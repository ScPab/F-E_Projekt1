"""Smoke-Test: prüft, ob der GDC-Wrapper tatsächlich gegen die echte GDC-API sprechen kann.

Kein Unit-Test (kein Mocking, echter Netzwerk-Request) — bewusst ein
einfaches, eigenständiges Skript für den schnellen manuellen/CI-Check
"funktioniert die Verbindung zur GDC-API gerade". Prüft nacheinander
Metadaten-Suche (GDCWrapper.search) und Schema-Introspektion
(GDCWrapper.get_schema), siehe wrappers/gdc/client.py.

Aufruf:
    python wrappers/gdc/scripts/check_connection.py

Nutzt GDC_API_BASE_URL aus der Umgebung, falls gesetzt (siehe .env.example),
sonst den GDC-Standard https://api.gdc.cancer.gov.

Exit-Code 0 bei Erfolg, 1 bei Fehler (z. B. für CI/Cron nutzbar).

English: Smoke test: checks whether the GDC wrapper can actually talk to
the real GDC API.

Not a unit test (no mocking, real network request) — deliberately a simple,
standalone script for the quick manual/CI check "does the connection to the
GDC API currently work". Checks metadata search (GDCWrapper.search) and
schema introspection (GDCWrapper.get_schema) in sequence, see
wrappers/gdc/client.py.

Invocation:
    python wrappers/gdc/scripts/check_connection.py

Uses GDC_API_BASE_URL from the environment if set (see .env.example),
otherwise the GDC default https://api.gdc.cancer.gov.

Exit code 0 on success, 1 on error (e.g. usable for CI/cron).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Läuft auch ohne vorherige `pip install -e ./wrappers` — wrappers/ wird
# direkt auf den Pfad gelegt, damit `import gdc` funktioniert.
# EN: Also runs without a prior `pip install -e ./wrappers` — wrappers/ is
# put directly on the path so `import gdc` works.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gdc import GDCWrapper  # noqa: E402
from requests import RequestException  # noqa: E402


def main() -> int:
    base_url = os.environ.get("GDC_API_BASE_URL", "https://api.gdc.cancer.gov")
    wrapper = GDCWrapper(base_url)

    print(f"Teste Verbindung zu {base_url} ...")
    try:
        result = wrapper.search(
            "files",
            project_id="TCGA-BRCA",
            experimental_strategy="RNA-Seq",
            fields=["file_id", "file_name"],
            size=1,
        )
    except RequestException as exc:
        print(f"FEHLER: GDC-API nicht erreichbar oder Fehler: {exc}")
        return 1

    pagination = result.get("pagination", {})
    hits = result.get("results", [])
    if not pagination.get("total") or not hits:
        print("FEHLER: Antwort kam an, enthält aber keine erwarteten Daten (Pagination/Treffer fehlen).")
        print(result)
        return 1
    print(f"OK: {pagination['total']} Treffer insgesamt für TCGA-BRCA/RNA-Seq, Beispiel: {hits[0]}")

    print("Prüfe Schema-Introspektion (_mapping) ...")
    try:
        fields = wrapper.get_schema("cases")
    except RequestException as exc:
        print(f"FEHLER: Schema-Abfrage fehlgeschlagen: {exc}")
        return 1
    if not fields:
        print("FEHLER: Schema-Antwort war leer.")
        return 1
    print(f"OK: {len(fields)} Felder für Endpunkt 'cases' verfügbar (z. B. {fields[:3]}).")

    print("\nVerbindung zur GDC-API funktioniert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
