"""Beispiel-Skript: TCGA-BRCA-Beispiel-Cases -> RDF/OWL (Turtle), end-to-end ohne laufenden Mediator-Service.

Nutzt dieselbe Mapping-Logik wie POST /transform (app/semantic/mapping.py),
liest die Beispieldaten aus sample_data/cases_brca_sample.json und schreibt
das Ergebnis nach scripts/output/tcga_brca_sample.ttl.

Aufruf (aus dem Verzeichnis mediator/, mit installiertem rdflib):
    python scripts/example_gdc_to_rdf.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MEDIATOR_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEDIATOR_ROOT))  # macht das app-Package importierbar, ohne den Mediator zu starten

from app.semantic import mapping  # noqa: E402
from app.semantic.paths import alignment_path  # noqa: E402

SAMPLE_PATH = MEDIATOR_ROOT / "sample_data" / "cases_brca_sample.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "tcga_brca_sample.ttl"


def main() -> None:
    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]

    alignment = mapping.load_alignment_table(alignment_path("ncit_primary_diagnosis.json"))
    graph, star_annotations = mapping.cases_to_graph(cases, alignment=alignment)
    turtle = mapping.serialize_with_provenance(graph, star_annotations)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(turtle, encoding="utf-8")

    print(f"{len(graph)} Tripel aus {len(cases)} Cases erzeugt -> {OUTPUT_PATH}")
    if not alignment:
        print("Hinweis: Alignment-Tabelle (alignment/ncit_primary_diagnosis.json) ist leer — "
              "primaryDiagnosis-Werte liegen nur als Literal (primaryDiagnosisLabel) vor.")
    print()
    print(turtle)


if __name__ == "__main__":
    main()
