"""Lesender Zugriff auf das Wissensnetz — **ohne jeden Qt-Import**.

Wie ``mediator_client.py`` bleibt dieses Modul ohne Bildschirm testbar: es gibt
einfache Python-Daten zurueck (``dict``/``list``), keine Widgets und keine
rdflib-Objekte. Gelesen wird ueber das Paket ``wissensnetz`` im eigenen Prozess
(ADR-0004, Punkt 3) — **kein** zusaetzlicher Endpunkt im Mediator.

Geschrieben wird hier nichts. Der Store gehoert dem Mediator; die Oberflaeche
liest ihn nur an.

Zum Zuschnitt: der Store weiss nicht, welcher Fall aus welchem Aufruf kam — der
Mediator laedt alles in den Default-Graph und ruft ``write_selection`` nie auf,
es gibt also weder Manifest noch Named Graph. "Was ist neu" kann deshalb nur die
Oberflaeche selbst wissen, ueber zwei Abzuege und :func:`diff`.
"""

from __future__ import annotations

from typing import Any

from wissensnetz.graphstore import GraphStore

# Zustaende eines Knotens im Vergleich zweier Abzuege.
NEU = "neu"
GEWACHSEN = "gewachsen"
UNVERAENDERT = "unveraendert"

# --- Die drei Abfragen -------------------------------------------------------
# a) Wurzel: wie viele Faelle und Kohorten stehen ueberhaupt im Store.
QUERY_ROOT = """\
PREFIX db: <http://databridge.hka/onto#>
SELECT (COUNT(DISTINCT ?case) AS ?cases) (COUNT(DISTINCT ?project) AS ?projects)
WHERE {
  ?case a db:Case .
  OPTIONAL { ?case db:belongsToProject ?project }
}
"""

# b) Kohorten mit ihrer Fallzahl.
QUERY_COHORTS = """\
PREFIX db: <http://databridge.hka/onto#>
SELECT ?projectId (COUNT(DISTINCT ?case) AS ?cases)
WHERE {
  ?project a db:Project ; db:projectId ?projectId .
  ?case db:belongsToProject ?project .
}
GROUP BY ?projectId
"""

# c) Attribute je Kohorte, in EINEM Aufruf fuer alle Kohorten.
#
# Diese Abfrage **kennt die Attributliste nicht** — und das muss so bleiben:
# legt ``resolve_attribute()`` im Mediator dynamisch eine neue Property an,
# erscheint sie hier von allein. Also keine Liste von Properties einbauen, auch
# nicht "zur Sicherheit".
#
# ``isLiteral(?v)`` erledigt zwei Dinge nebenbei, die sonst beim naechsten
# Anfassen "aufgeraeumt" wuerden: es wirft die Rueckverweise
# (db:isDemographicOf, db:describesCase) heraus und laesst die NCIt-IRI aus
# db:primaryDiagnosis weg, waehrend der Text aus db:primaryDiagnosisLabel bleibt.
QUERY_ATTRIBUTES = """\
PREFIX db:  <http://databridge.hka/onto#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?projectId ?p (COUNT(DISTINCT ?case) AS ?cases) (COUNT(DISTINCT ?v) AS ?values)
WHERE {
  ?case a db:Case ; db:belongsToProject ?project .
  ?project db:projectId ?projectId .
  ?case db:hasDemographic|db:hasDiagnosis|db:hasSample ?entity .
  ?entity ?p ?v .
  FILTER(isLiteral(?v))
  FILTER(?p != rdf:type)
}
GROUP BY ?projectId ?p
"""


def default_store() -> GraphStore:
    """Ein :class:`GraphStore` mit den Einstellungen aus der Umgebung.

    ``GRAPH_DB_HOST`` hat die Vorgabe ``localhost``; der Container-Name
    ``graph-db`` gilt nur innerhalb von Compose. Die Oberflaeche laeuft als
    Host-Prozess und braucht deshalb keine Sonderbehandlung.
    """
    return GraphStore()


def store_url(store: GraphStore) -> str:
    """Die Basis-URL des Stores — fuer die Meldung "nicht erreichbar"."""
    return store.settings.base_url


def is_reachable(store: GraphStore) -> bool:
    """Reicht :meth:`GraphStore.is_reachable` durch."""
    return store.is_reachable()


# --- Abzug -------------------------------------------------------------------
def _zahl(zeile: dict[str, Any], name: str) -> int:
    """Einen Zaehlwert aus einer SPARQL-Zeile holen; fehlt er, ist er 0.

    COUNT liefert die Zahl als Zeichenkette ("20"), und bei leerem Store kann
    die Bindung ganz fehlen — beides darf keinen KeyError geben.
    """
    try:
        return int(zeile.get(name) or 0)
    except (TypeError, ValueError):
        return 0


def local_name(iri: str) -> str:
    """Der lokale Teil einer Property-IRI (``…onto#sexAtBirth`` -> ``sexAtBirth``)."""
    for trenner in ("#", "/"):
        if trenner in iri:
            iri = iri.rsplit(trenner, 1)[-1]
    return iri


def leerer_abzug() -> dict[str, Any]:
    """Ein wohlgeformter Abzug ohne Inhalt — die Form, auf die sich alles
    Weitere verlassen darf."""
    return {"cases": 0, "projects": 0, "cohorts": {}}


def snapshot(store: GraphStore) -> dict[str, Any]:
    """Der vollstaendige Abzug des Stores aus genau drei Abfragen.

    Form::

        {"cases": 20, "projects": 1,
         "cohorts": {"TCGA-BRCA": {"cases": 20,
                                   "attributes": {"sexAtBirth": {"cases": 20,
                                                                 "values": 2}}}}}
    """
    abzug = leerer_abzug()

    zeilen = store.query(QUERY_ROOT)
    if zeilen:
        abzug["cases"] = _zahl(zeilen[0], "cases")
        abzug["projects"] = _zahl(zeilen[0], "projects")

    for zeile in store.query(QUERY_COHORTS):
        projekt = zeile.get("projectId")
        if not projekt:
            continue
        abzug["cohorts"][projekt] = {
            "cases": _zahl(zeile, "cases"),
            "attributes": {},
        }

    for zeile in store.query(QUERY_ATTRIBUTES):
        projekt = zeile.get("projectId")
        eigenschaft = zeile.get("p")
        if not projekt or not eigenschaft:
            continue
        # Eine Kohorte, die nur in c) auftaucht, trotzdem aufnehmen: die Form
        # des Abzugs soll nicht davon abhaengen, welche Abfrage zuerst lief.
        kohorte = abzug["cohorts"].setdefault(projekt, {"cases": 0, "attributes": {}})
        kohorte["attributes"][local_name(eigenschaft)] = {
            "cases": _zahl(zeile, "cases"),
            "values": _zahl(zeile, "values"),
        }

    return abzug


# --- Vergleich ---------------------------------------------------------------
def _zustand(vorher: int | None, nachher: int) -> dict[str, Any]:
    """Zustand und Zuwachs eines einzelnen Knotens."""
    if vorher is None:
        return {"state": NEU, "plus": nachher}
    if nachher > vorher:
        return {"state": GEWACHSEN, "plus": nachher - vorher}
    return {"state": UNVERAENDERT, "plus": 0}


def diff(vorher: dict[str, Any] | None, nachher: dict[str, Any] | None) -> dict[str, Any]:
    """Zwei Abzuege vergleichen: was ist neu, was ist gewachsen.

    Die Markierung gilt fuer **den letzten Aufruf** und wird nicht gespeichert.
    Eine Historie ueber die Sitzung hinaus waere erfunden, weil der Store sie
    nicht hergibt.
    """
    vorher = vorher or leerer_abzug()
    nachher = nachher or leerer_abzug()

    # Die Wurzel gilt als neu, wenn vorher ueberhaupt nichts im Store stand.
    alt_gesamt = vorher.get("cases", 0)
    unterschied: dict[str, Any] = {
        "root": _zustand(alt_gesamt if alt_gesamt else None, nachher.get("cases", 0)),
        "cohorts": {},
        "attributes": {},
    }
    if not nachher.get("cases"):
        unterschied["root"] = {"state": UNVERAENDERT, "plus": 0}

    alte_kohorten = vorher.get("cohorts") or {}
    for projekt, daten in (nachher.get("cohorts") or {}).items():
        alt = alte_kohorten.get(projekt)
        unterschied["cohorts"][projekt] = _zustand(
            None if alt is None else alt.get("cases", 0), daten.get("cases", 0)
        )

        alte_attribute = (alt or {}).get("attributes") or {}
        je_attribut: dict[str, Any] = {}
        for name, werte in (daten.get("attributes") or {}).items():
            altes = alte_attribute.get(name)
            je_attribut[name] = _zustand(
                None if altes is None else altes.get("cases", 0), werte.get("cases", 0)
            )
        unterschied["attributes"][projekt] = je_attribut

    return unterschied


# --- Reihenfolge -------------------------------------------------------------
# Neu zuerst, dann gewachsen, dann nach Fallzahl absteigend. Das ist nicht
# Kosmetik: die Reihen zeigen hoechstens sieben Knoten, und eine neue Kohorte
# darf nie hinter "… N weitere" verschwinden.
_RANG = {NEU: 0, GEWACHSEN: 1, UNVERAENDERT: 2}


def _sortiere(eintraege: dict[str, Any], zustaende: dict[str, Any]) -> list[str]:
    def schluessel(name: str) -> tuple[int, int, str]:
        zustand = (zustaende or {}).get(name, {}).get("state", UNVERAENDERT)
        return (_RANG.get(zustand, 2), -(eintraege[name].get("cases", 0)), name)

    return sorted(eintraege, key=schluessel)


def sortierte_kohorten(abzug: dict[str, Any],
                       unterschied: dict[str, Any] | None = None) -> list[str]:
    """Die Kohorten in Anzeigereihenfolge."""
    return _sortiere(abzug.get("cohorts") or {}, (unterschied or {}).get("cohorts") or {})


def sortierte_attribute(abzug: dict[str, Any], projekt: str,
                        unterschied: dict[str, Any] | None = None) -> list[str]:
    """Die Attribute einer Kohorte in Anzeigereihenfolge."""
    kohorte = (abzug.get("cohorts") or {}).get(projekt) or {}
    zustaende = ((unterschied or {}).get("attributes") or {}).get(projekt) or {}
    return _sortiere(kohorte.get("attributes") or {}, zustaende)


# --- Namen: Store-Property oder Panel-Attribut -------------------------------
def _camel(panel_name: str) -> str:
    """``sex_at_birth`` -> ``sexAtBirth``."""
    kopf, *rest = panel_name.split("_")
    return kopf + "".join(teil[:1].upper() + teil[1:] for teil in rest)


def panel_name(local: str, panel_namen: list[str]) -> str | None:
    """Der Panel-Name zu einer Store-Property — **nur bei exakter Deckung**.

    Das Panel schreibt ``sex_at_birth``, der Store traegt ``db:sexAtBirth``. Die
    Uebersetzung gehoert dem Mediator (``KNOWN_ATTRIBUTES``), den die Oberflaeche
    nicht importieren darf. Also die mechanische Regel: camelCase des
    Panel-Namens muss dem lokalen Namen genau entsprechen, sonst gibt es keine
    Zweitzeile.

    Damit bleiben zwei der elf ohne Zweitzeile, und das ist richtig so:
    ``has_metastasis`` liegt als ``db:metastasisAtDiagnosis`` im Store,
    ``primary_diagnosis`` als ``db:primaryDiagnosisLabel``. Eine halb stimmende
    Rueckuebersetzung waere genau die Sorte stiller Fehlzuordnung, die uns schon
    das tote GDC-Feld ``gender`` eingebrockt hat.
    """
    for name in panel_namen or []:
        if _camel(name) == local:
            return name
    return None


# --- Auf die Auswahl im Panel einschraenken --------------------------------
def store_property(panel: str, zuordnung: dict[str, str] | None = None) -> str:
    """Unter welcher Property ein Panel-Attribut im Store liegt.

    Neun der elf ergeben sich mechanisch aus dem camelCase des Panel-Namens;
    ``primary_diagnosis`` und ``has_metastasis`` nicht. Die beiden stehen
    deshalb ausdruecklich als ``store_property`` in ``config/panel.json`` —
    geraten wird hier nichts (siehe :func:`panel_name` zur selben Frage in der
    Gegenrichtung).
    """
    return (zuordnung or {}).get(panel) or _camel(panel)


def auswahl_abzug(abzug: dict[str, Any], kohorten: str | list[str],
                  attribute: list[str],
                  zuordnung: dict[str, str] | None = None) -> dict[str, Any]:
    """Einen Abzug auf die Auswahl im Panel einschraenken.

    Gezeigt werden genau die gewaehlten Kohorten mit genau den angehakten
    Attributen — nicht alles, was im Store liegt. Die **Zahlen** kommen
    weiterhin aus dem Store; was noch nie abgerufen wurde, steht mit 0 da,
    statt zu fehlen. So sieht man vor dem Klick, was die Auswahl im Netz
    bewegen wird.

    Die Schluessel bleiben die Store-Namen, damit ein Vergleich aus
    :func:`diff` weiterhin passt.
    """
    # Eine einzelne Kohorte darf auch als Zeichenkette kommen; ohne diese Zeile
    # liefe sie als Liste ihrer Buchstaben durch.
    if isinstance(kohorten, str):
        kohorten = [kohorten] if kohorten else []
    if not kohorten:
        return leerer_abzug()

    gefiltert: dict[str, Any] = {}
    gesamt = 0
    for kohorte in kohorten:
        vorhanden = (abzug.get("cohorts") or {}).get(kohorte) or {}
        im_store = vorhanden.get("attributes") or {}

        gewaehlt: dict[str, Any] = {}
        for panel in attribute:
            name = store_property(panel, zuordnung)
            gewaehlt[name] = im_store.get(name) or {"cases": 0, "values": 0}

        faelle = vorhanden.get("cases", 0)
        gesamt += faelle
        gefiltert[kohorte] = {"cases": faelle, "attributes": gewaehlt}

    return {"cases": gesamt, "projects": len(gefiltert), "cohorts": gefiltert}
