"""Aufgabe 9 — Abnahme: Lesezugriff auf das Expressions-``.h5ad`` (h5ad_source).

Reine Datei-/anndata-Tests, **kein Fuseki** nötig. Ohne installiertes ``anndata``
(bzw. ``numpy``) wird die Datei übersprungen — konsistent mit den übrigen
Prototyp-Skips, damit die Suite auch ohne Prototyp-Extras grün bleibt.

Das Modul liegt im Prototyp (``prototype/mp_lite/h5ad_source.py``) und wird per
Dateipfad geladen (kein regulärer Import — konsistent mit ``test_encodings.py``).

English: Task 9 — acceptance: read access to the expression ``.h5ad``
(h5ad_source).

Pure file/anndata tests, **no Fuseki** needed. Without ``anndata`` (or
``numpy``) installed, the file is skipped — consistent with the other
prototype skips, so the suite stays green even without the prototype extras.

The module lives in the prototype (``prototype/mp_lite/h5ad_source.py``)
and is loaded by file path (no regular import — consistent with
``test_encodings.py``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# anndata/numpy sind optionale Prototyp-Abhängigkeiten -> ohne sie überspringen.
# EN: anndata/numpy are optional prototype dependencies -> skip without them.
np = pytest.importorskip("numpy")
ad = pytest.importorskip("anndata")
pd = pytest.importorskip("pandas")

_SRC_PATH = (
    Path(__file__).resolve().parents[1] / "prototype" / "mp_lite" / "h5ad_source.py"
)
_spec = importlib.util.spec_from_file_location("mp_lite_h5ad_source_test", _SRC_PATH)
h5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h5)


def _tiny_adata() -> "ad.AnnData":
    """Winziges, selbstgebautes ``.h5ad``-Äquivalent (3 Proben × 2 Gene) mit der
    für MP-lite relevanten Struktur: Oviedo-``obs``, ``var["symbol"]``, tSNE-``obsm``.

    English: Tiny, hand-built ``.h5ad`` equivalent (3 samples × 2 genes)
    with the structure relevant for MP-lite: Oviedo ``obs``,
    ``var["symbol"]``, tSNE ``obsm``.
    """
    X = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]], dtype="float32")
    obs = pd.DataFrame(
        {
            "sample_type": ["Primary Tumor", "Primary Tumor", "Solid Tissue Normal"],
            "submitter_id": ["TCGA-AA-0001", "TCGA-AA-0002", "TCGA-AA-0003"],
            "project_id": ["TCGA-BRCA", "TCGA-BRCA", "TCGA-PAAD"],
            "race": ["white", "asian", "white"],
            "sex_at_birth": ["female", "male", "female"],
            "ethnicity": [None, "not hispanic or latino", None],
            "vital_status": ["Alive", "Dead", "Alive"],
            "tumor_stage": ["Stage I", "Stage II", "Stage III"],
            "morphology": ["8500/3", "8500/3", "8140/3"],
            "site_of_resection_or_biopsy": ["Breast, NOS", "Breast, NOS", "Pancreas"],
            "has_metastasis": ["No", "Yes", "No"],
            "primary_diagnosis": ["Duct carcinoma", "Duct carcinoma", "Adenocarcinoma"],
            "age_at_diagnosis": [20000, 25000, 30000],
            "cancer": ["BRCA", "BRCA", "PAAD"],
        },
        index=pd.Index(["s-1", "s-2", "s-3"], name="sample_id"),
    )
    var = pd.DataFrame(
        {"symbol": ["CA9", "SAA1"]},
        index=pd.Index(["ENSG1", "ENSG2"], name="feature_id"),
    )
    a = ad.AnnData(X=X, obs=obs, var=var)
    a.obsm["X_tsne_genes"] = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
    return a


# --- Pfad-Auflösung --------------------------------------------------------
# EN: --- Path resolution ---
def test_default_path_points_at_reference_h5ad() -> None:
    p = h5.default_h5ad_path()
    assert p.parts[-3:] == ("mediator", "sample_data", "tcga_brca_sample.h5ad")


def test_resolve_path_prefers_explicit_over_env(monkeypatch) -> None:
    monkeypatch.setenv(h5.ENV_VAR, "env/path.h5ad")
    assert h5.resolve_h5ad_path("explicit/x.h5ad") == Path("explicit/x.h5ad")
    # ohne explizites Argument gewinnt die ENV / EN: without an explicit argument, ENV wins
    assert h5.resolve_h5ad_path() == Path("env/path.h5ad")


def test_resolve_prefers_existing_pancancer_over_brca_default(monkeypatch, tmp_path) -> None:
    """Aufgabe 10: vorhandene pancancer.h5ad wird dem BRCA-Default vorgezogen —
    aber explizites Argument und ENV haben weiterhin Vorrang.

    English: Task 10: an existing pancancer.h5ad is preferred over the BRCA
    default — but an explicit argument and ENV still take precedence.
    """
    monkeypatch.delenv(h5.ENV_VAR, raising=False)
    pancancer = tmp_path / "pancancer.h5ad"
    monkeypatch.setattr(h5, "pancancer_h5ad_path", lambda: pancancer)

    # (a) Datei fehlt -> BRCA-Default / EN: (a) file missing -> BRCA default
    assert h5.resolve_h5ad_path() == h5.default_h5ad_path()

    # (b) Datei existiert -> Pancancer gewinnt / EN: (b) file exists -> pancancer wins
    pancancer.write_bytes(b"")
    assert h5.resolve_h5ad_path() == pancancer

    # (c) ENV schlägt selbst eine vorhandene Pancancer-Datei / EN: (c) ENV beats even an existing pancancer file
    monkeypatch.setenv(h5.ENV_VAR, "env/path.h5ad")
    assert h5.resolve_h5ad_path() == Path("env/path.h5ad")
    # (d) explizites Argument schlägt alles / EN: (d) an explicit argument beats everything
    assert h5.resolve_h5ad_path("explicit/x.h5ad") == Path("explicit/x.h5ad")


# --- load_h5ad -------------------------------------------------------------
# EN: --- load_h5ad ---
def test_load_missing_file_returns_none() -> None:
    assert h5.load_h5ad("does/not/exist.h5ad") is None


def test_load_roundtrip(tmp_path) -> None:
    p = tmp_path / "tiny.h5ad"
    _tiny_adata().write_h5ad(p)
    a = h5.load_h5ad(p)
    assert a is not None
    assert a.shape == (3, 2)


# --- points_from_obs -------------------------------------------------------
# EN: --- points_from_obs ---
def test_points_from_obs_columns_and_values() -> None:
    pts = h5.points_from_obs(_tiny_adata())
    assert len(pts) == 3
    row0 = pts[0]
    # alle Oviedo-Felder + sample_id + tumor vorhanden
    # EN: all Oviedo fields + sample_id + tumor present
    for col in (
        "sample_type", "submitter_id", "project_id", "race", "sex_at_birth", "ethnicity",
        "vital_status", "tumor_stage", "morphology", "site_of_resection_or_biopsy",
        "has_metastasis", "primary_diagnosis", "age_at_diagnosis", "cancer",
        "sample_id", "tumor",
    ):
        assert col in row0
    # tumor == submitter_id (Case-Barcode)
    # EN: tumor == submitter_id (case barcode)
    assert row0["tumor"] == "TCGA-AA-0001"
    assert row0["cancer"] == "BRCA"
    assert row0["sample_id"] == "s-1"
    # fehlender Wert (NaN/None) -> None / EN: missing value (NaN/None) -> None
    assert row0["ethnicity"] is None
    # numpy-Skalar wurde zu Python-int/str vereinfacht / EN: numpy scalar was simplified to Python int/str
    assert isinstance(row0["age_at_diagnosis"], int)


# --- marker_column ---------------------------------------------------------
# EN: --- marker_column ---
def test_marker_column_found_and_missing() -> None:
    a = _tiny_adata()
    ca9 = h5.marker_column(a, "CA9")
    assert ca9 is not None
    assert list(ca9) == [1.0, 2.0, 3.0]        # erste X-Spalte / EN: first X column
    saa1 = h5.marker_column(a, "SAA1")
    assert list(saa1) == [10.0, 20.0, 30.0]    # zweite X-Spalte / EN: second X column
    # unbekanntes Symbol -> None / EN: unknown symbol -> None
    assert h5.marker_column(a, "NOSUCHGENE") is None


# --- layout ----------------------------------------------------------------
# EN: --- layout ---
def test_layout_present_and_absent() -> None:
    a = _tiny_adata()
    g = h5.layout(a, "X_tsne_genes")
    assert g is not None
    assert g.shape == (3, 2)
    # nicht vorhandenes obsm -> None (Fixture hat kein miRNA-tSNE)
    # EN: obsm not present -> None (fixture has no miRNA tSNE)
    assert h5.layout(a, "X_tsne_mirna") is None


# --- Referenz-.h5ad (falls vorhanden) -------------------------------------
# EN: --- Reference .h5ad (if present) ---
def test_reference_h5ad_if_present() -> None:
    a = h5.load_h5ad()  # Default: mediator/sample_data/tcga_brca_sample.h5ad / EN: default: mediator/sample_data/tcga_brca_sample.h5ad
    if a is None:
        pytest.skip("Referenz-.h5ad nicht vorhanden (nur Mediator-Artefakt).")
    pts = h5.points_from_obs(a)
    assert pts and all("tumor" in p for p in pts)
    # das Referenz-Fixture enthält CA9; ein Fantasie-Symbol nicht.
    # EN: the reference fixture contains CA9; a made-up symbol does not.
    assert h5.marker_column(a, "CA9") is not None
    assert h5.marker_column(a, "NOSUCHGENE") is None
