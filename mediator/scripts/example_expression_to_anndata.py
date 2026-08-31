"""Beispiel-Skript: TCGA-BRCA-Beispiel-Expression -> anndata/.h5ad, end-to-end ohne
laufenden Mediator-Service (analog zu scripts/example_gdc_to_rdf.py).

Nutzt dieselbe Assemblierungs-Logik wie POST /export/anndata
(app/semantic/expression.py), liest die Expressions-Beispieldaten aus
sample_data/expression/*.rna_seq.gene_counts.tsv (Format 1:1 gegen eine
echte, live von der GDC-API geladene RNA-Seq-STAR-Gene-Counts-Datei
verifiziert — Werte selbst sind erfunden, keine echten Patientendaten,
analog zu sample_data/cases_brca_sample.json) sowie die klinischen
`obs`-Felder aus sample_data/cases_brca_sample.json (steht hier für
`enrichment.all_cases()` ein, da dieses Skript bewusst ohne laufendes
Fuseki auskommt — siehe wissensnetz/HANDOFF_anndata.md, Abschnitt 3b).

Schreibt das Ergebnis nach sample_data/tcga_brca_sample.h5ad — eingefrorene
Referenz-Fixture (Teil 3 im Handoff, "Gemeinsam: ein Referenz-.h5ad für
TCGA-BRCA (klein) als Fixture, analog zu cases_brca_sample.*"), Grundlage für
eine spätere MP-lite-Integration.

Aufruf (aus dem Verzeichnis mediator/, mit installiertem anndata/pandas/numpy,
optional scikit-learn für die tSNE-obsm-Spalte):
    python scripts/example_expression_to_anndata.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MEDIATOR_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEDIATOR_ROOT))  # macht das app-Package importierbar, ohne den Mediator zu starten

from app.semantic import expression  # noqa: E402

CASES_PATH = MEDIATOR_ROOT / "sample_data" / "cases_brca_sample.json"
EXPRESSION_DIR = MEDIATOR_ROOT / "sample_data" / "expression"
OUTPUT_PATH = MEDIATOR_ROOT / "sample_data" / "tcga_brca_sample.h5ad"

# Nur die "Primary Tumor"-Probe je Case (siehe sample_data/expression/*.tsv) —
# obs-Granularität "pro Sample" (siehe expression.build_obs-Docstring), hier
# auf ein repräsentatives Sample je Case beschränkt, weil nur dafür
# Beispiel-Expressionsdateien vorliegen.
PRIMARY_SAMPLE_SUFFIX = "-01"


def _case_context_row(case: dict) -> dict:
    """Flacht ein cases_brca_sample.json-Case auf dieselbe Dict-Form ab, die
    `wissensnetz.enrichment.all_cases()` liefert (siehe expression.build_obs)."""
    demographic = case.get("demographic") or {}
    diagnosis = (case.get("diagnoses") or [{}])[0]
    return {
        "submitter_id": case.get("submitter_id"),
        "project_id": (case.get("project") or {}).get("project_id"),
        "gender": demographic.get("gender"),
        "race": demographic.get("race"),
        "ethnicity": demographic.get("ethnicity"),
        "vital_status": demographic.get("vital_status"),
        "tumor_stage": diagnosis.get("ajcc_pathologic_stage"),
        "morphology": diagnosis.get("morphology"),
        "site_of_resection_or_biopsy": diagnosis.get("site_of_resection_or_biopsy"),
        "has_metastasis": diagnosis.get("metastasis_at_diagnosis"),
        "primary_diagnosis": diagnosis.get("primary_diagnosis"),
        "age_at_diagnosis": diagnosis.get("age_at_diagnosis"),
    }


def main() -> None:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]

    cases_by_submitter = {c["submitter_id"]: _case_context_row(c) for c in cases}

    sample_case_map: dict[str, str] = {}
    sample_types: dict[str, str] = {}
    sample_files: dict[str, Path] = {}
    for case in cases:
        for sample in case.get("samples") or []:
            sample_id = sample["sample_id"]
            if not sample_id.endswith(PRIMARY_SAMPLE_SUFFIX):
                continue
            expr_path = EXPRESSION_DIR / f"{sample_id}.rna_seq.gene_counts.tsv"
            if not expr_path.exists():
                continue
            sample_case_map[sample_id] = case["submitter_id"]
            sample_types[sample_id] = sample.get("sample_type")
            sample_files[sample_id] = expr_path

    X, sample_ids, gene_ids, gene_labels = expression.assemble_matrix(
        sample_files, id_column="gene_id", value_column="tpm_unstranded", label_column="gene_name"
    )

    obs = expression.build_obs(sample_case_map, cases_by_submitter, sample_types=sample_types)
    obs = obs.loc[sample_ids]
    var = expression.build_var(gene_ids, gene_labels)

    obsm = {}
    tsne = expression.compute_tsne(X)
    if tsne is not None:
        obsm["X_tsne_genes"] = tsne

    adata = expression.build_anndata(X, obs, var, obsm=obsm or None)
    out_path = expression.write_h5ad(adata, OUTPUT_PATH)

    print(f"{adata.n_obs} Proben x {adata.n_vars} Gene -> {out_path}")
    print(f"obs-Spalten: {list(obs.columns)}")
    print(f"obsm: {list(obsm.keys()) or '(keine — zu wenige Proben oder scikit-learn fehlt)'}")
    print(obs)


if __name__ == "__main__":
    main()
