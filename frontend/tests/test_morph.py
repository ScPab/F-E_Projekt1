"""Tests fuer ``morph`` — ohne Qt, ohne Bildschirm, ohne Datei auf der Platte.

Gearbeitet wird mit einem kleinen kuenstlichen ``AnnData`` im Speicher. Fehlt
``anndata`` im Testlauf, werden die Tests uebersprungen, die es brauchen; die
reine Rechnung (softmax, Skalierung) laeuft auch ohne.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import morph  # noqa: E402

# Die fuenfzehn Regler in Oviedos fester Reihenfolge und Benennung.
ERWARTETE_REIHENFOLGE = [
    "genes", "mirna", "cancer", "type", "race", "sex_at_birth", "ethnicity",
    "primary_diagnosis", "has_metastasis", "vital_status", "cancer (ver)",
    "tumor_stage (ver)", "miRNA-210-3p (hor)", "CA9 (ver)", "SAA1 (hor)",
]


def _adata(n: int = 8, *, mit_layout: bool = True, einwertig: bool = False):
    """Ein kleines AnnData im Speicher — nur so viel, wie ``morph`` liest."""
    ad = pytest.importorskip("anndata")
    pd = pytest.importorskip("pandas")

    obs = pd.DataFrame(
        {
            "submitter_id": [f"TCGA-ZZ-{i:04d}" for i in range(n)],
            "project_id": ["TCGA-BRCA"] * (n // 2) + ["TCGA-LUAD"] * (n - n // 2),
            "sex_at_birth": (["female"] * n if einwertig
                             else ["female", "male"] * (n // 2)),
            "sample_type": ["Primary Tumor", "Solid Tissue Normal"] * (n // 2),
            "vital_status": ["Alive", "Dead"] * (n // 2),
            "tumor_stage": ["stage i", "stage ii"] * (n // 2),
            "primary_diagnosis": ["A", "B"] * (n // 2),
        },
        index=[f"s{i}" for i in range(n)],
    )
    var = pd.DataFrame({"symbol": ["CA9", "SAA1"]}, index=["g1", "g2"])
    rng = np.random.default_rng(7)
    adata = ad.AnnData(X=rng.normal(size=(n, 2)), obs=obs, var=var)
    if mit_layout:
        adata.obsm["X_tsne_genes"] = rng.normal(0, 30.0, size=(n, 2))
    return adata


# --- Rechnung ----------------------------------------------------------------
def test_softmax_summiert_auf_eins() -> None:
    a = morph.softmax(np.array([0.0, 0.5, 1.0, 2.0]))
    assert a.sum() == pytest.approx(1.0)
    assert (a > 0).all()


def test_softmax_ist_bei_grossen_werten_stabil() -> None:
    """Ohne Abzug des Maximums liefe ``exp`` hier ueber."""
    a = morph.softmax(np.array([1000.0, 1001.0]))
    assert a.sum() == pytest.approx(1.0)


def test_ein_regler_auf_eins_ergibt_fast_genau_dieses_encoding() -> None:
    """Mit SENS = 10 draengt ein einzelner Regler auf 1 die uebrigen praktisch
    auf null — genau das ist der Sinn des Sensibilitaets-Koeffizienten."""
    n = 5
    erstes = np.tile([1.0, 0.0], (n, 1))
    zweites = np.tile([0.0, 1.0], (n, 1))
    modell = morph.Morphmodell(
        eintraege=[morph.Eintrag("a", encoding=erstes),
                   morph.Eintrag("b", encoding=zweites)],
        punkte=[{}] * n,
    )
    pos = morph.positionen(modell, [1.0, 0.0])
    assert pos[:, 0] == pytest.approx(np.ones(n), abs=1e-4)
    assert pos[:, 1] == pytest.approx(np.zeros(n), abs=1e-4)


def test_positionen_ohne_nutzbares_encoding_sind_null() -> None:
    modell = morph.Morphmodell(
        eintraege=[morph.Eintrag("a", grund=morph.GRUND_SPALTE)],
        punkte=[{}, {}],
    )
    assert morph.positionen(modell, [1.0]).shape == (2, 2)
    assert not morph.positionen(modell, [1.0]).any()


def test_skaliere_layout_zentriert_und_skaliert() -> None:
    arr = np.array([[100.0, 40.0], [140.0, 60.0], [180.0, 20.0]])
    skaliert = morph.skaliere_layout(arr)
    assert skaliert.mean(axis=0) == pytest.approx([0.0, 0.0], abs=1e-9)
    assert float(np.max(np.abs(skaliert))) == pytest.approx(morph.CIRCLE_SCALE)


def test_skaliere_layout_vertraegt_einen_einzigen_punkt() -> None:
    """Alle Punkte auf derselben Stelle: Division durch null waere der Absturz."""
    arr = np.array([[3.0, 3.0], [3.0, 3.0]])
    assert not morph.skaliere_layout(arr).any()


# --- Modell ------------------------------------------------------------------
def test_reihenfolge_der_fuenfzehn_eintraege() -> None:
    """Auch deaktivierte bleiben sichtbar und an ihrem Platz."""
    modell = morph.baue_encodings(_adata())
    assert [e.name for e in modell.eintraege] == ERWARTETE_REIHENFOLGE


def test_genes_startet_auf_dem_basisgewicht() -> None:
    modell = morph.baue_encodings(_adata())
    assert modell.eintraege[0].start == morph.BASE_WEIGHT
    assert all(e.start == 0.0 for e in modell.eintraege[1:])


def test_ohne_obsm_gibt_es_keine_basis_und_einen_benannten_grund() -> None:
    """Kein Layout heisst keine Karte — und keine erfundene Punktwolke."""
    modell = morph.baue_encodings(_adata(mit_layout=False))
    assert modell.hat_basis is False
    assert modell.eintraege[0].grund == "obsm 'X_tsne_genes' fehlt"
    assert modell.eintraege[1].grund == "obsm 'X_tsne_mirna' fehlt"


def test_einwertige_spalte_wird_deaktiviert_und_benannt() -> None:
    modell = morph.baue_encodings(_adata(einwertig=True))
    eintrag = next(e for e in modell.eintraege if e.name == "sex_at_birth")
    assert not eintrag.nutzbar
    assert eintrag.grund == morph.GRUND_EINWERTIG


def test_fehlende_spalte_wird_deaktiviert_und_benannt() -> None:
    modell = morph.baue_encodings(_adata())
    eintrag = next(e for e in modell.eintraege if e.name == "race")
    assert not eintrag.nutzbar
    assert eintrag.grund == morph.GRUND_SPALTE


def test_fehlender_marker_wird_deaktiviert_und_benannt() -> None:
    modell = morph.baue_encodings(_adata())
    eintrag = next(e for e in modell.eintraege if e.name == "miRNA-210-3p (hor)")
    assert not eintrag.nutzbar
    assert eintrag.grund == morph.GRUND_MARKER


def test_kohorten_kommen_aus_der_project_id() -> None:
    modell = morph.baue_encodings(_adata())
    assert set(modell.kohorten) == {"BRCA", "LUAD"}


def test_encodings_haben_die_form_der_punktzahl() -> None:
    modell = morph.baue_encodings(_adata(n=8))
    for eintrag in modell.eintraege:
        if eintrag.nutzbar:
            assert eintrag.encoding.shape == (8, 2), eintrag.name
    assert morph.positionen(modell, modell.startwerte).shape == (8, 2)
