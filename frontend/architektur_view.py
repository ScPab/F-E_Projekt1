"""Die Architektur als Ablauf — was gerade im Hintergrund passiert.

Gezeichnet wie das Wissensnetz (:mod:`netz_view`): eine Szene, Kaesten mit
Titel, Komponente und Beleg, dazwischen Pfeile. Die Stationen und ihre Zustaende
rechnet :mod:`ablauf` aus, hier wird nur gemalt — dieselbe Trennung wie zwischen
``store_reader`` und ``netz_view``.

Vorlage: ``docs/DataBridge_Architektur.drawio``. Das Bild ist vom 31.08. und an
zwei Stellen ueberholt (``anndata`` und der Rueckkanal stehen dort als
"geplant"); hier steht der Stand von heute. Nicht die Datei wird gerendert,
sondern dieselbe Kette neu gezeichnet: eine ``.drawio`` ist XML fuer einen
Editor, kein Format, aus dem man Zustaende lebendig machen kann.
"""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

import ablauf
import theme


def _farben(zustand: str) -> tuple[str, str, bool]:
    """Flaeche, Rand und ob der Text gedaempft ist — je Zustand."""
    if zustand == ablauf.LAEUFT:
        return theme.ACCENT_BG, theme.ACCENT, False
    if zustand == ablauf.OK:
        return theme.SUCCESS_BG, theme.SUCCESS, False
    if zustand == ablauf.FEHLER:
        return theme.ERROR_BG, theme.ERROR, False
    if zustand == ablauf.UEBERSPRUNGEN:
        return theme.SURFACE, theme.BORDER, True
    return theme.WINDOW_BG, theme.BORDER, True      # wartet


def _male_symbol(painter: QPainter, art: str, feld: QRectF, farbe: str) -> None:
    """Das Bild einer Station — selbst gezeichnet, keine Icon-Datei.

    Aus demselben Grund wie im Netz: gezeichnete Formen skalieren mit der Szene,
    tragen die Farbe des Zustands und kosten keine neue Abhaengigkeit.
    """
    stift = QPen(theme.qcolor(farbe))
    stift.setWidth(2)
    stift.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(stift)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    x, y, b, h = feld.x(), feld.y(), feld.width(), feld.height()

    if art == ablauf.SYM_JSON:
        # Blatt mit geknickter Ecke und drei Zeilen: der Auftrag als Dokument.
        knick = b * 0.3
        pfad = QPainterPath(QPointF(x, y))
        pfad.lineTo(x + b - knick, y)
        pfad.lineTo(x + b, y + knick)
        pfad.lineTo(x + b, y + h)
        pfad.lineTo(x, y + h)
        pfad.closeSubpath()
        painter.drawPath(pfad)
        for i in range(3):
            zeile = y + h * (0.42 + i * 0.18)
            painter.drawLine(QPointF(x + b * 0.2, zeile), QPointF(x + b * 0.8, zeile))

    elif art == ablauf.SYM_DIENST:
        # Zwei Einschuebe uebereinander: ein Dienst, der Anfragen annimmt.
        for i in range(2):
            oben = y + h * (0.08 + i * 0.5)
            kasten = QRectF(x, oben, b, h * 0.36)
            painter.drawRoundedRect(kasten, 3, 3)
            painter.drawEllipse(QPointF(x + b * 0.2, oben + h * 0.18), 1.6, 1.6)

    elif art == ablauf.SYM_QUELLE:
        # Wolke: die Datenquelle liegt ausserhalb.
        painter.drawEllipse(QPointF(x + b * 0.32, y + h * 0.52), b * 0.26, h * 0.26)
        painter.drawEllipse(QPointF(x + b * 0.62, y + h * 0.46), b * 0.3, h * 0.3)
        painter.drawLine(QPointF(x + b * 0.12, y + h * 0.74),
                         QPointF(x + b * 0.88, y + h * 0.74))

    elif art == ablauf.SYM_TRIPEL:
        # Subjekt - Praedikat - Objekt: drei Knoten, zwei Kanten.
        punkte = [QPointF(x + b * 0.15, y + h * 0.3),
                  QPointF(x + b * 0.5, y + h * 0.75),
                  QPointF(x + b * 0.85, y + h * 0.3)]
        painter.drawLine(punkte[0], punkte[1])
        painter.drawLine(punkte[1], punkte[2])
        painter.setBrush(QBrush(theme.qcolor(farbe)))
        for punkt in punkte:
            painter.drawEllipse(punkt, 2.6, 2.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    elif art == ablauf.SYM_SPEICHER:
        # Zylinder: der Store.
        deckel = QRectF(x, y, b, h * 0.26)
        painter.drawEllipse(deckel)
        painter.drawLine(QPointF(x, y + h * 0.13), QPointF(x, y + h * 0.87))
        painter.drawLine(QPointF(x + b, y + h * 0.13), QPointF(x + b, y + h * 0.87))
        boden = QRectF(x, y + h * 0.74, b, h * 0.26)
        painter.drawArc(boden, 0, -180 * 16)
        painter.drawArc(QRectF(x, y + h * 0.37, b, h * 0.26), 0, -180 * 16)

    elif art == ablauf.SYM_NETZ:
        # Ein Knoten oben, zwei darunter — das Wissensnetz im Kleinen.
        oben = QPointF(x + b * 0.5, y + h * 0.18)
        links = QPointF(x + b * 0.16, y + h * 0.82)
        rechts = QPointF(x + b * 0.84, y + h * 0.82)
        painter.drawLine(oben, links)
        painter.drawLine(oben, rechts)
        painter.setBrush(QBrush(theme.qcolor(farbe)))
        for punkt in (oben, links, rechts):
            painter.drawEllipse(punkt, 3.0, 3.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)


class _Kasten(QGraphicsItem):
    """Eine Station: Symbol links, Titel fett, darunter Komponente und Detail.

    Laeuft sie gerade, wandert eine leuchtende Linie am Rand entlang. Das ist
    bewusst **kein Fortschrittsbalken**: die Oberflaeche weiss nicht, wie weit
    der Mediator ist (siehe ``ablauf``), und ein Balken wuerde genau das
    behaupten. Eine umlaufende Linie sagt "hier passiert etwas", ohne zu luegen.
    """

    def __init__(self, station: ablauf.Station) -> None:
        super().__init__()
        self._station = station
        self._phase = 0.0
        self.setToolTip(
            f"{station.name}\n{station.komponente}"
            + (f"\n{station.detail}" if station.detail else "")
            + (f"\nBeleg: {station.beleg}" if station.beleg else "")
        )

    def boundingRect(self) -> QRectF:  # noqa: D102
        # Etwas groesser als der Kasten: der Schein der Laufschrift blutet nach
        # aussen aus und wuerde sonst abgeschnitten.
        rand = theme.ARCH_PULS_BREITE * theme.ARCH_PULS_SCHEIN
        return QRectF(0, 0, theme.ARCH_BOX_WIDTH,
                      theme.ARCH_BOX_HEIGHT).adjusted(-rand, -rand, rand, rand)

    def setze_phase(self, phase: float) -> None:
        """Die Animation weiterdrehen — nur laufende Kaesten zeichnen neu."""
        if not self._station.laeuft:
            return
        self._phase = phase
        self.update()

    def _male_laufschrift(self, painter: QPainter) -> None:
        """Ein leuchtendes Stueck, das am Rand entlangwandert.

        Umgesetzt ueber ein Strichmuster mit wanderndem Versatz: ein kurzes
        "an", eine sehr lange Luecke — sichtbar ist damit immer genau ein
        Stueck. Darunter liegen ein paar breitere, blassere Lagen als Schein.
        """
        feld = QRectF(0, 0, theme.ARCH_BOX_WIDTH,
                      theme.ARCH_BOX_HEIGHT).adjusted(1, 1, -1, -1)
        pfad = QPainterPath()
        pfad.addRoundedRect(feld, theme.RADIUS, theme.RADIUS)

        umfang = 2 * (feld.width() + feld.height())
        breite = theme.ARCH_PULS_BREITE
        # Das Strichmuster rechnet in Vielfachen der Strichstaerke.
        an = theme.ARCH_PULS_LAENGE / breite
        aus = umfang / breite
        versatz = (self._phase % 1.0) * (an + aus)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for lage in range(theme.ARCH_PULS_SCHEIN, 0, -1):
            stift = QPen(theme.mit_deckkraft(theme.ACCENT, 0.9 / (lage * lage)))
            stift.setWidthF(breite * lage)
            stift.setCapStyle(Qt.PenCapStyle.RoundCap)
            stift.setDashPattern([an, aus])
            stift.setDashOffset(versatz)
            painter.setPen(stift)
            painter.drawPath(pfad)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        flaeche, rand_farbe, gedaempft = _farben(self._station.zustand)

        stift = QPen(theme.qcolor(rand_farbe))
        stift.setWidth(theme.NETZ_BORDER_OPEN if self._station.laeuft
                       else theme.BORDER_WIDTH)
        painter.setPen(stift)
        painter.setBrush(QBrush(theme.qcolor(flaeche)))
        painter.drawRoundedRect(
            QRectF(0, 0, theme.ARCH_BOX_WIDTH, theme.ARCH_BOX_HEIGHT)
            .adjusted(1, 1, -1, -1),
            theme.RADIUS, theme.RADIUS)
        if self._station.laeuft:
            self._male_laufschrift(painter)

        # Symbol links, Text rechts daneben.
        rand = theme.ARCH_ICON_MARGIN
        groesse = theme.ARCH_ICON
        _male_symbol(painter, self._station.symbol,
                     QRectF(rand, (theme.ARCH_BOX_HEIGHT - groesse) / 2,
                            groesse, groesse),
                     theme.TEXT_MUTED if gedaempft else rand_farbe)

        links = rand + groesse + 10
        innen = theme.ARCH_BOX_WIDTH - links - 10
        schrift = QFont(painter.font())
        schrift.setBold(True)
        painter.setFont(schrift)
        painter.setPen(theme.qcolor(theme.TEXT_MUTED if gedaempft else theme.TEXT))
        metrik = painter.fontMetrics()
        painter.drawText(
            QRectF(links, 8, innen, 18),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrik.elidedText(self._station.name, Qt.TextElideMode.ElideRight, innen),
        )

        schrift.setBold(False)
        painter.setFont(schrift)
        metrik = painter.fontMetrics()
        zeilen = [
            (self._station.komponente, theme.TEXT_MUTED),
            (self._station.detail, theme.TEXT_MUTED if gedaempft else theme.TEXT),
        ]
        for i, (text, farbe) in enumerate(zeilen):
            if not text:
                continue
            painter.setPen(theme.qcolor(farbe))
            painter.drawText(
                QRectF(links, 26 + i * 15, innen, 15),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrik.elidedText(text, Qt.TextElideMode.ElideRight, innen),
            )


class ArchitekturView(QGraphicsView):
    """Die Stationenkette als Bild."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(theme.OBJ_NETZ)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(theme.qcolor(theme.WINDOW_BG)))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._ablauf = ablauf.ruhend()
        self._kaesten: list[_Kasten] = []

        # Ein Takt fuer die Animation. Er laeuft **nur**, solange eine Station
        # laeuft — im Ruhezustand kostet die Ansicht nichts.
        self._uhr = QElapsedTimer()
        self._takt = QTimer(self)
        self._takt.setInterval(theme.ARCH_TAKT_MS)
        self._takt.timeout.connect(self._tick)

        self.zeichne()

    def zeige(self, neuer: ablauf.Ablauf) -> None:
        self._ablauf = neuer
        self.zeichne()

    def _tick(self) -> None:
        """Ein Bild weiter: die Phase haengt an der verstrichenen Zeit, nicht an
        der Zahl der Bilder — so laeuft die Linie ueberall gleich schnell."""
        strecke = self._uhr.elapsed() / 1000.0 * theme.ARCH_PULS_TEMPO
        phase = strecke / (theme.ARCH_PULS_LAENGE + 2 * (theme.ARCH_BOX_WIDTH
                                                         + theme.ARCH_BOX_HEIGHT))
        for kasten in self._kaesten:
            kasten.setze_phase(phase)

    # -- Zeichnen ----------------------------------------------------------
    def zeichne(self) -> None:
        szene = self.scene()
        szene.clear()

        breite = theme.ARCH_BOX_WIDTH
        abstand = theme.ARCH_GAP
        kaesten = []
        for i, station in enumerate(self._ablauf.stationen):
            kasten = _Kasten(station)
            kasten.setPos(i * (breite + abstand), 0)
            szene.addItem(kasten)
            kaesten.append(kasten)

        for links, rechts in zip(kaesten, kaesten[1:]):
            self._male_pfeil(links, rechts)

        if self._ablauf.ueberschrift:
            etikett = szene.addText(self._ablauf.ueberschrift)
            etikett.setDefaultTextColor(theme.qcolor(theme.TEXT_MUTED))
            etikett.setPos(0, theme.ARCH_BOX_HEIGHT + 12)

        szene.setSceneRect(szene.itemsBoundingRect().adjusted(-8, -8, 8, 8))
        self._einpassen()

        # Takt nur laufen lassen, wenn es etwas zu animieren gibt.
        self._kaesten = kaesten
        if any(s.laeuft for s in self._ablauf.stationen):
            if not self._takt.isActive():
                self._uhr.restart()
                self._takt.start()
        else:
            self._takt.stop()

    def _male_pfeil(self, links: _Kasten, rechts: _Kasten) -> None:
        """Waagerechter Pfeil von Kasten zu Kasten."""
        y = theme.ARCH_BOX_HEIGHT / 2
        x1 = links.pos().x() + theme.ARCH_BOX_WIDTH
        x2 = rechts.pos().x()
        stift = QPen(theme.qcolor(theme.BORDER), theme.BORDER_WIDTH)
        linie = self.scene().addLine(x1 + 2, y, x2 - 6, y, stift)
        linie.setZValue(-1)

        spitze = QPainterPath(QPointF(x2 - 2, y))
        spitze.lineTo(x2 - 8, y - 4)
        spitze.lineTo(x2 - 8, y + 4)
        spitze.closeSubpath()
        kopf = self.scene().addPath(spitze, QPen(Qt.PenStyle.NoPen),
                                    QBrush(theme.qcolor(theme.BORDER)))
        kopf.setZValue(-1)

    def _einpassen(self) -> None:
        rechteck = self.scene().sceneRect()
        if rechteck.isEmpty():
            return
        self.fitInView(rechteck, Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.0:
            self.resetTransform()
            self.centerOn(rechteck.center())

    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        self._einpassen()


class ArchitekturPanel(QWidget):
    """Die Ansicht, wie sie unten in der Anzeigeflaeche sitzt."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = ArchitekturView()
        layout.addWidget(self.view, stretch=1)

    def zeige(self, neuer: ablauf.Ablauf) -> None:
        self.view.zeige(neuer)
