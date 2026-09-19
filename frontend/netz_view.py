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
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen, QTextOption
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import store_reader as sr
import theme

# Rollen, unter denen ein Knoten weiss, was er ist.
KIND_ROLE = 0      # "root" | "cohort" | "attribute"
KEY_ROLE = 1       # projectId bzw. lokaler Property-Name

KIND_ROOT = "root"
KIND_COHORT = "cohort"
KIND_ATTRIBUTE = "attribute"

# Etiketten an den Kantenscharen, wie in der Skizze.
EDGE_PROJECT = "db:belongsToProject"
EDGE_ENTITY = "db:hasDemographic | db:hasDiagnosis | db:hasSample"

# Die beiden leeren Zustaende. Sie sehen sonst gleich aus und bedeuten
# Verschiedenes: ein leerer Store ist der normale Anfang nach
# `docker compose down -v`, kein Fehler.
TEXT_LEER = ("Zu dieser Auswahl liegt noch nichts im Store.\n"
             "Jede Vorschau erweitert das Netz.")


def _anzahl(zahl: int, einzahl: str, mehrzahl: str) -> str:
    """``1 Kohorte`` statt ``1 Kohorten`` — die Zahl steht in jeder Zweitzeile."""
    return f"{zahl} {einzahl if zahl == 1 else mehrzahl}"


class _Knoten(QGraphicsItem):
    """Ein Knoten: abgerundetes Rechteck, fetter Titel, gedaempfte Zweitzeile.

    Gemalt statt aus Widgets zusammengesetzt, aus demselben Grund wie die Zeilen
    in ``searchable_select.py``: so kennt der Knoten seine Breite und kann den
    Titel bei Bedarf kuerzen.
    """

    def __init__(self, titel: str, zweitzeile: str, dritte: str = "", *,
                 zustand: str = sr.UNVERAENDERT, offen: bool = False,
                 breite: int | None = None, hoehe: int | None = None) -> None:
        super().__init__()
        self._titel = titel
        self._zweitzeile = zweitzeile
        # Dritte Zeile nur bei den Attributknoten: dort traegt die zweite den
        # Panel-Namen (Deliverable 9) und die dritte die Zaehlungen.
        self._dritte = dritte
        self._zustand = zustand
        self._offen = offen
        self._breite = breite or theme.NETZ_NODE_WIDTH
        self._hoehe = hoehe or theme.NETZ_NODE_HEIGHT

    def boundingRect(self) -> QRectF:  # noqa: D102
        return QRectF(0, 0, self._breite, self._hoehe)

    def _farben(self) -> tuple[str, str]:
        """Flaeche und Rand nach dem Zustand aus dem letzten Vergleich."""
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
    def zeige_abzug(self, abzug: dict[str, Any],
                    unterschied: dict[str, Any] | None = None,
                    offen: str | None = None) -> None:
        """Einen Abzug anzeigen, optional mit der Markierung des letzten Aufrufs.

        ``offen`` ist die Kohorte, deren Attribute gleich mitkommen sollen — das
        Netz zeigt die Auswahl aus dem Panel, und dazu gehoeren die angehakten
        Attribute, ohne dass man erst klicken muss.
        """
        self._abzug = abzug or sr.leerer_abzug()
        self._unterschied = unterschied or {}
        self._meldung = None
        self._meldung_fehler = False
        if offen is not None:
            self._offene_kohorte = offen
        # Eine Kohorte, die es nicht mehr gibt, darf nicht aufgeklappt bleiben.
        if self._offene_kohorte not in (self._abzug.get("cohorts") or {}):
            self._offene_kohorte = None
        self.zeichne()

    def zeige_hinweis(self, text: str) -> None:
        """Eine gedaempfte Meldung statt eines Netzes — etwa, solange nichts
        ausgewaehlt ist. Kein Fehler, also keine Fehlerfarbe."""
        self._abzug = sr.leerer_abzug()
        self._unterschied = {}
        self._offene_kohorte = None
        self._meldung = text
        self._meldung_fehler = False
        self.zeichne()

    def zeige_nicht_erreichbar(self, url: str) -> None:
        """Fuseki antwortet nicht — das ist ein anderer Zustand als "leer"."""
        self._abzug = sr.leerer_abzug()
        self._unterschied = {}
        self._offene_kohorte = None
        self._meldung = (f"Fuseki unter {url} nicht erreichbar.\n"
                         "Laeuft `docker compose up`?")
        self._meldung_fehler = True
        self.zeichne()

    # -- Zeichnen ----------------------------------------------------------
    def zeichne(self) -> None:
        szene = self.scene()
        szene.clear()

        if self._meldung is not None:
            self._male_meldung(self._meldung, fehler=self._meldung_fehler)
            return
        if not (self._abzug.get("cohorts") or self._abzug.get("cases")):
            # Leer, aber erreichbar: gedaempft, KEINE Fehlerfarbe.
            self._male_meldung(TEXT_LEER, fehler=False)
            return

        kohorten = sr.sortierte_kohorten(self._abzug, self._unterschied)
        gezeigt = kohorten[:theme.NETZ_MAX_NODES]

        breite_reihe2 = self._reihenbreite(len(gezeigt))
        attribute = (sr.sortierte_attribute(self._abzug, self._offene_kohorte,
                                            self._unterschied)
                     if self._offene_kohorte else [])
        gezeigte_attribute = attribute[:theme.NETZ_MAX_NODES]
        breite_reihe3 = self._reihenbreite(len(gezeigte_attribute), KIND_ATTRIBUTE)
        breite = max(breite_reihe2, breite_reihe3, theme.NETZ_NODE_WIDTH * 3)

        # Reihe 1: Wurzel. Breiter als die uebrigen Knoten — sie traegt zwei
        # Zahlen, und abgeschnitten ("18 Fa…") nuetzt die zweite nichts.
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
        y2 = theme.NETZ_NODE_HEIGHT + theme.NETZ_ROW_GAP
        knoten2 = self._male_reihe(gezeigt, y2, breite, KIND_COHORT)
        for knoten in knoten2:
            self._male_kante(wurzel, knoten)
        if knoten2:
            self._male_kantenetikett(EDGE_PROJECT, y2 - theme.NETZ_ROW_GAP + 8)
        self._male_rest(len(kohorten) - len(gezeigt), "Kohorten",
                        y2 + theme.NETZ_NODE_HEIGHT + 4, breite)

        # Reihe 3: Attribute der aufgeklappten Kohorte.
        if self._offene_kohorte and gezeigte_attribute:
            y3 = y2 + theme.NETZ_NODE_HEIGHT + theme.NETZ_ROW_GAP
            eltern = next((k for k in knoten2 if k.data(KEY_ROLE) == self._offene_kohorte),
                          None)
            knoten3 = self._male_reihe(gezeigte_attribute, y3, breite, KIND_ATTRIBUTE)
            if eltern is not None:
                for knoten in knoten3:
                    self._male_kante(eltern, knoten)
            self._male_kantenetikett(EDGE_ENTITY, y3 - theme.NETZ_ROW_GAP + 8)
            self._male_rest(len(attribute) - len(gezeigte_attribute), "Attribute",
                            y3 + theme.NETZ_NODE_HEIGHT_3 + 4, breite)

        szene.setSceneRect(szene.itemsBoundingRect().adjusted(-12, -12, 12, 12))
        self._einpassen()

    @staticmethod
    def _knotenbreite(kind: str) -> int:
        """Attributknoten sind breiter: sie tragen die laengste Zeile
        (``47 Faelle · 6 Werte · +29``), und abgeschnitten nuetzt der Zuwachs
        nichts."""
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
        knoten.setToolTip("\n".join(t for t in (titel, zweitzeile, dritte) if t))
        knoten.setData(KIND_ROLE, kind)
        knoten.setData(KEY_ROLE, key)
        self.scene().addItem(knoten)
        return knoten

    def _male_reihe(self, namen: list[str], y: float, breite: float,
                    kind: str) -> list[_Knoten]:
        """Eine Reihe waagerecht mittig setzen und die Knoten zurueckgeben."""
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
        """``+N`` fuer einen gewachsenen Knoten, sonst nichts."""
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
        ``store_reader.panel_name``) — kein Raten, keine Tabelle."""
        kohorte = (self._abzug.get("cohorts") or {}).get(self._offene_kohorte) or {}
        daten = (kohorte.get("attributes") or {}).get(name) or {}
        zustand = ((self._unterschied.get("attributes") or {})
                   .get(self._offene_kohorte) or {}).get(name) or {}
        zaehlungen = (f"{_anzahl(daten.get('cases', 0), 'Fall', 'Faelle')} · "
                      f"{_anzahl(daten.get('values', 0), 'Wert', 'Werte')}"
                      f"{self._zusatz(zustand)}")
        return (name,
                sr.panel_name(name, self._panel_namen) or "",
                zaehlungen,
                zustand.get("state", sr.UNVERAENDERT))

    def _male_kante(self, oben: _Knoten, unten: _Knoten) -> None:
        """Weiche Kurve von der Unterkante des Elternknotens zur Oberkante des
        Kindes — wie in der Skizze, keine Ecken."""
        start = QPointF(oben.pos().x() + oben.boundingRect().width() / 2,
                        oben.pos().y() + oben.boundingRect().height())
        ende = QPointF(unten.pos().x() + unten.boundingRect().width() / 2, unten.pos().y())
        pfad = QPainterPath(start)
        mitte = (start.y() + ende.y()) / 2
        pfad.cubicTo(QPointF(start.x(), mitte), QPointF(ende.x(), mitte), ende)
        kante = self.scene().addPath(pfad, QPen(theme.qcolor(theme.BORDER),
                                                theme.BORDER_WIDTH))
        # Kanten liegen hinter den Knoten, sonst schneiden sie durch die Flaeche.
        kante.setZValue(-1)

    def _male_kantenetikett(self, text: str, y: float) -> None:
        etikett = self.scene().addText(text)
        etikett.setDefaultTextColor(theme.qcolor(theme.TEXT_MUTED))
        schrift = QFont(etikett.font())
        schrift.setPointSizeF(max(schrift.pointSizeF() - 1, 6))
        etikett.setFont(schrift)
        etikett.setPos(0, y)

    def _male_rest(self, anzahl: int, was: str, y: float, breite: float) -> None:
        """``… N weitere Kohorten`` unter der Reihe, gedaempft."""
        if anzahl <= 0:
            return
        etikett = self.scene().addText(f"… {anzahl} weitere {was}")
        etikett.setDefaultTextColor(theme.qcolor(theme.TEXT_MUTED))
        etikett.setPos((breite - etikett.boundingRect().width()) / 2, y)

    def _male_meldung(self, text: str, *, fehler: bool) -> None:
        szene = self.scene()
        etikett = szene.addText(text)
        etikett.setDefaultTextColor(theme.qcolor(theme.ERROR if fehler else theme.TEXT_MUTED))
        etikett.setTextWidth(360)
        # Ohne das steht der Text linksbuendig in einem mittig gesetzten Block
        # und wirkt wie verrutscht.
        option = QTextOption(Qt.AlignmentFlag.AlignHCenter)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        etikett.document().setDefaultTextOption(option)
        szene.setSceneRect(etikett.boundingRect())
        self.resetTransform()
        self.centerOn(etikett)

    # -- Groesse -----------------------------------------------------------
    def _einpassen(self) -> None:
        """Die Szene in die Flaeche einpassen, aber nie vergroessern.

        Ohne die Schranke wuerde ein Netz aus zwei Knoten bildschirmfuellend
        aufgeblasen; mit ihr bleibt es bei 900 x 600 lesbar und nichts wird
        abgeschnitten.
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
    """Titelzeile plus Netzflaeche — das, was oben in die Anzeigeflaeche kommt.

    Die Zeile darueber ist eine Zeile, keine eigene Kartenflaeche: links fett
    ``Wissensnetz``, rechts gedaempft der Hinweis, dass hier Struktur und
    Zaehlungen stehen und keine Messdaten (wie in der Skizze).
    """

    def __init__(self, panel_namen: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        kopf = QHBoxLayout()
        kopf.setContentsMargins(2, 0, 2, 0)
        titel = QLabel("Wissensnetz")
        titel.setObjectName(theme.OBJ_NETZ_TITLE)
        hinweis = QLabel("Struktur und Zaehlungen, keine Messdaten")
        hinweis.setObjectName(theme.OBJ_NETZ_NOTE)
        kopf.addWidget(titel)
        kopf.addStretch(1)
        kopf.addWidget(hinweis)
        layout.addLayout(kopf)

        self.view = NetzView(panel_namen)
        layout.addWidget(self.view, stretch=1)

    # Durchreichen, damit das Fenster nur das Panel kennt.
    def zeige_abzug(self, abzug: dict[str, Any],
                    unterschied: dict[str, Any] | None = None,
                    offen: str | None = None) -> None:
        self.view.zeige_abzug(abzug, unterschied, offen)

    def zeige_hinweis(self, text: str) -> None:
        self.view.zeige_hinweis(text)

    def zeige_nicht_erreichbar(self, url: str) -> None:
        self.view.zeige_nicht_erreichbar(url)
