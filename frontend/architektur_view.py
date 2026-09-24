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

from PySide6.QtCore import QPointF, QRectF, Qt
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


class _Kasten(QGraphicsItem):
    """Eine Station: Titel fett, darunter Komponente, Detail und Beleg."""

    def __init__(self, station: ablauf.Station) -> None:
        super().__init__()
        self._station = station
        self.setToolTip(
            f"{station.name}\n{station.komponente}"
            + (f"\n{station.detail}" if station.detail else "")
            + (f"\nBeleg: {station.beleg}" if station.beleg else "")
        )

    def boundingRect(self) -> QRectF:  # noqa: D102
        return QRectF(0, 0, theme.ARCH_BOX_WIDTH, theme.ARCH_BOX_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        flaeche, rand, gedaempft = _farben(self._station.zustand)

        stift = QPen(theme.qcolor(rand))
        stift.setWidth(theme.NETZ_BORDER_OPEN if self._station.laeuft
                       else theme.BORDER_WIDTH)
        painter.setPen(stift)
        painter.setBrush(QBrush(theme.qcolor(flaeche)))
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1),
                                theme.RADIUS, theme.RADIUS)

        innen = theme.ARCH_BOX_WIDTH - 20
        schrift = QFont(painter.font())
        schrift.setBold(True)
        painter.setFont(schrift)
        painter.setPen(theme.qcolor(theme.TEXT_MUTED if gedaempft else theme.TEXT))
        metrik = painter.fontMetrics()
        painter.drawText(
            QRectF(10, 6, innen, 18),
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
                QRectF(10, 24 + i * 15, innen, 15),
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
        self.zeichne()

    def zeige(self, neuer: ablauf.Ablauf) -> None:
        self._ablauf = neuer
        self.zeichne()

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
