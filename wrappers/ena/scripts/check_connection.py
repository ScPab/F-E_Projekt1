"""Smoke-Test: prüft, ob der ENA-Wrapper tatsächlich gegen die echte EBI-Portal-API sprechen kann.

Kein Unit-Test (kein Mocking, echter Netzwerk-Request) — bewusst ein
einfaches, eigenständiges Skript für den schnellen manuellen/CI-Check
"funktioniert die Verbindung zu ENA gerade", analog zu
wrappers/gdc/scripts/check_connection.py. Prüft nacheinander Metadaten-Suche
(ENAWrapper.search) und Schema-Introspektion (ENAWrapper.get_schema), siehe
wrappers/ena/client.py.

Aufruf:
    python wrappers/ena/scripts/check_connection.py

Nutzt ENA_API_BASE_URL aus der Umgebung, falls gesetzt, sonst den
EBI-Standard https://www.ebi.ac.uk/ena/portal/api.

Exit-Code 0 bei Erfolg, 1 bei Fehler (z. B. für CI/Cron nutzbar).

English: Smoke test: checks whether the ENA wrapper can actually talk to
the real EBI Portal API.

Not a unit test (no mocking, real network request) — deliberately a simple,
standalone script for the quick manual/CI check "does the connection to
ENA currently work", analogous to
wrappers/gdc/scripts/check_connection.py. Checks metadata search
(ENAWrapper.search) and schema introspection (ENAWrapper.get_schema) in
sequence, see wrappers/ena/client.py.

Invocation:
    python wrappers/ena/scripts/check_connection.py

Uses ENA_API_BASE_URL from the environment if set, otherwise the EBI
default https://www.ebi.ac.uk/ena/portal/api.

Exit code 0 on success, 1 on error (e.g. usable for CI/cron).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Läuft auch ohne vorherige `pip install -e ./wrappers` — wrappers/ wird
# direkt auf den Pfad gelegt, damit `import ena` funktioniert.
# EN: Also runs without a prior `pip install -e ./wrappers` — wrappers/ is
# put directly on the path so `import ena` works.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ena import ENAWrapper  # noqa: E402
from requests import RequestException  # noqa: E402

# Öffentlich zugängliche Beispiel-Studie (RNA-Seq), zum schnellen manuellen
# Nachvollziehen live gegen die ENA-Weboberfläche geprüft.
# EN: Publicly accessible example study (RNA-Seq), checked live against the
# ENA web interface for quick manual verification.
SAMPLE_STUDY_ACCESSION = "PRJEB1234"


def main() -> int:
    base_url = os.environ.get("ENA_API_BASE_URL", "https://www.ebi.ac.uk/ena/portal/api")
    wrapper = ENAWrapper(base_url)

    print(f"Teste Verbindung zu {base_url} ...")
    try:
        result = wrapper.search(
            study_accession=SAMPLE_STUDY_ACCESSION,
            fields=["run_accession", "study_accession", "center_name"],
            size=1,
        )
    except RequestException as exc:
        print(f"FEHLER: ENA-API nicht erreichbar oder Fehler: {exc}")
        return 1

    hits = result.get("results", [])
    if not hits:
        print("FEHLER: Antwort kam an, enthält aber keine erwarteten Treffer.")
        print(result)
        return 1
    print(f"OK: Treffer für Studie {SAMPLE_STUDY_ACCESSION}, Beispiel: {hits[0]}")

    print("Prüfe Schema-Introspektion (returnFields) ...")
    try:
        fields = wrapper.get_schema("read_run")
    except RequestException as exc:
        print(f"FEHLER: Schema-Abfrage fehlgeschlagen: {exc}")
        return 1
    if not fields:
        print("FEHLER: Schema-Antwort war leer.")
        return 1
    print(f"OK: {len(fields)} Felder für Ergebnistyp 'read_run' verfügbar (z. B. {fields[:3]}).")

    print("\nVerbindung zu ENA funktioniert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
