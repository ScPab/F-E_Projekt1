"""GDC-Expressionsdateien -> anndata/.h5ad (Teil 3, siehe wissensnetz/HANDOFF_anndata.md).

Setzt den Mediator-seitigen Schritt um, auf den alle Wrapper-Docstrings
verweisen (`Wrapper.to_anndata()` ist dort bewusst `NotImplementedError`):
Der Wrapper (Julian) beschafft rohe GDC-Quantifizierungsdateien (RNA-Seq
STAR-Gene-Counts bzw. miRNA-Seq-Quantifizierung) + Proben/Case-Zuordnung, das
Wissensnetz (Marcel) liefert die klinischen `obs`-Metadaten über
`enrichment.all_cases()`. Dieses Modul baut daraus den `anndata.AnnData`-
Container (X/obs/var/obsm) und serialisiert ihn nach `.h5ad`.

Architekturentscheidung (siehe HANDOFF_anndata.md, Abschnitt 0): Expression
läuft NICHT als RDF-Tripel ins Wissensnetz, sondern als Matrix im
`.h5ad`-Container — das Wissensnetz liefert nur die semantischen Metadaten,
mit denen `obs` angereichert wird.

Offene Punkte aus dem Handoff (Abschnitt 5), hier mit einer für den ersten
Wurf getroffenen, dokumentierten Default-Entscheidung (Team kann das
revidieren, siehe jeweilige Funktions-Docstrings):
  1. obs-Granularität: **pro Sample** (nicht pro Case) — Expression ist pro
     Aliquot/Sample gemessen, siehe `build_obs`.
  2. tSNE (`obsm`): optional vom Mediator selbst berechnet (`compute_tsne`,
     Default aus bewusst konservativ, siehe dort), sonst liefert der Export
     nur X/obs/var und Oviedo/Scanpy rechnet selbst.
  3. Genumfang: kein Default-Filter — alle Gene aus den gelieferten Dateien;
     ein Subset lässt sich über die Aufrufer-Ebene (Mediator-Endpoint)
     einschränken.
  4. Übergabeweg: siehe `POST /export/anndata` in app/main.py (Download-Endpoint).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from anndata import AnnData

from wissensnetz.cohorts import cancer_code

# obs-Spalten aus dem Wissensnetz (siehe HANDOFF_anndata.md, Abschnitt 3b,
# obs-Spalten-Mapping-Tabelle) -> Key im case_context()/all_cases()-Dict.
_OBS_CASE_FIELDS: tuple[tuple[str, str], ...] = (
    ("submitter_id", "submitter_id"),
    ("project_id", "project_id"),
    ("race", "race"),
    ("gender", "gender"),
    ("ethnicity", "ethnicity"),
    ("vital_status", "vital_status"),
    ("tumor_stage", "tumor_stage"),
    ("morphology", "morphology"),
    ("site_of_resection_or_biopsy", "site_of_resection_or_biopsy"),
    ("has_metastasis", "has_metastasis"),
    ("primary_diagnosis", "primary_diagnosis"),
    ("age_at_diagnosis", "age_at_diagnosis"),
)


class ExpressionAssemblyError(ValueError):
    """Rohdaten/Metadaten reichen nicht aus, um eine Matrix zusammenzubauen."""


def parse_gdc_quantification_file(
    path: str | Path,
    *,
    id_column: str,
    value_column: str,
    label_column: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Liest eine einzelne GDC-Quantifizierungsdatei (TSV, ggf. `.gz`) ein.

    Deckt sowohl RNA-Seq-Gene-Counts (`id_column="gene_id"`,
    `value_column="tpm_unstranded"`, `label_column="gene_name"`) als auch
    miRNA-Seq-Quantifizierung (`id_column="miRNA_ID"`,
    `value_column="reads_per_million_miRNA_mapped"`) ab, ohne das Format
    hart zu kodieren.

    GDC-STAR-Gene-Counts-Dateien enthalten vier Summenzeilen (`N_unmapped`,
    `N_multimapping`, `N_noFeature`, `N_ambiguous`) VOR den eigentlichen
    Gen-Zeilen, deren TPM/FPKM-Spalten leer sind. Statt eine ID-Präfix-Regel
    (z. B. "ENSG") hart zu kodieren, wird stattdessen generisch über
    `value_column` gefiltert: Zeilen, die sich dort nicht in eine Zahl
    umwandeln lassen, fallen heraus. Das funktioniert unverändert auch für
    miRNA-Dateien, die keine solchen Summenzeilen haben.

    Gibt ``{id: {"value": float, "label": str | None}}`` zurück (Reihenfolge
    wie in der Datei).
    """
    p = Path(path)
    compression = "gzip" if p.suffix == ".gz" else None
    df = pd.read_csv(p, sep="\t", comment="#", compression=compression, dtype=str)

    if id_column not in df.columns or value_column not in df.columns:
        raise ExpressionAssemblyError(
            f"{p}: erwartete Spalten {id_column!r}/{value_column!r} nicht gefunden "
            f"(vorhanden: {list(df.columns)})"
        )

    values = pd.to_numeric(df[value_column], errors="coerce")
    ids = df[id_column]
    keep = values.notna() & ids.notna()

    result: dict[str, dict[str, Any]] = {}
    for gene_id, value, label in zip(
        ids[keep], values[keep], df[label_column][keep] if label_column in df.columns else [None] * int(keep.sum())
    ):
        result[str(gene_id)] = {"value": float(value), "label": None if pd.isna(label) else str(label)}
    return result


def assemble_matrix(
    sample_files: dict[str, str | Path],
    *,
    id_column: str,
    value_column: str,
    label_column: Optional[str] = None,
    gene_ids: Optional[list[str]] = None,
) -> tuple[np.ndarray, list[str], list[str], dict[str, str]]:
    """Baut die Expressionsmatrix ``X`` (Proben x Gene/miRNA) aus mehreren
    Quantifizierungsdateien.

    ``sample_files``: ``{sample_id: dateipfad}`` — eine Datei je Probe (siehe
    Modul-Docstring, Proben↔Case-Zuordnung kommt vom Wrapper/Aufrufer).
    ``gene_ids``: optionale Whitelist (Genumfang einschränken, siehe
    Offener Punkt 3 im HANDOFF); ohne Angabe die Vereinigung aller in den
    Dateien vorkommenden IDs (sortiert, für deterministische Spaltenreihenfolge).

    Fehlt eine ID in einer einzelnen Probe (z. B. weil eine Datei ein anderes
    Gen-Set führt), wird ``0.0`` eingesetzt — anndata erwartet eine dichte
    Matrix ohne Lücken.

    Gibt ``(X, sample_ids, gene_ids, gene_labels)`` zurück; ``gene_labels``
    ist ``{gene_id: label}`` für die Gene, für die ein `label_column`-Wert
    gefunden wurde (Grundlage für `build_var`).
    """
    if not sample_files:
        raise ExpressionAssemblyError("Keine Expressions-Dateien übergeben — keine Probe zum Zusammenbauen.")

    sample_ids = list(sample_files.keys())
    parsed: dict[str, dict[str, dict[str, Any]]] = {
        sid: parse_gdc_quantification_file(
            path, id_column=id_column, value_column=value_column, label_column=label_column
        )
        for sid, path in sample_files.items()
    }

    if gene_ids is None:
        seen: set[str] = set()
        for rows in parsed.values():
            seen.update(rows.keys())
        gene_ids = sorted(seen)
    if not gene_ids:
        raise ExpressionAssemblyError("Keine Gen-/miRNA-IDs in den Quantifizierungsdateien gefunden.")

    gene_index = {gid: i for i, gid in enumerate(gene_ids)}
    X = np.zeros((len(sample_ids), len(gene_ids)), dtype=np.float32)
    gene_labels: dict[str, str] = {}
    for row, sid in enumerate(sample_ids):
        for gid, entry in parsed[sid].items():
            col = gene_index.get(gid)
            if col is None:
                continue
            X[row, col] = entry["value"]
            if entry["label"] and gid not in gene_labels:
                gene_labels[gid] = entry["label"]

    return X, sample_ids, gene_ids, gene_labels


def build_obs(
    sample_case_map: dict[str, str],
    cases_by_submitter: dict[str, dict[str, Any]],
    *,
    sample_types: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """Baut `obs` (Zeilen-Metadaten je Probe) aus dem Wissensnetz-Case-Kontext.

    obs-Index = **Probe** (``sample_id``), nicht Case (Offener Punkt 1 im
    HANDOFF, hier entschieden: Expression wird pro Aliquot/Sample gemessen).
    Die Klinik-Felder sind pro Case im Wissensnetz abgelegt und werden über
    ``sample_case_map`` (``sample_id -> submitter_id``, vom Aufrufer aus der
    GDC-Files-Suche gebaut) auf jede zugehörige Probe dupliziert — hat ein
    Case mehrere Proben, tragen sie identische Klinik-Werte, bis das
    Wissensnetz eine sample-granulare Abfrage liefert (siehe
    HANDOFF_anndata.md, Abschnitt 3c).

    ``cases_by_submitter``: ``{submitter_id: case_context-artiges Dict}``,
    wie es ``{c["submitter_id"]: c for c in enrichment.all_cases(store)}``
    liefert. Fehlt ein Case (z. B. noch nicht im Graphen), bleiben dessen
    Spalten für die betroffene Probe ``None`` statt eines Fehlers.
    """
    sample_types = sample_types or {}
    rows: list[dict[str, Any]] = []
    for sample_id, submitter_id in sample_case_map.items():
        case = cases_by_submitter.get(submitter_id, {})
        row: dict[str, Any] = {"sample_type": sample_types.get(sample_id)}
        for obs_col, case_key in _OBS_CASE_FIELDS:
            row[obs_col] = case.get(case_key)
        row["cancer"] = cancer_code(case.get("project_id"))
        rows.append(row)

    obs = pd.DataFrame(rows, index=pd.Index(list(sample_case_map.keys()), name="sample_id"))
    return obs


def build_var(gene_ids: list[str], gene_labels: Optional[dict[str, str]] = None) -> pd.DataFrame:
    """Baut `var` (Spalten-Metadaten je Gen/miRNA).

    ``gene_labels`` (optional, aus `assemble_matrix`) füllt eine
    `symbol`-Spalte (z. B. Gene-Symbol aus `gene_name`), wo vorhanden;
    fehlende Labels bleiben ``None``. Semantische Anreicherung (Gen -> GO)
    aus dem Wissensnetz ist laut HANDOFF optional/später und hier bewusst
    nicht Teil dieser ersten Ausbaustufe.
    """
    gene_labels = gene_labels or {}
    return pd.DataFrame(
        {"symbol": [gene_labels.get(gid) for gid in gene_ids]},
        index=pd.Index(gene_ids, name="feature_id"),
    )


def compute_tsne(X: np.ndarray, *, n_components: int = 2, random_state: int = 0) -> Optional[np.ndarray]:
    """Optionale 2D-tSNE-Projektion (Basis-Encoding `E[0]`/`E[1]` für MP-lite,
    siehe HANDOFF_anndata.md Offener Punkt 2 — "Wer berechnet die tSNE?").

    Erfordert `scikit-learn` (siehe mediator/environment.yml). tSNE braucht
    `perplexity < n_samples`; bei zu wenigen Proben (<= 3, kleiner als die
    sklearn-Mindest-Perplexity von 5 sinnvoll nutzbar) wird ``None``
    zurückgegeben statt eines Fehlers — der Aufrufer liefert dann `X`/`obs`/
    `var` ohne `obsm` (siehe Modul-Docstring, Punkt 2, zweite Alternative).
    """
    n_samples = X.shape[0]
    if n_samples <= 3:
        return None
    try:
        from sklearn.manifold import TSNE
    except ImportError:
        return None

    # sklearn verlangt perplexity < n_samples; bei kleinen Stichproben (z. B.
    # Fixtures) auf n_samples - 1 begrenzen statt einen ValueError zu riskieren.
    perplexity = min(30.0, max(5.0, (n_samples - 1) / 3), n_samples - 1)
    tsne = TSNE(n_components=n_components, random_state=random_state, perplexity=perplexity, init="pca")
    return tsne.fit_transform(X)


def build_anndata(
    X: np.ndarray,
    obs: pd.DataFrame,
    var: pd.DataFrame,
    *,
    obsm: Optional[dict[str, np.ndarray]] = None,
) -> AnnData:
    """Baut den `anndata.AnnData`-Container aus X/obs/var(/obsm)."""
    adata = AnnData(X=X, obs=obs, var=var)
    if obsm:
        for key, value in obsm.items():
            adata.obsm[key] = value
    return adata


def write_h5ad(adata: AnnData, path: str | Path) -> Path:
    """Serialisiert den AnnData-Container nach `.h5ad` (HDF5, von Scanpy nativ lesbar)."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out_path)
    return out_path
