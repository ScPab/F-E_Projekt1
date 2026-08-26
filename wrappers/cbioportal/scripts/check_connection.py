"""Smoke-Test: prüft, ob der cBioPortal-Wrapper tatsächlich gegen die echte
cBioPortal-API sprechen kann.

Kein Unit-Test (kein Mocking, echter Netzwerk-Request) — bewusst ein
einfaches, eigenständiges Skript für den schnellen manuellen/CI-Check
"funktioniert die Verbindung zu cBioPortal gerade", analog zu
wrappers/gdc/scripts/check_connection.py. Prüft nacheinander Studien-Suche
(list_studies), Schema-Introspektion (get_schema) und einen kleinen
Molekulardaten-Abruf (get_molecular_data), siehe wrappers/cbioportal/client.py.

Aufruf:
    python wrappers/cbioportal/scripts/check_connection.py

Nutzt CBIOPORTAL_API_BASE_URL aus der Umgebung, falls gesetzt, sonst den
öffentlichen Standard https://www.cbioportal.org/api.

Exit-Code 0 bei Erfolg, 1 bei Fehler (z. B. für CI/Cron nutzbar).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Läuft auch ohne vorherige `pip install -e ./wrappers` — wrappers/ wird
# direkt auf den Pfad gelegt, damit `import cbioportal` funktioniert.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cbioportal import CBioPortalWrapper  # noqa: E402
from requests import RequestException  # noqa: E402

# Öffentlich zugängliche TCGA-Beispielstudie, passend zum Testfall
# TCGA-BRCA/TCGA-ACC der anderen Wrapper.
SAMPLE_STUDY_ID = "acc_tcga"


def main() -> int:
    base_url = os.environ.get("CBIOPORTAL_API_BASE_URL", "https://www.cbioportal.org/api")
    wrapper = CBioPortalWrapper(base_url)

    print(f"Teste Verbindung zu {base_url} ...")
    try:
        result = wrapper.list_studies(keyword="breast", size=3)
    except RequestException as exc:
        print(f"FEHLER: cBioPortal-API nicht erreichbar oder Fehler: {exc}")
        return 1

    hits = result.get("results", [])
    if not hits:
        print("FEHLER: Antwort kam an, enthält aber keine erwarteten Treffer.")
        print(result)
        return 1
    print(f"OK: {len(hits)} Studien für Stichwort 'breast', Beispiel: {hits[0].get('studyId')}")

    print(f"Prüfe Schema-Introspektion (clinical-attributes) für Studie {SAMPLE_STUDY_ID} ...")
    try:
        fields = wrapper.get_schema(SAMPLE_STUDY_ID)
    except RequestException as exc:
        print(f"FEHLER: Schema-Abfrage fehlgeschlagen: {exc}")
        return 1
    if not fields:
        print("FEHLER: Schema-Antwort war leer.")
        return 1
    print(f"OK: {len(fields)} klinische Attribute für Studie '{SAMPLE_STUDY_ID}' verfügbar (z. B. {fields[:3]}).")

    print("Prüfe Bulk-Tier (Molekulardaten) ...")
    try:
        profiles = wrapper.list_molecular_profiles(SAMPLE_STUDY_ID)
        sample_lists = wrapper.list_sample_lists(SAMPLE_STUDY_ID)
        gistic_profile = next(p["molecularProfileId"] for p in profiles if p["molecularProfileId"].endswith("_gistic"))
        all_samples = next(s["sampleListId"] for s in sample_lists if s["sampleListId"].endswith("_all"))
        molecular = wrapper.get_molecular_data(
            gistic_profile, sample_list_id=all_samples, entrez_gene_ids=[672, 675]
        )
    except (RequestException, StopIteration) as exc:
        print(f"FEHLER: Molekulardaten-Abruf fehlgeschlagen: {exc}")
        return 1
    if not molecular["results"]:
        print("FEHLER: Molekulardaten-Antwort war leer.")
        return 1
    print(f"OK: {len(molecular['results'])} Werte aus Profil '{gistic_profile}' abgerufen.")

    print("\nVerbindung zu cBioPortal funktioniert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
