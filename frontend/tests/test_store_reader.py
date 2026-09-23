"""Tests fuer ``store_reader`` — ohne Qt, ohne Netz, ohne Fuseki.

Der Store wird durch ein Doppel ersetzt: die drei Abfragen werden nicht wirklich
gestellt, sondern anhand ihres Textes wiedererkannt und mit vorbereiteten Zeilen
beantwortet. Damit prueft der Test die Auswertung, nicht Fuseki.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import store_reader as sr  # noqa: E402


class StoreDoppel:
    """Antwortet auf die drei Abfragen aus ``store_reader`` mit festen Zeilen."""

    def __init__(self, wurzel=None, kohorten=None, attribute=None) -> None:
        self._wurzel = wurzel or []
        self._kohorten = kohorten or []
        self._attribute = attribute or []
        self.gestellt: list[str] = []

    def query(self, sparql: str):
        self.gestellt.append(sparql)
        if "?projectId ?p" in sparql:
            return self._attribute
        if "GROUP BY ?projectId" in sparql:
            return self._kohorten
        return self._wurzel


def _abzug(cases: int, cohorts: dict) -> dict:
    return {"cases": cases, "projects": len(cohorts), "cohorts": cohorts}


def _kohorte(cases: int, **attribute) -> dict:
    return {"cases": cases,
            "attributes": {name: {"cases": n, "values": v}
                           for name, (n, v) in attribute.items()}}


# --- Abzug -------------------------------------------------------------------
def test_snapshot_auf_leerem_store_ist_wohlgeformt() -> None:
    """Leerer Store heisst leerer Abzug, nicht KeyError."""
    abzug = sr.snapshot(StoreDoppel())
    assert abzug == {"cases": 0, "projects": 0, "cohorts": {}}


def test_snapshot_stellt_genau_drei_abfragen() -> None:
    doppel = StoreDoppel()
    sr.snapshot(doppel)
    assert len(doppel.gestellt) == 3


def test_snapshot_fuehrt_kohorten_und_attribute_zusammen() -> None:
    doppel = StoreDoppel(
        wurzel=[{"cases": "20", "projects": "1"}],
        kohorten=[{"projectId": "TCGA-BRCA", "cases": "20"}],
        attribute=[
            {"projectId": "TCGA-BRCA",
             "p": "http://databridge.hka/onto#sexAtBirth",
             "cases": "20", "values": "2"},
        ],
    )
    abzug = sr.snapshot(doppel)
    assert abzug["cases"] == 20
    assert abzug["cohorts"]["TCGA-BRCA"]["cases"] == 20
    # Der lokale Name, nicht die volle IRI.
    assert abzug["cohorts"]["TCGA-BRCA"]["attributes"] == {
        "sexAtBirth": {"cases": 20, "values": 2}
    }


def test_snapshot_vertraegt_fehlende_zaehlwerte() -> None:
    doppel = StoreDoppel(wurzel=[{}], kohorten=[{"projectId": "TCGA-BRCA"}])
    abzug = sr.snapshot(doppel)
    assert abzug["cases"] == 0
    assert abzug["cohorts"]["TCGA-BRCA"]["cases"] == 0


# --- Vergleich ---------------------------------------------------------------
def test_diff_erkennt_neu_gewachsen_und_unveraendert() -> None:
    vorher = _abzug(30, {"TCGA-BRCA": _kohorte(20), "TCGA-KIRC": _kohorte(10)})
    nachher = _abzug(70, {"TCGA-BRCA": _kohorte(50),
                          "TCGA-KIRC": _kohorte(10),
                          "TCGA-LUAD": _kohorte(10)})
    unterschied = sr.diff(vorher, nachher)

    assert unterschied["cohorts"]["TCGA-LUAD"] == {"state": sr.NEU, "plus": 10}
    assert unterschied["cohorts"]["TCGA-BRCA"] == {"state": sr.GEWACHSEN, "plus": 30}
    assert unterschied["cohorts"]["TCGA-KIRC"] == {"state": sr.UNVERAENDERT, "plus": 0}


def test_diff_erkennt_neues_attribut_unter_bekannter_kohorte() -> None:
    """Gleiche Kohorte, neue Frage — genau das bildet das Trigger-Modell ab."""
    vorher = _abzug(20, {"TCGA-BRCA": _kohorte(20, sexAtBirth=(20, 2))})
    nachher = _abzug(20, {"TCGA-BRCA": _kohorte(20, sexAtBirth=(20, 2),
                                                vitalStatus=(20, 2))})
    unterschied = sr.diff(vorher, nachher)

    assert unterschied["cohorts"]["TCGA-BRCA"]["state"] == sr.UNVERAENDERT
    je_attribut = unterschied["attributes"]["TCGA-BRCA"]
    assert je_attribut["vitalStatus"]["state"] == sr.NEU
    assert je_attribut["sexAtBirth"]["state"] == sr.UNVERAENDERT


def test_diff_auf_leerem_vorher_macht_die_wurzel_neu() -> None:
    unterschied = sr.diff(sr.leerer_abzug(), _abzug(20, {"TCGA-BRCA": _kohorte(20)}))
    assert unterschied["root"] == {"state": sr.NEU, "plus": 20}


def test_diff_ohne_faelle_markiert_die_wurzel_nicht() -> None:
    unterschied = sr.diff(sr.leerer_abzug(), sr.leerer_abzug())
    assert unterschied["root"]["state"] == sr.UNVERAENDERT


# --- Reihenfolge -------------------------------------------------------------
def test_sortierung_neu_vor_gewachsen_vor_fallzahl() -> None:
    """Eine neue Kohorte darf nie hinter '… N weitere' verschwinden."""
    vorher = _abzug(1100, {"TCGA-BRCA": _kohorte(1000), "TCGA-KIRC": _kohorte(100)})
    nachher = _abzug(1160, {"TCGA-BRCA": _kohorte(1000),   # unveraendert, aber gross
                            "TCGA-KIRC": _kohorte(150),    # gewachsen
                            "TCGA-LUAD": _kohorte(10)})    # neu, aber klein
    unterschied = sr.diff(vorher, nachher)

    assert sr.sortierte_kohorten(nachher, unterschied) == [
        "TCGA-LUAD", "TCGA-KIRC", "TCGA-BRCA",
    ]


def test_sortierung_ohne_vergleich_geht_nach_fallzahl() -> None:
    abzug = _abzug(60, {"TCGA-BRCA": _kohorte(10), "TCGA-LUAD": _kohorte(50)})
    assert sr.sortierte_kohorten(abzug) == ["TCGA-LUAD", "TCGA-BRCA"]


def test_attribute_werden_ebenso_sortiert() -> None:
    vorher = _abzug(20, {"TCGA-BRCA": _kohorte(20, sexAtBirth=(20, 2))})
    nachher = _abzug(20, {"TCGA-BRCA": _kohorte(20, sexAtBirth=(20, 2),
                                                vitalStatus=(5, 2))})
    unterschied = sr.diff(vorher, nachher)
    assert sr.sortierte_attribute(nachher, "TCGA-BRCA", unterschied) == [
        "vitalStatus", "sexAtBirth",
    ]


# --- Namensregel -------------------------------------------------------------
PANEL_NAMEN = [
    "sex_at_birth", "race", "ethnicity", "vital_status",
    "primary_diagnosis", "age_at_diagnosis", "morphology",
    "site_of_resection_or_biopsy", "tumor_stage", "has_metastasis",
    "sample_type",
]


@pytest.mark.parametrize("local, erwartet", [
    ("sexAtBirth", "sex_at_birth"),
    ("vitalStatus", "vital_status"),
    ("siteOfResectionOrBiopsy", "site_of_resection_or_biopsy"),
    ("sampleType", "sample_type"),
])
def test_panel_name_bei_genauer_deckung(local: str, erwartet: str) -> None:
    assert sr.panel_name(local, PANEL_NAMEN) == erwartet


@pytest.mark.parametrize("local", [
    "metastasisAtDiagnosis",     # Panel: has_metastasis
    "primaryDiagnosisLabel",     # Panel: primary_diagnosis
])
def test_panel_name_raet_nicht(local: str) -> None:
    """Zwei der elf bleiben ohne Zweitzeile — eine halb stimmende
    Rueckuebersetzung waere genau die Sorte stiller Fehlzuordnung, die uns schon
    das tote GDC-Feld 'gender' eingebrockt hat."""
    assert sr.panel_name(local, PANEL_NAMEN) is None


# --- Einschraenkung auf die Auswahl im Panel ---------------------------------
ZUORDNUNG = {"primary_diagnosis": "primaryDiagnosisLabel",
             "has_metastasis": "metastasisAtDiagnosis"}


def test_store_property_folgt_dem_camelcase() -> None:
    assert sr.store_property("sex_at_birth", ZUORDNUNG) == "sexAtBirth"
    assert sr.store_property("site_of_resection_or_biopsy", ZUORDNUNG) == \
        "siteOfResectionOrBiopsy"


def test_store_property_nimmt_die_ausdrueckliche_zuordnung() -> None:
    """Die zwei, die nicht mechanisch folgen, stehen in config/panel.json."""
    assert sr.store_property("primary_diagnosis", ZUORDNUNG) == "primaryDiagnosisLabel"
    assert sr.store_property("has_metastasis", ZUORDNUNG) == "metastasisAtDiagnosis"


def test_auswahl_abzug_zeigt_nur_die_gewaehlte_kohorte() -> None:
    abzug = _abzug(70, {"TCGA-BRCA": _kohorte(50, sexAtBirth=(50, 2)),
                        "TCGA-LUAD": _kohorte(20, sexAtBirth=(20, 2))})
    gefiltert = sr.auswahl_abzug(abzug, "TCGA-BRCA", ["sex_at_birth"], ZUORDNUNG)
    assert list(gefiltert["cohorts"]) == ["TCGA-BRCA"]
    assert gefiltert["cases"] == 50


def test_auswahl_abzug_zeigt_nur_angehakte_attribute() -> None:
    abzug = _abzug(50, {"TCGA-BRCA": _kohorte(50, sexAtBirth=(50, 2),
                                              vitalStatus=(50, 2),
                                              primaryDiagnosisLabel=(50, 6))})
    gefiltert = sr.auswahl_abzug(abzug, "TCGA-BRCA",
                                 ["sex_at_birth", "primary_diagnosis"], ZUORDNUNG)
    assert set(gefiltert["cohorts"]["TCGA-BRCA"]["attributes"]) == {
        "sexAtBirth", "primaryDiagnosisLabel",
    }


def test_auswahl_abzug_zeigt_noch_nicht_abgerufenes_mit_null() -> None:
    """Vor dem Klick sichtbar machen, was die Auswahl bewegen wird — fehlende
    Knoten waeren dafuer nutzlos."""
    abzug = _abzug(50, {"TCGA-BRCA": _kohorte(50, sexAtBirth=(50, 2))})
    gefiltert = sr.auswahl_abzug(abzug, "TCGA-BRCA",
                                 ["sex_at_birth", "tumor_stage"], ZUORDNUNG)
    assert gefiltert["cohorts"]["TCGA-BRCA"]["attributes"]["tumorStage"] == {
        "cases": 0, "values": 0,
    }


def test_auswahl_abzug_einer_nie_abgerufenen_kohorte() -> None:
    gefiltert = sr.auswahl_abzug(_abzug(0, {}), "TCGA-LUAD", ["sex_at_birth"],
                                 ZUORDNUNG)
    assert gefiltert["cohorts"]["TCGA-LUAD"]["cases"] == 0
    assert gefiltert["cohorts"]["TCGA-LUAD"]["attributes"]["sexAtBirth"]["cases"] == 0


def test_auswahl_abzug_ohne_kohorte_ist_leer() -> None:
    assert sr.auswahl_abzug(_abzug(50, {"TCGA-BRCA": _kohorte(50)}), "",
                            ["sex_at_birth"], ZUORDNUNG) == sr.leerer_abzug()


def test_auswahl_abzug_behaelt_die_store_namen_als_schluessel() -> None:
    """Sonst faende diff() seine Eintraege nicht wieder."""
    vorher = _abzug(20, {"TCGA-BRCA": _kohorte(20, sexAtBirth=(20, 2))})
    nachher = _abzug(50, {"TCGA-BRCA": _kohorte(50, sexAtBirth=(50, 2))})
    unterschied = sr.diff(vorher, nachher)
    gefiltert = sr.auswahl_abzug(nachher, "TCGA-BRCA", ["sex_at_birth"], ZUORDNUNG)
    assert set(gefiltert["cohorts"]["TCGA-BRCA"]["attributes"]) <= set(
        unterschied["attributes"]["TCGA-BRCA"]
    )


def test_auswahl_abzug_nimmt_mehrere_kohorten() -> None:
    """Vergleichen heisst mehrere Kohorten nebeneinander — alle gewaehlten
    stehen im Netz, die uebrigen aus dem Store nicht."""
    abzug = _abzug(90, {"TCGA-BRCA": _kohorte(50, sexAtBirth=(50, 2)),
                        "TCGA-LUAD": _kohorte(30, sexAtBirth=(30, 2)),
                        "TCGA-KIRC": _kohorte(10, sexAtBirth=(10, 2))})
    gefiltert = sr.auswahl_abzug(abzug, ["TCGA-BRCA", "TCGA-LUAD"],
                                 ["sex_at_birth"], ZUORDNUNG)
    assert set(gefiltert["cohorts"]) == {"TCGA-BRCA", "TCGA-LUAD"}
    assert gefiltert["cases"] == 80          # Summe der gewaehlten, nicht 90
    assert gefiltert["projects"] == 2


def test_auswahl_abzug_mischt_bekannte_und_neue_kohorten() -> None:
    abzug = _abzug(50, {"TCGA-BRCA": _kohorte(50, sexAtBirth=(50, 2))})
    gefiltert = sr.auswahl_abzug(abzug, ["TCGA-BRCA", "TCGA-LUAD"],
                                 ["sex_at_birth"], ZUORDNUNG)
    assert gefiltert["cohorts"]["TCGA-LUAD"]["cases"] == 0
    assert gefiltert["cohorts"]["TCGA-BRCA"]["cases"] == 50


def test_auswahl_abzug_leere_liste_ist_leer() -> None:
    assert sr.auswahl_abzug(_abzug(50, {"TCGA-BRCA": _kohorte(50)}), [],
                            ["sex_at_birth"], ZUORDNUNG) == sr.leerer_abzug()


# --- Attribute ueber alle gewaehlten Kohorten --------------------------------
def test_gesamt_attribute_summiert_die_faelle() -> None:
    """Die Attribute gelten der ganzen Auswahl — im Auftrag stehen sie neben den
    Kohorten, nicht unter einer davon."""
    abzug = _abzug(70, {"TCGA-ACC": _kohorte(50, race=(50, 4), sexAtBirth=(50, 2)),
                        "TCGA-BLCA": _kohorte(20, race=(20, 3), sexAtBirth=(0, 0))})
    gesamt = sr.gesamt_attribute(abzug)
    assert gesamt["race"]["cases"] == 70
    assert gesamt["sexAtBirth"]["cases"] == 50      # eine Kohorte hat dazu nichts
    assert gesamt["race"]["kohorten"] == 2


def test_gesamt_attribute_summiert_die_werte_nicht() -> None:
    """Distinkte Werte je Kohorte lassen sich nicht addieren — 'female' in zwei
    Kohorten waere sonst zweimal gezaehlt."""
    abzug = _abzug(70, {"TCGA-ACC": _kohorte(50, sexAtBirth=(50, 2)),
                        "TCGA-BLCA": _kohorte(20, sexAtBirth=(20, 2))})
    assert sr.gesamt_attribute(abzug)["sexAtBirth"]["values"] == 0


def test_gesamt_zustand_ist_neu_wenn_es_in_einer_kohorte_neu_ist() -> None:
    vorher = _abzug(50, {"TCGA-ACC": _kohorte(50, race=(50, 4)),
                         "TCGA-BLCA": _kohorte(20)})
    nachher = _abzug(70, {"TCGA-ACC": _kohorte(50, race=(50, 4)),
                          "TCGA-BLCA": _kohorte(20, race=(20, 3))})
    unterschied = sr.diff(vorher, nachher)
    assert sr.gesamt_zustand(unterschied, "race") == {"state": sr.NEU, "plus": 20}


def test_gesamt_zustand_summiert_den_zuwachs() -> None:
    vorher = _abzug(30, {"TCGA-ACC": _kohorte(20, race=(20, 4)),
                         "TCGA-BLCA": _kohorte(10, race=(10, 3))})
    nachher = _abzug(70, {"TCGA-ACC": _kohorte(50, race=(50, 4)),
                          "TCGA-BLCA": _kohorte(20, race=(20, 3))})
    unterschied = sr.diff(vorher, nachher)
    assert sr.gesamt_zustand(unterschied, "race") == {"state": sr.GEWACHSEN, "plus": 40}
