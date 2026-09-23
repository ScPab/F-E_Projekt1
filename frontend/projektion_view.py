"""Die Morphing-Projektion als Qt-Ansicht — Karte links, Regler rechts.

Vorbild ist Oviedos ``demo.py`` in der Fassung, die MP-Lite nachstellt: ein
Scatter mit dem Titel ``Cancer map``, daneben **ein Regler je Variable**, und die
Punktposition ist die softmax-gewichtete Summe der Encodings. Gerechnet wird in
:mod:`morph`, hier wird nur gezeichnet.

``pyqtgraph`` statt matplotlib: beim Ziehen mehrerer Regler werden tausende
Punkte neu gesetzt, und matplotlib wird dabei zaeh. Kein QtWebEngine, kein
Bokeh — die Ansicht ist ein Qt-Widget, kein eingebetteter Browser (ADR-0004).

Zwei Dinge, die pyqtgraph von Haus aus anders macht und die hier geradegezogen
werden: es ist dunkel (haette als schwarzer Block in einer hellen Oberflaeche
gesessen) und es verzerrt die Achsen frei (die Kreis-Encodings waeren zu
Ellipsen geworden).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

import morph
import theme

# Der Regler arbeitet in ganzen Schritten; 0..100 entspricht 0,00..1,00.
_SCHRITTE = 100


class _AuswahlBox(pg.ViewBox):
    """Ein ``ViewBox``, dessen Linksziehen ein **Auswahl**rechteck ist.

    pyqtgraph bringt das Gummiband schon mit (``updateScaleBox``), benutzt es im
    Normalfall aber zum Hineinzoomen. Hier wird derselbe Rahmen gezeichnet und
    am Ende die Flaeche gemeldet. Rechtsklick und Rad bleiben unveraendert, das
    Bild laesst sich also weiter verschieben und zoomen.

    Ein Freihand-Lasso waere Handarbeit an Polygon-Tests und bleibt draussen,
    bis sich zeigt, dass es fehlt.
    """

    rechteck_gezogen = Signal(object)      # QRectF in Datenkoordinaten

    def mouseDragEvent(self, ev, axis=None) -> None:  # noqa: D102, N802
        if ev.button() != Qt.MouseButton.LeftButton:
            super().mouseDragEvent(ev, axis)
            return
        ev.accept()
        self.updateScaleBox(ev.buttonDownPos(), ev.pos())
        if ev.isFinish():
            self.rbScaleBox.hide()
            rechteck = QRectF(ev.buttonDownPos(), ev.pos()).normalized()
            self.rechteck_gezogen.emit(
                self.childGroup.mapRectFromParent(rechteck)
            )


class _Regler(QWidget):
    """Ein Regler mit Namen links, Wert rechts und dem Schieber darunter.

    Nicht nutzbare Variablen bleiben **sichtbar** und an ihrem Platz, nur
    deaktiviert und mit dem Grund im Tooltip — dieselbe Regel wie bei ENA und
    GEO im Auswahlpanel: ehrliche Luecke statt unsichtbarer Grenze.
    """

    wert_geaendert = Signal()

    def __init__(self, eintrag: morph.Eintrag, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._eintrag = eintrag

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        kopf = QHBoxLayout()
        kopf.setContentsMargins(0, 0, 0, 0)
        self._name = QLabel(eintrag.name)
        self._name.setObjectName(theme.OBJ_SLIDER_NAME)
        self._wert = QLabel("0.00")
        self._wert.setObjectName(theme.OBJ_SLIDER_VALUE)
        kopf.addWidget(self._name)
        kopf.addStretch(1)
        kopf.addWidget(self._wert)
        layout.addLayout(kopf)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SCHRITTE)
        self._slider.setValue(int(round(eintrag.start * _SCHRITTE)))
        self._slider.valueChanged.connect(self._nachziehen)
        layout.addWidget(self._slider)

        if not eintrag.nutzbar:
            self._slider.setEnabled(False)
            self._name.setEnabled(False)
            hinweis = f"{eintrag.name}: {eintrag.grund}"
            for teil in (self, self._slider, self._name, self._wert):
                teil.setToolTip(hinweis)
        self._nachziehen()

    def _nachziehen(self) -> None:
        # Der Zahlenwert neben dem Regler: ohne ihn weiss man nach dem Ziehen
        # nicht, wo man steht.
        self._wert.setText(f"{self.wert():.2f}")
        self.wert_geaendert.emit()

    def wert(self) -> float:
        return self._slider.value() / _SCHRITTE


class ProjektionPanel(QWidget):
    """Karte, Regler und die Wege zur Datei.

    Die Ansicht haelt ein :class:`morph.Morphmodell` und zeichnet es; geladen
    wird die Datei im Worker-Thread, deshalb kommt das Modell von aussen ueber
    :meth:`zeige_modell`.
    """

    # Eine Datei soll geladen werden (Pfad) — das Fenster startet den Worker.
    datei_gewuenscht = Signal(str)
    # Eine Probe wurde angeklickt (submitter_id) bzw. ein Rechteck aufgezogen.
    probe_geklickt = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modell: morph.Morphmodell | None = None
        self._regler: list[_Regler] = []
        self._farben: list[QColor] = []
        self._ausgewaehlt: set[int] = set()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._baue_karte(), stretch=1)
        layout.addWidget(self._baue_reglerspalte())

    # -- Aufbau ------------------------------------------------------------
    def _baue_karte(self) -> QWidget:
        seite = QWidget()
        layout = QVBoxLayout(seite)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        kopf = QHBoxLayout()
        kopf.setContentsMargins(0, 0, 0, 0)
        self._oeffnen = QPushButton("Datei oeffnen …")
        self._oeffnen.clicked.connect(self._waehle_datei)
        kopf.addWidget(self._oeffnen)
        kopf.addStretch(1)
        layout.addLayout(kopf)

        # pyqtgraph ist von Haus aus dunkel; Flaeche und Achsen hier auf die
        # helle Oberflaeche ziehen, sonst sitzt ein schwarzer Block im Fenster.
        pg.setConfigOptions(antialias=True)
        self._box = _AuswahlBox()
        self._box.rechteck_gezogen.connect(self._rechteck)
        self._plot = pg.PlotWidget(background=theme.WINDOW_BG, viewBox=self._box)
        self._plot.setTitle("Cancer map", color=theme.TEXT, size="10pt")
        # Die Koordinaten bedeuten nach dem Morphen nichts Absolutes — Achsen
        # ohne Beschriftung, aber sichtbar als Rahmen.
        for achse in ("left", "bottom"):
            self._plot.getAxis(achse).setPen(pg.mkPen(theme.BORDER))
            # Keine Zahlen an den Achsen: nach dem Morphen ist eine Koordinate
            # keine Groesse, die man ablesen koennte. Der Rahmen bleibt.
            self._plot.getAxis(achse).setStyle(showValues=False)
        # Sonst verzerren die Kreis-Encodings zu Ellipsen.
        self._plot.setAspectLocked(True)
        self._plot.setMenuEnabled(False)
        # Die Karte soll auch bei 900 x 600 nicht zur Briefmarke werden.
        self._plot.setMinimumHeight(theme.MAP_MIN_HEIGHT)

        self._punkte = pg.ScatterPlotItem(size=theme.SCATTER_POINT_SIZE,
                                          pen=pg.mkPen(None))
        self._punkte.sigClicked.connect(self._punkt_geklickt)
        self._plot.addItem(self._punkte)
        # Klick ins Leere hebt die Auswahl auf. Der Punkt-Klick kommt zuerst und
        # setzt eine Marke, an der dieser Handler erkennt, dass er nichts tun soll.
        self._klick_auf_punkt = False
        self._plot.scene().sigMouseClicked.connect(self._klick_daneben)

        # Meldung statt Karte: leerer Zustand, Ladehinweis, fehlendes Layout.
        self._hinweis = QLabel("Keine Datei geladen.\nUeber `Datei oeffnen …` eine "
                               ".h5ad waehlen.")
        self._hinweis.setObjectName(theme.OBJ_PROJ_HINT)
        self._hinweis.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hinweis.setWordWrap(True)
        self._hinweis.setFrameShape(QFrame.Shape.NoFrame)

        layout.addWidget(self._plot, stretch=1)
        layout.addWidget(self._hinweis, stretch=1)
        self._plot.hide()

        # Die Legende in einem flachen Rollbereich: 32 Kohorten waeren sonst
        # sechs Zeilen hoch und wuerden die Karte auf einen Rest zusammendruecken.
        self._legende = QLabel("")
        self._legende.setObjectName(theme.OBJ_SLIDER_VALUE)
        self._legende.setWordWrap(True)
        self._legende.setTextFormat(Qt.TextFormat.RichText)
        self._legendenbereich = QScrollArea()
        self._legendenbereich.setWidgetResizable(True)
        self._legendenbereich.setFrameShape(QFrame.Shape.NoFrame)
        self._legendenbereich.setMaximumHeight(theme.LEGEND_MAX_HEIGHT)
        self._legendenbereich.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._legendenbereich.setWidget(self._legende)
        layout.addWidget(self._legendenbereich)

        # Anzahl der ausgewaehlten Proben unter der Karte — neben der
        # Schaltflaeche war sie in der schmalen Spalte abgeschnitten.
        self._auswahl_label = QLabel("")
        self._auswahl_label.setObjectName(theme.OBJ_SLIDER_VALUE)
        layout.addWidget(self._auswahl_label)

        self._kontext = QLabel("")
        self._kontext.setObjectName(theme.OBJ_SLIDER_VALUE)
        self._kontext.setWordWrap(True)
        self._kontext.hide()
        layout.addWidget(self._kontext)
        return seite

    def _baue_reglerspalte(self) -> QWidget:
        # 15 Regler passen bei 600 Pixel Fensterhoehe nicht alle hinein.
        self._reglerbereich = QScrollArea()
        self._reglerbereich.setWidgetResizable(True)
        self._reglerbereich.setFixedWidth(theme.SLIDER_COLUMN_WIDTH)
        self._reglerbereich.setFrameShape(QFrame.Shape.NoFrame)
        self._reglerbereich.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._reglerinhalt = QWidget()
        self._reglerlayout = QVBoxLayout(self._reglerinhalt)
        self._reglerlayout.setContentsMargins(4, 0, 8, 0)
        self._reglerlayout.setSpacing(10)
        self._reglerlayout.addStretch(1)
        self._reglerbereich.setWidget(self._reglerinhalt)
        self._reglerbereich.setSizePolicy(QSizePolicy.Policy.Fixed,
                                          QSizePolicy.Policy.Expanding)
        return self._reglerbereich

    # -- Datei -------------------------------------------------------------
    def _waehle_datei(self) -> None:
        """Dateidialog; Startordner wie beim Speichern eines ``.h5ad``."""
        start = Path(__file__).resolve().parent.parent / "wissensnetz" / "data"
        pfad, _ = QFileDialog.getOpenFileName(
            self, "AnnData oeffnen", str(start), "AnnData (*.h5ad);;Alle Dateien (*)"
        )
        if pfad:
            self.datei_gewuenscht.emit(pfad)

    def zeige_laden(self, dateiname: str) -> None:
        self._zeige_hinweis(f"Lade {dateiname} …")

    def zeige_fehler(self, text: str) -> None:
        self._zeige_hinweis(text)

    def _zeige_hinweis(self, text: str) -> None:
        self._hinweis.setText(text)
        self._hinweis.show()
        self._plot.hide()
        self._legende.setText("")

    # -- Modell ------------------------------------------------------------
    def dateiname(self) -> str:
        return self._modell.dateiname if self._modell else ""

    def hat_modell(self) -> bool:
        return self._modell is not None

    def zeige_modell(self, modell: morph.Morphmodell) -> None:
        """Ein geladenes Modell uebernehmen: Regler bauen, Karte zeichnen."""
        self._modell = modell
        self._ausgewaehlt.clear()
        self._auswahl_label.setText("")
        self._kontext.hide()
        self._baue_regler(modell)

        if not modell.hat_basis:
            # Kein 2D-Layout, also keine Karte — und schon gar keine erfundenen
            # Koordinaten (siehe morph.TEXT_OHNE_LAYOUT).
            self._zeige_hinweis(morph.TEXT_OHNE_LAYOUT)
            return

        self._farben = [theme.cohort_color(code) for code in modell.kohorten]
        self._hinweis.hide()
        self._plot.show()
        self._legende.setText(self._legendentext(modell))
        self._zeichne(erste=True)

    def _baue_regler(self, modell: morph.Morphmodell) -> None:
        for regler in self._regler:
            self._reglerlayout.removeWidget(regler)
            regler.deleteLater()
        self._regler = []
        for eintrag in modell.eintraege:
            regler = _Regler(eintrag)
            regler.wert_geaendert.connect(self._zeichne)
            self._reglerlayout.insertWidget(self._reglerlayout.count() - 1, regler)
            self._regler.append(regler)

    def _legendentext(self, modell: morph.Morphmodell) -> str:
        """Nur die im Datensatz vorkommenden Kohorten, in Oviedo-Reihenfolge."""
        from wissensnetz.cohorts import OVIEDO_COHORTS

        vorhanden = {k for k in modell.kohorten if k}
        teile = [
            f'<span style="color:{theme.cohort_color(code).name()}">■</span> {code}'
            for code in OVIEDO_COHORTS if code in vorhanden
        ]
        if any(k is None for k in modell.kohorten):
            teile.append(f'<span style="color:{theme.NEUTRAL}">■</span> ohne Kohorte')
        return "  ".join(teile)

    # -- Zeichnen ----------------------------------------------------------
    def _zeichne(self, erste: bool = False) -> None:
        """Positionen neu rechnen und setzen.

        Kein Neuaufbau des ``ScatterPlotItem``, nur ``setData`` — sonst flackert
        es und wird langsam.
        """
        if self._modell is None or not self._modell.hat_basis:
            return
        gewichte = [r.wert() for r in self._regler]
        pos = morph.positionen(self._modell, gewichte)
        if pos.size == 0:
            return
        self._punkte.setData(x=pos[:, 0], y=pos[:, 1],
                             brush=self._pinsel(), pen=self._stifte(),
                             data=list(range(len(pos))))
        # Nach jedem Morphen neu einpassen: die Wolke wechselt zwischen
        # tSNE-Spanne und Kreisradius, ein stehender Ausschnitt wuerde sie
        # anschneiden. In Bokeh macht das die DataRange von selbst.
        self._plot.autoRange()

    def _pinsel(self) -> list[QBrush]:
        return [QBrush(farbe) for farbe in self._farben]

    def _stifte(self) -> list[QPen]:
        """Ausgewaehlte Punkte bekommen einen Rand in der Akzentfarbe; die
        Fuellung bleibt die Kohortenfarbe."""
        leer = QPen(Qt.PenStyle.NoPen)
        rand = QPen(theme.qcolor(theme.ACCENT))
        rand.setWidth(2)
        return [rand if i in self._ausgewaehlt else leer
                for i in range(len(self._farben))]

    # -- Auswahl -----------------------------------------------------------
    def _punkt_geklickt(self, _item, punkte) -> None:
        if not punkte or self._modell is None:
            return
        index = punkte[0].data()
        if index is None:
            return
        self._klick_auf_punkt = True
        self._ausgewaehlt = {int(index)}
        self._zeichne()
        zeile = self._modell.punkte[int(index)]
        self._auswahl_label.setText("1 Probe ausgewaehlt")
        self.probe_geklickt.emit(str(zeile.get("tumor") or zeile.get("sample_id") or ""))

    def _rechteck(self, rechteck: QRectF) -> None:
        """Alle Punkte im aufgezogenen Rechteck auswaehlen."""
        if self._modell is None or not self._modell.hat_basis:
            return
        # Ein Klick ohne Ziehen ergibt ein leeres Rechteck - das ist kein
        # Auswahlversuch, sondern das Aufheben der Auswahl.
        if rechteck.width() <= 0 or rechteck.height() <= 0:
            self._leere_auswahl()
            return
        pos = morph.positionen(self._modell, [r.wert() for r in self._regler])
        innen = (
            (pos[:, 0] >= rechteck.left()) & (pos[:, 0] <= rechteck.right())
            & (pos[:, 1] >= rechteck.top()) & (pos[:, 1] <= rechteck.bottom())
        )
        self._ausgewaehlt = {int(i) for i in np.flatnonzero(innen)}
        self._zeichne()
        anzahl = len(self._ausgewaehlt)
        self._auswahl_label.setText(
            f"{anzahl} {'Probe' if anzahl == 1 else 'Proben'} ausgewaehlt"
            if anzahl else ""
        )

    def _klick_daneben(self, _ereignis) -> None:
        """Klick ins Leere hebt die Auswahl auf."""
        if self._klick_auf_punkt:
            self._klick_auf_punkt = False
            return
        self._leere_auswahl()

    def _leere_auswahl(self) -> None:
        if not self._ausgewaehlt:
            return
        self._ausgewaehlt = set()
        self._auswahl_label.setText("")
        self.zeige_kontext("")
        self._zeichne()

    def zeige_kontext(self, text: str) -> None:
        """Den Kontextblock unter der Karte setzen (kommt aus dem Wissensnetz)."""
        self._kontext.setText(text)
        self._kontext.setVisible(bool(text))
