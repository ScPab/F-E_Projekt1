"""Was gerade im Hintergrund passiert — als Stationenkette, **ohne Qt-Import**.

Dasselbe Muster wie ``store_reader.py`` und ``morph.py``: die Ableitung steht
getrennt von der Zeichnung und ist damit ohne Bildschirm testbar.

**Was diese Ansicht ehrlich zeigen kann.** Die Oberflaeche hoert den Mediator
nicht mit: es gibt keinen Fortschrittskanal, nur einen HTTP-Aufruf, der laeuft,
und eine Antwort, die kommt. Waehrend des Aufrufs steht deshalb fest, *dass*
Mediator und Wrapper arbeiten, nicht wie weit sie sind. Alles Genauere —
Tripelzahl, fehlgeschlagene Kohorten, ``.h5ad`` — ist **Beleg aus der Antwort**,
nicht Mitschnitt. Die Ansicht sagt das auch dazu; eine erfundene
Fortschrittsanzeige waere genau die Sorte Behauptung, die man spaeter glaubt.

Die Stationen folgen ``docs/DataBridge_Architektur.drawio``, benennen aber
**Komponenten statt Personen**: wer gerade welchen Teil betreut, gehoert in die
Projektdoku, nicht in eine Oberflaeche, die spaeter jemand anders bedient. Das
Diagramm ist vom 31.08. und an zwei Stellen ueberholt — ``anndata`` und der
Rueckkanal stehen dort als "geplant", anndata laeuft inzwischen. Hier steht der
Stand von heute.

English: What is currently happening in the background — as a chain of
stations, **without a Qt import**.

Same pattern as ``store_reader.py`` and ``morph.py``: the derivation is
kept separate from the drawing and is thereby testable without a
screen.

**What this view can honestly show.** The UI does not listen in on the
mediator: there is no progress channel, only an HTTP call that runs and
a response that arrives. While the call is running it is therefore only
established *that* the mediator and wrapper are working, not how far
along they are. Everything more precise — triple count, failed
cohorts, ``.h5ad`` — is **evidence from the response**, not a
recording. The view says so as well; a made-up progress indicator
would be exactly the kind of claim one later believes.

The stations follow ``docs/DataBridge_Architektur.drawio``, but name
**components instead of people**: who is currently responsible for
which part belongs in the project docs, not in a UI that someone else
will operate later. The diagram is from 08/31 and outdated in two
places — ``anndata`` and the feedback channel are listed there as
"planned", but anndata is running in the meantime. This file reflects
today's state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Zustaende einer Station.
# EN: States of a station.
WARTET = "wartet"
LAEUFT = "laeuft"
OK = "ok"
FEHLER = "fehler"
UEBERSPRUNGEN = "uebersprungen"

# Die Stationen, in der Reihenfolge des Ablaufs.
# EN: The stations, in the order of the flow.
AUFTRAG = "Auswahl → JSON"
MEDIATOR = "Mediator"
WRAPPER = "Wrapper → Datenquelle"
MAPPING = "GDC-JSON → RDF"
FUSEKI = "graph-db (Fuseki)"
WISSENSNETZ = "Wissensnetz"
# Die Messmatrix (.h5ad) steht bewusst NICHT in der Kette: sie ist ein
# Nebenprodukt des Generierens und bei jeder Vorschau grau - also meistens
# Rauschen. Was aus ihr wurde, sagen Statuszeile und Textausgabe.
# EN: The expression matrix (.h5ad) is deliberately NOT in the chain: it
# is a byproduct of generating and grayed out on every preview — so
# mostly noise. What became of it is reported by the status line and
# the output pane.


# Symbole, die die Ansicht je Station zeichnet (siehe architektur_view).
# EN: Symbols the view draws per station (see architektur_view).
SYM_JSON = "json"
SYM_DIENST = "dienst"
SYM_QUELLE = "quelle"
SYM_TRIPEL = "tripel"
SYM_SPEICHER = "speicher"
SYM_NETZ = "netz"


@dataclass
class Station:
    """Eine Station des Ablaufs mit ihrem Zustand und dem, was sie belegt.

    English: A station of the flow with its state and what backs it up.
    """

    name: str
    komponente: str           # welche Komponente das tut — keine Personen / EN: which component does this — no people
    symbol: str = SYM_DIENST  # welches Bild dafuer steht / EN: which image stands for it
    zustand: str = WARTET
    detail: str = ""          # was tatsaechlich passiert ist / EN: what actually happened
    beleg: str = ""           # woher das bekannt ist (Antwortfeld, eigener Abzug) / EN: how this is known (response field, own snapshot)

    @property
    def laeuft(self) -> bool:
        return self.zustand == LAEUFT


@dataclass
class Ablauf:
    """Die ganze Kette plus eine Zeile, die den Stand zusammenfasst.

    English: The whole chain plus one line summarizing the state.
    """

    stationen: list[Station] = field(default_factory=list)
    ueberschrift: str = ""

    def station(self, name: str) -> Station | None:
        return next((s for s in self.stationen if s.name == name), None)


def _leer() -> list[Station]:
    return [
        Station(AUFTRAG, "frontend/mediator_client.py", SYM_JSON),
        Station(MEDIATOR, "FastAPI · POST /selection/*", SYM_DIENST),
        Station(WRAPPER, "wrappers/gdc · GDC-API", SYM_QUELLE),
        Station(MAPPING, "app/semantic/mapping.py", SYM_TRIPEL),
        Station(FUSEKI, "Apache Jena · Default-Graph", SYM_SPEICHER),
        Station(WISSENSNETZ, "wissensnetz · SPARQL", SYM_NETZ),
    ]


def ruhend() -> Ablauf:
    """Vor dem ersten Aufruf: die Kette steht, nichts ist gelaufen.

    English: Before the first call: the chain sits idle, nothing has
    run.
    """
    return Ablauf(stationen=_leer(),
                  ueberschrift="Noch kein Aufruf. Die Kette zeigt, was beim "
                               "Abschicken der Reihe nach passiert.")


def _quellen(payload: dict[str, Any]) -> list[str]:
    return [lvl.get("source") or "?" for lvl in payload.get("levels") or []]


def laufend(payload: dict[str, Any], mode: str) -> Ablauf:
    """Waehrend des Aufrufs: der Auftrag steht, der Rest ist unterwegs.

    English: While the call is running: the request is set, the rest is
    in transit.
    """
    ebenen = payload.get("levels") or []
    erste = ebenen[0] if ebenen else {}
    stationen = _leer()

    auftrag = stationen[0]
    auftrag.zustand = OK
    auftrag.detail = (
        f"{len(erste.get('cohorts') or [])} Kohorten · "
        f"{len(erste.get('attributes') or [])} Attribute · "
        f"{payload.get('size')} Proben"
        # Ebenen nur nennen, wenn es mehr als eine gibt - sonst ist es Rauschen.
        # EN: Only mention levels if there is more than one — otherwise it is noise.
        + (f" · {len(ebenen)} Ebenen" if len(ebenen) > 1 else "")
    )
    auftrag.beleg = "im Fenster gebaut"

    was = "preview" if mode == "preview" else "generate"
    stationen[1].zustand = LAEUFT
    stationen[1].detail = f"POST /selection/{was} laeuft"
    stationen[2].zustand = LAEUFT
    stationen[2].detail = ", ".join(_quellen(payload)) or "—"

    return Ablauf(stationen=stationen,
                  ueberschrift="Der Aufruf laeuft. Die Zwischenschritte belegt "
                               "erst die Antwort — die Oberflaeche hoert den "
                               "Mediator nicht mit.")


def _zahl(levels: list[dict[str, Any]], feld: str) -> int:
    return sum(int(lvl.get(feld) or 0) for lvl in levels)


def fertig(payload: dict[str, Any], mode: str, ok: bool,
           levels: list[dict[str, Any]] | None = None,
           fehler: str = "",
           unterschied: dict[str, Any] | None = None) -> Ablauf:
    """Nach der Antwort: jede Station bekommt, was die Antwort ueber sie hergibt.

    ``unterschied`` ist der Vergleich der beiden Store-Abzuege (siehe
    ``store_reader.diff``) — das Einzige, was die Oberflaeche **selbst** gemessen
    hat, statt es der Antwort zu glauben.

    English: After the response: each station gets what the response
    yields about it.

    ``unterschied`` is the comparison of the two store snapshots (see
    ``store_reader.diff``) — the only thing the UI has **itself**
    measured, rather than trusting the response for it.
    """
    ablauf = laufend(payload, mode)
    stationen = ablauf.stationen
    levels = levels or []

    if not ok:
        stationen[1].zustand = FEHLER
        stationen[1].detail = (fehler or "Aufruf fehlgeschlagen").splitlines()[0]
        stationen[2].zustand = WARTET
        stationen[2].detail = "nicht erreicht"
        ablauf.ueberschrift = "Der Aufruf ist fehlgeschlagen."
        return ablauf

    gelungen = [lvl for lvl in levels if lvl.get("status") == "ok"]
    gescheitert = [lvl for lvl in levels if lvl.get("status") != "ok"]
    ausgefallen = sorted({c for lvl in levels for c in (lvl.get("failed_cohorts") or [])})

    # Mediator: eine Ebene kann scheitern, ohne die anderen mitzureissen
    # (ADR-0003, Entscheidung 7.2) — gescheitert ist er erst, wenn keine bleibt.
    # EN: Mediator: one level can fail without dragging the others down
    # with it (ADR-0003, decision 7.2) — it has only failed once none
    # remain.
    stationen[1].zustand = OK if gelungen else FEHLER
    schluessel = [lvl.get("recipe_key") for lvl in levels if lvl.get("recipe_key")]
    stationen[1].detail = (
        (f"{len(gelungen)} von {len(levels)} Ebenen ok" if len(levels) > 1 else "Ebene ok")
        + (f" · {schluessel[0][:10]}…" if schluessel else "")
    )
    stationen[1].beleg = "status, recipe_key"

    # Wrapper und Datenquelle
    # EN: Wrapper and data source
    quellen = ", ".join(_quellen(payload)) or "—"
    if gescheitert and not gelungen:
        stationen[2].zustand = FEHLER
        stationen[2].detail = (gescheitert[0].get("error") or "Abruf fehlgeschlagen")[:80]
    else:
        stationen[2].zustand = OK
        stationen[2].detail = quellen + (
            f" · ausgefallen: {', '.join(ausgefallen)}" if ausgefallen else "")
    stationen[2].beleg = "failed_cohorts"

    # Mapping GDC-JSON -> RDF
    # EN: Mapping GDC JSON -> RDF
    tripel = _zahl(gelungen, "triple_count")
    if tripel:
        stationen[3].zustand = OK
        stationen[3].detail = f"{tripel} Tripel erzeugt"
    else:
        stationen[3].zustand = UEBERSPRUNGEN if gelungen else WARTET
        stationen[3].detail = "kein Turtle in der Antwort"
    stationen[3].beleg = "triple_count"

    # Fuseki: der Mediator laedt bei preview UND generate (SelectionRequest.load)
    # EN: Fuseki: the mediator loads on preview AND generate (SelectionRequest.load)
    if tripel:
        stationen[4].zustand = OK
        stationen[4].detail = "in den Default-Graph geladen"
        stationen[4].beleg = "load=true, siehe ADR-0003"
    else:
        stationen[4].zustand = UEBERSPRUNGEN
        stationen[4].detail = "nichts zu laden"

    # Wissensnetz: unser eigener Abzug vorher/nachher
    # EN: Knowledge graph: our own before/after snapshot
    if unterschied:
        zuwachs = (unterschied.get("root") or {}).get("plus", 0)
        neue = [k for k, z in (unterschied.get("cohorts") or {}).items()
                if z.get("state") == "neu"]
        stationen[5].zustand = OK
        stationen[5].detail = (f"+{zuwachs} Faelle" if zuwachs else "unveraendert")
        if neue:
            stationen[5].detail += f" · neu: {', '.join(sorted(neue))}"
        stationen[5].beleg = "eigener Abzug vorher/nachher"
    else:
        stationen[5].zustand = UEBERSPRUNGEN
        stationen[5].detail = "kein Abzug (Store nicht erreichbar?)"

    if not gelungen:
        ablauf.ueberschrift = "Alle Ebenen sind gescheitert."
    elif gescheitert:
        ablauf.ueberschrift = (f"{len(gelungen)} von {len(levels)} Ebenen gelungen — "
                               "die uebrigen stehen unten im Text.")
    else:
        ablauf.ueberschrift = ("Durchgelaufen. Die Zwischenschritte sind aus der "
                               "Antwort belegt, nicht mitgehoert.")
    return ablauf
