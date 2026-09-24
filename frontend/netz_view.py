"""Das Wissensnetz als gezeichnetes Netz — drei Reihen, wie in der Skizze.

Vorlage: ``recherche/Konzept_Navigation_Ebene1.png``. Wurzel oben, darunter die
Kohorten, darunter die Attribute der aufgeklappten Kohorte; Kanten als weiche
Kurven mit einem gedaempften Etikett links an der Kantenschar.

Warum ``QGraphicsView`` und nicht die vorhandene pyvis-Ansicht: die Oberflaeche
soll gerade **kein** Browser sein (ADR-0004). Kein QtWebEngine, kein pyvis, keine
neue Abhaengigkeit — ``QtWidgets`` reicht. Und bewusst **nicht** ``graph_view``
genannt: unter ``scripts/graph_view.py`` liegt bereits die pyvis-Ansicht, und
zwei Dinge mit demselben Namen in einem Projekt sind eine Falle.

Die Form des Netzes ist die Geschichte der Aufrufe: im Store stehen genau die
Kohorten, die je angefragt wurden, und unter jeder genau die Attribute, die je
als Trigger mitgegeben wurden. Eine nie angefragte Kohorte ist nicht ausgegraut,
sie existiert nicht.

Zwei Signale, die sich nicht ins Gehege kommen: **Auswahl zeigt der Rand,
Wachstum zeigt die Farbe.**

English: The knowledge net as a drawn graph — three rows, as in the sketch.

Template: ``recherche/Konzept_Navigation_Ebene1.png``. Root at the top, the
cohorts below it, the attributes of the expanded cohort below that; edges as
soft curves with a muted label on the left of the edge bundle.

Why ``QGraphicsView`` and not the existing pyvis view: the UI is deliberately
meant to **not** be a browser (ADR-0004). No QtWebEngine, no pyvis, no new
dependency — ``QtWidgets`` is enough. And deliberately **not** named
``graph_view``: the pyvis view already lives under ``scripts/graph_view.py``,
and two things with the same name in one project are a trap.

The shape of the net is the history of the calls: the store holds exactly the
cohorts that were ever requested, and under each exactly the attributes that
were ever passed as triggers. A cohort that was never requested is not grayed
out, it does not exist.

Two signals that do not get in each other's way: **selection is shown by the
border, growth is shown by the color.**
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen, QTextOption
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

import store_reader as sr
import theme

# Rollen, unter denen ein Knoten weiss, was er ist.
# EN: Roles by which a node knows what it is.
KIND_ROLE = 0      # "root" | "cohort" | "attribute"
KEY_ROLE = 1       # projectId bzw. lokaler Property-Name / EN: projectId or local property name

KIND_ROOT = "root"
KIND_COHORT = "cohort"
KIND_ATTRIBUTE = "attribute"

# Etiketten an den Kantenscharen, wie in der Skizze.
# EN: Labels on the edge bundles, as in the sketch.
EDGE_PROJECT = "db:belongsToProject"
EDGE_ENTITY = "db:hasDemographic | db:hasDiagnosis | db:hasSample"

# Die beiden leeren Zustaende. Sie sehen sonst gleich aus und bedeuten
# Verschiedenes: ein leerer Store ist der normale Anfang nach
# `docker compose down -v`, kein Fehler.
# EN: The two empty states. They would otherwise look identical yet mean
# different things: an empty store is the normal starting point after
# `docker compose down -v`, not an error.
TEXT_LEER = ("Zu dieser Auswahl liegt noch nichts im Store.\n"
             "Jede Vorschau erweitert das Netz.")


def _anzahl(zahl: int, einzahl: str, mehrzahl: str) -> str:
    """``1 Kohorte`` statt ``1 Kohorten`` — die Zahl steht in jeder Zweitzeile.

    English: ``1 Kohorte`` (1 cohort) instead of ``1 Kohorten`` — the number
    appears in every second line.
    """
    return f"{zahl} {einzahl if zahl == 1 else mehrzahl}"


class _Knoten(QGraphicsItem):
    """Ein Knoten: abgerundetes Rechteck, fetter Titel, gedaempfte Zweitzeile.

    Gemalt statt aus Widgets zusammengesetzt, aus demselben Grund wie die Zeilen
    in ``searchable_select.py``: so kennt der Knoten seine Breite und kann den
    Titel bei Bedarf kuerzen.

    English: A node: rounded rectangle, bold title, muted second line.

    Painted instead of assembled from widgets, for the same reason as the
    rows in ``searchable_select.py``: this way the node knows its width and
    can elide the title if needed.
    """

    def __init__(self, titel: str, zweitzeile: str, dritte: str = "", *,
                 zustand: str = sr.UNVERAENDERT, offen: bool = False,
                 breite: int | None = None, hoehe: int | None = None) -> None:
        super().__init__()
        self._titel = titel
        self._zweitzeile = zweitzeile
        # Dritte Zeile nur bei den Attributknoten: dort traegt die zweite den
        # Panel-Namen (Deliverable 9) und die dritte die Zaehlungen.
        # EN: Third line only for the attribute nodes: there the second line
        # carries the panel name (deliverable 9) and the third the counts.
        self._dritte = dritte
        self._zustand = zustand
        self._offen = offen
        self._breite = breite or theme.NETZ_NODE_WIDTH
        self._hoehe = hoehe or theme.NETZ_NODE_HEIGHT

    def boundingRect(self) -> QRectF:  # noqa: D102
        return QRectF(0, 0, self._breite, self._hoehe)

    def _farben(self) -> tuple[str, str]:
        """Flaeche und Rand nach dem Zustand aus dem letzten Vergleich.

        English: Fill and border based on the state from the last comparison.
        """
        if self._zustand == sr.NEU:
            return theme.SUCCESS_BG, theme.SUCCESS
        if self._zustand == sr.GEWACHSEN:
            return theme.ACCENT_BG, theme.ACCENT
        return theme.WINDOW_BG, theme.BORDER

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        flaeche, rand = self._farben()

        stift = QPen(theme.qcolor(rand))
        # Der aufgeklappte Knoten traegt einen dickeren Rand, KEINE andere
        # Farbe — die Farbe ist fuer das Wachstum reserviert.
        # EN: The expanded node carries a thicker border, NOT a different
        # color — color is reserved for growth.
        stift.setWidth(theme.NETZ_BORDER_OPEN if self._offen else theme.BORDER_WIDTH)
        painter.setPen(stift)
        painter.setBrush(QBrush(theme.qcolor(flaeche)))
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1),
                                theme.RADIUS, theme.RADIUS)

        schrift = QFont(painter.font())
        schrift.setBold(True)
        painter.setFont(schrift)
        painter.setPen(theme.qcolor(theme.TEXT))
        metrik = painter.fontMetrics()
        innen = self._breite - 16
        painter.drawText(
            QRectF(8, 6, innen, 18),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            metrik.elidedText(self._titel, Qt.TextElideMode.ElideRight, innen),
        )

        schrift.setBold(False)
        painter.setFont(schrift)
        painter.setPen(theme.qcolor(theme.TEXT_MUTED))
        metrik = painter.fontMetrics()
        for i, zeile in enumerate((self._zweitzeile, self._dritte)):
            if not zeile:
                continue
            painter.drawText(
                QRectF(8, 24 + i * 15, innen, 15),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                metrik.elidedText(zeile, Qt.TextElideMode.ElideRight, innen),
            )


class NetzView(QGraphicsView):
    """Die Netzflaeche: zeichnet einen Abzug und markiert, was dazukam.

    Gezeigt wird **die Auswahl aus dem Panel**, nicht der ganze Store: die
    gewaehlte Kohorte und die angehakten Attribute. Die Zahlen kommen weiter aus
    dem Store, was noch nie abgerufen wurde steht mit 0 da — so sieht man vor
    dem Klick, was die Auswahl im Netz bewegen wird.

    Bedienung: Klick auf die Kohorte klappt ihre Attribute zu und wieder auf,
    Klick auf die Wurzel klappt zu. Es ist immer **hoechstens eine** Kohorte
    aufgeklappt, sonst wird Reihe 3 beliebig breit.

    **Der Klick aendert das Auswahlpanel rechts nicht.** Das Netz ist in dieser
    Fassung eine Anzeige, keine Navigation; "im Netz klicken und damit den
    naechsten Auftrag zusammenstellen" ist der zurueckgestellte Drill-down aus
    ADR-0003 und eine eigene Entscheidung.

    English: The net surface: draws a snapshot and marks what was added.

    What is shown is **the selection from the panel**, not the whole store:
    the chosen cohort and the checked attributes. The numbers still come from
    the store; anything that has never been fetched shows as 0 — so one can
    see, before clicking, what the selection will move in the net.

    Operation: clicking the cohort collapses and re-expands its attributes,
    clicking the root collapses it. At most **one** cohort is ever expanded,
    otherwise row 3 would become arbitrarily wide.

    **The click does not change the selection panel on the right.** In this
    version the net is a display, not navigation; "clicking in the net to
    assemble the next request" is the deferred drill-down from ADR-0003 and
    a separate decision.
    """

    def __init__(self, panel_namen: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(theme.OBJ_NETZ)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(theme.qcolor(theme.WINDOW_BG)))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self._panel_namen = list(panel_namen or [])
        self._abzug: dict[str, Any] = sr.leerer_abzug()
        self._unterschied: dict[str, Any] = {}
        self._offene_kohorte: str | None = None
        self._meldung: str | None = None
        self._meldung_fehler = False

        self.zeichne()

    # -- Inhalt setzen -----------------------------------------------------
    # EN: Setting content
    def offene_kohorte(self) -> str | None:
        """Welche Kohorte gerade aufgeklappt ist — das Fenster laesst sie beim
        Neuzeichnen offen, statt immer auf die erste zu springen.

        English: Which cohort is currently expanded — the window leaves it
        open when redrawing instead of always jumping back to the first one.
        """
        return self._offene_kohorte
    def zeige_abzug(self, abzug: dict[str, Any],
                    unterschied: dict[str, Any] | None = None,
                    offen: str | None = None) -> None:
        """Einen Abzug anzeigen, optional mit der Markierung des letzten Aufrufs.

        ``offen`` ist die Kohorte, auf deren Zahlen die Attributreihe
        eingeschraenkt wird. Leer heisst **alle gewaehlten Kohorten** — so
        stehen die Attribute auch im Auftrag: neben den Kohorten, nicht unter
        einer davon.

        English: Show a snapshot, optionally with the last call's markers.

        ``offen`` is the cohort to which the attribute row's numbers are
        restricted. Empty means **all selected cohorts** — that mirrors how
        the attributes also appear in the request: next to the cohorts, not
        under one of them.
        """
        self._abzug = abzug or sr.leerer_abzug()
        self._unterschied = unterschied or {}
        self._meldung = None
        self._meldung_fehler = False
        if offen is not None:
            self._offene_kohorte = offen
        # Eine Kohorte, die es nicht mehr gibt, darf nicht aufgeklappt bleiben.
        # EN: A cohort that no longer exists must not remain expanded.
        if self._offene_kohorte not in (self._abzug.get("cohorts") or {}):
            self._offene_kohorte = None
        self.zeichne()

    def zeige_hinweis(self, text: str) -> None:
        """Eine gedaempfte Meldung statt eines Netzes — etwa, solange nichts
        ausgewaehlt ist. Kein Fehler, also keine Fehlerfarbe.

        English: A muted message instead of a net — e.g. while nothing is
        selected. Not an error, so no error color.
        """
        self._abzug = sr.leerer_abzug()
        self._unterschied = {}
        self._offene_kohorte = None
        self._meldung = text
        self._meldung_fehler = False
        self.zeichne()

    def zeige_nicht_erreichbar(self, url: str) -> None:
        """Fuseki antwortet nicht — das ist ein anderer Zustand als "leer".

        English: Fuseki is not responding — that is a different state than
        "empty".
        """
        self._abzug = sr.leerer_abzug()
        self._unterschied = {}
        self._offene_kohorte = None
        self._meldung = (f"Fuseki unter {url} nicht erreichbar.\n"
                         "Laeuft `docker compose up`?")
        self._meldung_fehler = True
        self.zeichne()

    # -- Zeichnen ----------------------------------------------------------
    # EN: Drawing
    def zeichne(self) -> None:
        szene = self.scene()
        szene.clear()

        if self._meldung is not None:
            self._male_meldung(self._meldung, fehler=self._meldung_fehler)
            return
        if not (self._abzug.get("cohorts") or self._abzug.get("cases")):
            # Leer, aber erreichbar: gedaempft, KEINE Fehlerfarbe.
            # EN: Empty but reachable: muted, NOT an error color.
            self._male_meldung(TEXT_LEER, fehler=False)
            return

        kohorten = sr.sortierte_kohorten(self._abzug, self._unterschied)
        gezeigt = kohorten[:theme.NETZ_MAX_NODES]

        breite_reihe2 = self._reihenbreite(len(gezeigt))
        # Ohne aufgeklappte Kohorte gelten die Attribute der GANZEN Auswahl —
        # so stehen sie auch im Auftrag: neben den Kohorten, nicht unter einer
        # davon. Ein Klick auf eine Kohorte schraenkt sie auf deren Zahlen ein.
        # EN: Without an expanded cohort, the attributes apply to the WHOLE
        # selection — that mirrors how they also appear in the request: next
        # to the cohorts, not under one of them. A click on a cohort
        # restricts them to its numbers.
        attribute = (sr.sortierte_attribute(self._abzug, self._offene_kohorte,
                                            self._unterschied)
                     if self._offene_kohorte
                     else sr.sortierte_gesamt_attribute(self._abzug,
                                                        self._unterschied))
        gezeigte_attribute = attribute[:theme.NETZ_MAX_NODES]
        breite_reihe3 = self._reihenbreite(len(gezeigte_attribute), KIND_ATTRIBUTE)
        breite = max(breite_reihe2, breite_reihe3, theme.NETZ_NODE_WIDTH * 3)

        # Reihe 1: Wurzel. Breiter als die uebrigen Knoten — sie traegt zwei
        # Zahlen, und abgeschnitten ("18 Fa…") nuetzt die zweite nichts.
        # EN: Row 1: root. Wider than the other nodes — it carries two
        # numbers, and cut off ("18 Fa…") the second one is useless.
        wurzel = self._neuer_knoten(
            "Auswahl",
            f"{_anzahl(len(self._abzug.get('cohorts') or {}), 'Kohorte', 'Kohorten')} · "
            f"{_anzahl(self._abzug.get('cases', 0), 'Fall', 'Faelle')}",
            zustand=self._zustand_wurzel(),
            kind=KIND_ROOT,
            key="",
            breite=theme.NETZ_ROOT_WIDTH,
        )
        wurzel.setPos((breite - theme.NETZ_ROOT_WIDTH) / 2, 0)

        # Reihe 2: Kohorten.
        # EN: Row 2: cohorts.
        y2 = theme.NETZ_NODE_HEIGHT + theme.NETZ_ROW_GAP
        knoten2 = self._male_reihe(gezeigt, y2, breite, KIND_COHORT)
        for knoten in knoten2:
            self._male_kante(wurzel, knoten)
        if knoten2:
            self._male_kantenetikett(EDGE_PROJECT, y2 - theme.NETZ_ROW_GAP + 8)
        self._male_rest(len(kohorten) - len(gezeigt), "Kohorten",
                        y2 + theme.NETZ_NODE_HEIGHT + 4, breite)

        # Reihe 3: die Attribute. Ohne aufgeklappte Kohorte haengen sie an
        # allen, sonst nur an der aufgeklappten.
        # EN: Row 3: the attributes. Without an expanded cohort they hang off
        # all of them, otherwise only off the expanded one.
        if gezeigte_attribute:
            y3 = y2 + theme.NETZ_NODE_HEIGHT + theme.NETZ_ROW_GAP
            if self._offene_kohorte:
                eltern = [k for k in knoten2
                          if k.data(KEY_ROLE) == self._offene_kohorte]
            else:
                eltern = knoten2
            knoten3 = self._male_reihe(gezeigte_attribute, y3, breite, KIND_ATTRIBUTE)
            for elternknoten in eltern:
                for knoten in knoten3:
                    self._male_kante(elternknoten, knoten)
            self._male_kantenetikett(EDGE_ENTITY, y3 - theme.NETZ_ROW_GAP + 8)
            hinweis = ("" if self._offene_kohorte
                       else "Attribute gelten fuer alle gewaehlten Kohorten")
            self._male_rest(len(attribute) - len(gezeigte_attribute), "Attribute",
                            y3 + theme.NETZ_NODE_HEIGHT_3 + 4, breite,
                            zusatz=hinweis)

        szene.setSceneRect(szene.itemsBoundingRect().adjusted(-12, -12, 12, 12))
        self._einpassen()

    @staticmethod
    def _knotenbreite(kind: str) -> int:
        """Attributknoten sind breiter: sie tragen die laengste Zeile
        (``47 Faelle · 6 Werte · +29``), und abgeschnitten nuetzt der Zuwachs
        nichts.

        English: Attribute nodes are wider: they carry the longest line
        (``47 cases · 6 values · +29``), and cut off, the growth figure is
        useless.
        """
        return (theme.NETZ_NODE_WIDTH_3 if kind == KIND_ATTRIBUTE
                else theme.NETZ_NODE_WIDTH)

    def _reihenbreite(self, anzahl: int, kind: str = KIND_COHORT) -> int:
        if anzahl <= 0:
            return 0
        return (anzahl * self._knotenbreite(kind)
                + (anzahl - 1) * theme.NETZ_NODE_GAP)

    def _zustand_wurzel(self) -> str:
        return (self._unterschied.get("root") or {}).get("state", sr.UNVERAENDERT)

    def _neuer_knoten(self, titel: str, zweitzeile: str, dritte: str = "", *,
                      zustand: str, kind: str, key: str, offen: bool = False,
                      hoehe: int | None = None, breite: int | None = None) -> _Knoten:
        knoten = _Knoten(titel, zweitzeile, dritte, zustand=zustand, offen=offen,
                         hoehe=hoehe, breite=breite)
        # Der Knoten kuerzt lange Namen (`primaryDiagnosisLabel`); im Tooltip
        # steht deshalb alles ungekuerzt.
        # EN: The node elides long names (`primaryDiagnosisLabel`); the
        # tooltip therefore shows everything unabridged.
        knoten.setToolTip("\n".join(t for t in (titel, zweitzeile, dritte) if t))
        knoten.setData(KIND_ROLE, kind)
        knoten.setData(KEY_ROLE, key)
        self.scene().addItem(knoten)
        return knoten

    def _male_reihe(self, namen: list[str], y: float, breite: float,
                    kind: str) -> list[_Knoten]:
        """Eine Reihe waagerecht mittig setzen und die Knoten zurueckgeben.

        English: Center a row horizontally and return the nodes.
        """
        gesamt = self._reihenbreite(len(namen), kind)
        x = (breite - gesamt) / 2
        knoten: list[_Knoten] = []
        for name in namen:
            if kind == KIND_COHORT:
                titel, zweitzeile, dritte, zustand = self._kohorten_text(name)
            else:
                titel, zweitzeile, dritte, zustand = self._attribut_text(name)
            k = self._neuer_knoten(
                titel, zweitzeile, dritte, zustand=zustand, kind=kind, key=name,
                offen=(kind == KIND_COHORT and name == self._offene_kohorte),
                hoehe=theme.NETZ_NODE_HEIGHT_3 if kind == KIND_ATTRIBUTE else None,
                breite=self._knotenbreite(kind),
            )
            k.setPos(x, y)
            knoten.append(k)
            x += self._knotenbreite(kind) + theme.NETZ_NODE_GAP
        return knoten

    def _zusatz(self, zustand: dict[str, Any]) -> str:
        """``+N`` fuer einen gewachsenen Knoten, sonst nichts.

        English: ``+N`` for a grown node, otherwise nothing.
        """
        return f" · +{zustand['plus']}" if zustand.get("state") == sr.GEWACHSEN else ""

    def _kohorten_text(self, projekt: str) -> tuple[str, str, str, str]:
        daten = (self._abzug.get("cohorts") or {}).get(projekt) or {}
        zustand = (self._unterschied.get("cohorts") or {}).get(projekt) or {}
        return (projekt,
                f"{_anzahl(daten.get('cases', 0), 'Fall', 'Faelle')}"
                f"{self._zusatz(zustand)}",
                "",
                zustand.get("state", sr.UNVERAENDERT))

    def _attribut_text(self, name: str) -> tuple[str, str, str, str]:
        """Titel ist der **lokale Name der Property aus dem Store**; der
        Panel-Name steht nur darunter, wenn er mechanisch genau passt (siehe
        ``store_reader.panel_name``) — kein Raten, keine Tabelle.

        Ohne aufgeklappte Kohorte stehen die Faelle **aller** gewaehlten
        Kohorten zusammen; die Zahl der Werte fehlt dann, weil distinkte Werte
        je Kohorte sich nicht addieren lassen (siehe
        ``store_reader.gesamt_attribute``).

        English: The title is the **local property name from the store**;
        the panel name appears below it only when it matches mechanically
        exactly (see ``store_reader.panel_name``) — no guessing, no lookup
        table.

        Without an expanded cohort, the cases of **all** selected cohorts are
        combined; the value count is then missing, because distinct values
        per cohort cannot be summed (see ``store_reader.gesamt_attribute``).
        """
        panel = sr.panel_name(name, self._panel_namen) or ""
        if not self._offene_kohorte:
            daten = sr.gesamt_attribute(self._abzug).get(name) or {}
            zustand = sr.gesamt_zustand(self._unterschied, name)
            zaehlungen = (f"{_anzahl(daten.get('cases', 0), 'Fall', 'Faelle')} · "
                          f"{_anzahl(daten.get('kohorten', 0), 'Kohorte', 'Kohorten')}"
                          f"{self._zusatz(zustand)}")
            return name, panel, zaehlungen, zustand.get("state", sr.UNVERAENDERT)

        kohorte = (self._abzug.get("cohorts") or {}).get(self._offene_kohorte) or {}
        daten = (kohorte.get("attributes") or {}).get(name) or {}
        zustand = ((self._unterschied.get("attributes") or {})
                   .get(self._offene_kohorte) or {}).get(name) or {}
        zaehlungen = (f"{_anzahl(daten.get('cases', 0), 'Fall', 'Faelle')} · "
                      f"{_anzahl(daten.get('values', 0), 'Wert', 'Werte')}"
                      f"{self._zusatz(zustand)}")
        return name, panel, zaehlungen, zustand.get("state", sr.UNVERAENDERT)

    def _male_kante(self, oben: _Knoten, unten: _Knoten) -> None:
        """Weiche Kurve von der Unterkante des Elternknotens zur Oberkante des
        Kindes — wie in der Skizze, keine Ecken.

        English: A soft curve from the bottom edge of the parent node to the
        top edge of the child — as in the sketch, no corners.
        """
        start = QPointF(oben.pos().x() + oben.boundingRect().width() / 2,
                        oben.pos().y() + oben.boundingRect().height())
        ende = QPointF(unten.pos().x() + unten.boundingRect().width() / 2, unten.pos().y())
        pfad = QPainterPath(start)
        mitte = (start.y() + ende.y()) / 2
        pfad.cubicTo(QPointF(start.x(), mitte), QPointF(ende.x(), mitte), ende)
        kante = self.scene().addPath(pfad, QPen(theme.qcolor(theme.BORDER),
                                                theme.BORDER_WIDTH))
        # Kanten liegen hinter den Knoten, sonst schneiden sie durch die Flaeche.
        # EN: Edges sit behind the nodes, otherwise they would cut through
        # the surface.
        kante.setZValue(-1)

    def _male_kantenetikett(self, text: str, y: float) -> None:
        etikett = self.scene().addText(text)
        etikett.setDefaultTextColor(theme.qcolor(theme.TEXT_MUTED))
        schrift = QFont(etikett.font())
        schrift.setPointSizeF(max(schrift.pointSizeF() - 1, 6))
        etikett.setFont(schrift)
        etikett.setPos(0, y)

    def _male_rest(self, anzahl: int, was: str, y: float, breite: float, *,
                   zusatz: str = "") -> None:
        """``… N weitere Kohorten`` unter der Reihe, gedaempft.

        ``zusatz`` steht daneben, wenn es sonst nichts zu melden gibt — etwa der
        Hinweis, dass die Attribute fuer alle Kohorten gelten.

        English: ``… N more cohorts`` below the row, muted.

        ``zusatz`` (addendum) is shown next to it when there is otherwise
        nothing to report — e.g. the note that the attributes apply to all
        cohorts.
        """
        text = f"… {anzahl} weitere {was}" if anzahl > 0 else ""
        if zusatz:
            text = f"{text}   ·   {zusatz}" if text else zusatz
        if not text:
            return
        etikett = self.scene().addText(text)
        etikett.setDefaultTextColor(theme.qcolor(theme.TEXT_MUTED))
        etikett.setPos((breite - etikett.boundingRect().width()) / 2, y)

    def _male_meldung(self, text: str, *, fehler: bool) -> None:
        szene = self.scene()
        etikett = szene.addText(text)
        etikett.setDefaultTextColor(theme.qcolor(theme.ERROR if fehler else theme.TEXT_MUTED))
        etikett.setTextWidth(360)
        # Ohne das steht der Text linksbuendig in einem mittig gesetzten Block
        # und wirkt wie verrutscht.
        # EN: Without this, the text is left-aligned inside a centered block
        # and looks misplaced.
        option = QTextOption(Qt.AlignmentFlag.AlignHCenter)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        etikett.document().setDefaultTextOption(option)
        szene.setSceneRect(etikett.boundingRect())
        self.resetTransform()
        self.centerOn(etikett)

    # -- Groesse -----------------------------------------------------------
    # EN: Size
    def _einpassen(self) -> None:
        """Die Szene in die Flaeche einpassen, aber nie vergroessern.

        Ohne die Schranke wuerde ein Netz aus zwei Knoten bildschirmfuellend
        aufgeblasen; mit ihr bleibt es bei 900 x 600 lesbar und nichts wird
        abgeschnitten.

        English: Fit the scene into the surface, but never enlarge it.

        Without this limit, a net of two nodes would be blown up to fill the
        screen; with it, it stays readable at 900 x 600 and nothing is cut
        off.
        """
        rechteck = self.scene().sceneRect()
        if rechteck.isEmpty():
            return
        self.fitInView(rechteck, Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.0:
            self.resetTransform()
            self.centerOn(rechteck.center())

    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        if self._meldung is None:
            self._einpassen()
        else:
            self.centerOn(self.scene().sceneRect().center())

    # -- Klick -------------------------------------------------------------
    # EN: Click
    def mousePressEvent(self, event) -> None:  # noqa: D102
        knoten = self.itemAt(event.position().toPoint())
        while knoten is not None and not isinstance(knoten, _Knoten):
            knoten = knoten.parentItem()
        if knoten is not None:
            art = knoten.data(KIND_ROLE)
            if art == KIND_ROOT:
                self._offene_kohorte = None
                self.zeichne()
            elif art == KIND_COHORT:
                key = knoten.data(KEY_ROLE)
                self._offene_kohorte = None if key == self._offene_kohorte else key
                self.zeichne()
        super().mousePressEvent(event)


class NetzPanel(QWidget):
    """Die Netzflaeche als Seite der Anzeige.

    Die Titelzeile hat dieses Panel frueher selbst gebaut. Seit es eine zweite
    Ansicht gibt (Projektion), steht sie im Fenster und ueberschreibt beide —
    hier bleibt die reine Ansicht.

    English: The net surface as a page of the display.

    This panel used to build the title bar itself. Since there is a second
    view (projection), it lives in the window and spans both — here only the
    pure view remains.
    """

    def __init__(self, panel_namen: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = NetzView(panel_namen)
        layout.addWidget(self.view, stretch=1)

    # Durchreichen, damit das Fenster nur das Panel kennt.
    # EN: Pass-through, so the window only knows the panel.
    def zeige_abzug(self, abzug: dict[str, Any],
                    unterschied: dict[str, Any] | None = None,
                    offen: str | None = None) -> None:
        self.view.zeige_abzug(abzug, unterschied, offen)

    def offene_kohorte(self) -> str | None:
        return self.view.offene_kohorte()

    def zeige_hinweis(self, text: str) -> None:
        self.view.zeige_hinweis(text)

    def zeige_nicht_erreichbar(self, url: str) -> None:
        self.view.zeige_nicht_erreichbar(url)
