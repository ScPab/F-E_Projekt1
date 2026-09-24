"""Tests fuer ``ablauf`` — die Stationenkette der Architekturansicht, ohne Qt.

Geprueft wird vor allem eines: dass die Ansicht **nur behauptet, was die Antwort
hergibt**. Eine Station steht auf "ok", weil ein Feld es belegt, nicht weil der
Aufruf insgesamt gelungen ist.

English: Tests for ``ablauf`` — the station chain of the architecture
view, without Qt.

Above all, one thing is checked: that the view **only claims what the
response actually yields**. A station shows "ok" because a field backs
it up, not because the call as a whole succeeded.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ablauf  # noqa: E402

AUFTRAG = {
    "levels": [{"source": "gdc", "cohorts": ["TCGA-BRCA", "TCGA-LUAD"],
                "modality": "gene_expression", "attributes": ["sex_at_birth"]}],
    "size": 20,
}


def _zustand(a: ablauf.Ablauf, name: str) -> str:
    station = a.station(name)
    assert station is not None, name
    return station.zustand


def _detail(a: ablauf.Ablauf, name: str) -> str:
    return a.station(name).detail


# --- Vor und waehrend dem Aufruf ---------------------------------------------
# EN: --- Before and during the call ---
def test_ruhend_haelt_alle_stationen_zurueck() -> None:
    a = ablauf.ruhend()
    assert len(a.stationen) == 6
    assert all(s.zustand == ablauf.WARTET for s in a.stationen)


def test_laufend_setzt_nur_den_auftrag_auf_ok() -> None:
    """Der Auftrag ist gebaut — alles Weitere ist noch unterwegs.

    English: The request is built — everything else is still in
    transit.
    """
    a = ablauf.laufend(AUFTRAG, "generate")
    assert _zustand(a, ablauf.AUFTRAG) == ablauf.OK
    assert _zustand(a, ablauf.MEDIATOR) == ablauf.LAEUFT
    assert _zustand(a, ablauf.WRAPPER) == ablauf.LAEUFT
    # Was der Mediator intern tut, weiss die Oberflaeche nicht.
    # EN: What the mediator does internally is unknown to the UI.
    assert _zustand(a, ablauf.MAPPING) == ablauf.WARTET
    assert _zustand(a, ablauf.FUSEKI) == ablauf.WARTET
    assert _zustand(a, ablauf.WISSENSNETZ) == ablauf.WARTET


def test_die_messmatrix_steht_nicht_in_der_kette() -> None:
    """Sie ist ein Nebenprodukt des Generierens und bei jeder Vorschau grau —
    also meistens Rauschen. Statuszeile und Textausgabe sagen, was aus ihr wurde.

    English: It is a byproduct of generating and grayed out on every
    preview — so mostly noise. The status line and output pane report
    what became of it.
    """
    namen = [s.name for s in ablauf.ruhend().stationen]
    assert not any("Messmatrix" in n for n in namen)


def test_auftrag_nennt_kohorten_attribute_und_proben() -> None:
    detail = _detail(ablauf.laufend(AUFTRAG, "preview"), ablauf.AUFTRAG)
    assert "2 Kohorten" in detail and "1 Attribute" in detail and "20 Proben" in detail


# --- Nach der Antwort ---------------------------------------------------------
# EN: --- After the response ---
def _ebene(**felder):
    basis = {"status": "ok", "recipe_key": "abc123def456",
             "selection": {"source": "gdc"}, "triple_count": 485}
    basis.update(felder)
    return basis


def test_fertig_belegt_jede_station_aus_der_antwort() -> None:
    a = ablauf.fertig(AUFTRAG, "generate", ok=True, levels=[_ebene(
        anndata={"n_obs": 40, "n_vars": 60660, "filename": "x.h5ad"})],
        unterschied={"root": {"state": "gewachsen", "plus": 19},
                     "cohorts": {"TCGA-LUAD": {"state": "neu", "plus": 19}}})
    assert _zustand(a, ablauf.MEDIATOR) == ablauf.OK
    assert "485 Tripel" in _detail(a, ablauf.MAPPING)
    assert _zustand(a, ablauf.FUSEKI) == ablauf.OK
    assert "+19 Faelle" in _detail(a, ablauf.WISSENSNETZ)
    assert "TCGA-LUAD" in _detail(a, ablauf.WISSENSNETZ)


def test_ohne_tripel_wird_fuseki_nicht_als_geladen_behauptet() -> None:
    """Kein triple_count heisst: es gibt keinen Beleg, dass etwas geladen wurde.

    English: No triple_count means: there is no evidence that anything
    was loaded.
    """
    a = ablauf.fertig(AUFTRAG, "preview", ok=True, levels=[_ebene(triple_count=0)])
    assert _zustand(a, ablauf.MAPPING) == ablauf.UEBERSPRUNGEN
    assert _zustand(a, ablauf.FUSEKI) == ablauf.UEBERSPRUNGEN


def test_ohne_abzug_bleibt_das_wissensnetz_ohne_aussage() -> None:
    """Ist Fuseki fuer die Oberflaeche nicht erreichbar, gibt es keinen Vergleich
    — und damit nichts zu behaupten.

    English: If Fuseki is unreachable for the UI, there is no
    comparison — and thus nothing to claim.
    """
    a = ablauf.fertig(AUFTRAG, "preview", ok=True, levels=[_ebene()], unterschied=None)
    assert _zustand(a, ablauf.WISSENSNETZ) == ablauf.UEBERSPRUNGEN


def test_eine_gescheiterte_ebene_reisst_den_mediator_nicht_mit() -> None:
    """ADR-0003, Entscheidung 7.2: Ebenen scheitern unabhaengig voneinander.

    English: ADR-0003, decision 7.2: levels fail independently of one
    another.
    """
    a = ablauf.fertig(AUFTRAG, "preview", ok=True,
                      levels=[_ebene(), _ebene(status="error", error="GEO kaputt")])
    assert _zustand(a, ablauf.MEDIATOR) == ablauf.OK
    assert "1 von 2" in _detail(a, ablauf.MEDIATOR)


def test_wenn_keine_ebene_bleibt_ist_der_mediator_gescheitert() -> None:
    a = ablauf.fertig(AUFTRAG, "preview", ok=True,
                      levels=[_ebene(status="error", error="GDC nicht erreichbar")])
    assert _zustand(a, ablauf.MEDIATOR) == ablauf.FEHLER
    assert _zustand(a, ablauf.WRAPPER) == ablauf.FEHLER


def test_ausgefallene_kohorten_stehen_am_wrapper() -> None:
    a = ablauf.fertig(AUFTRAG, "preview", ok=True,
                      levels=[_ebene(failed_cohorts=["TCGA-LUAD"])])
    assert "TCGA-LUAD" in _detail(a, ablauf.WRAPPER)


def test_ein_fehlgeschlagener_aufruf_erreicht_den_wrapper_nicht() -> None:
    a = ablauf.fertig(AUFTRAG, "preview", ok=False,
                      fehler="Verbindung zum Mediator fehlgeschlagen")
    assert _zustand(a, ablauf.MEDIATOR) == ablauf.FEHLER
    assert _zustand(a, ablauf.WRAPPER) == ablauf.WARTET
    # Der Auftrag selbst steht trotzdem - er wurde ja gebaut.
    # EN: The request itself still stands nonetheless - it was built after all.
    assert _zustand(a, ablauf.AUFTRAG) == ablauf.OK


def test_generieren_zeigt_dieselbe_kette_wie_die_vorschau() -> None:
    vorschau = [s.name for s in ablauf.fertig(AUFTRAG, "preview", ok=True,
                                              levels=[_ebene()]).stationen]
    generieren = [s.name for s in ablauf.fertig(AUFTRAG, "generate", ok=True,
                                                levels=[_ebene()]).stationen]
    assert vorschau == generieren
