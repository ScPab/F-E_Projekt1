"""Aufklappbare Auswahl mit Suchfeld — ein durchsuchbares Auswahlmenue.

Muster: eine Schaltflaeche zeigt die aktuelle Wahl, ein Klick klappt eine Karte
darunter auf, die oben ein Suchfeld und darunter die gefilterte Liste enthaelt.

Warum nicht ``QComboBox`` mit ``setEditable(True)``: dessen Completer ersetzt den
Text im Feld und laesst keine zweizeilige Zeile mit Kuerzel rechts zu. Und warum
keine dauerhaft sichtbare Liste im Panel: 32 Kohorten brauchen Platz, den das
schmale Auswahlpanel nicht hat — die Liste hat die darunterliegenden Zeilen
ueberlagert.

Die Zeilen zeichnet ein :class:`RowDelegate` statt eigener Widgets je Zeile
(``setItemWidget``). Ein Delegate kennt die tatsaechlich verfuegbare Breite,
kuerzt den Namen bei Bedarf und kann das Kuerzel zuverlaessig rechts ausrichten;
Zeilen-Widgets waren breiter als der Sichtbereich, wodurch das Kuerzel aus dem
Bild geschoben wurde.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QStyle,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

import theme

# Rollen je Listeneintrag.
VALUE_ROLE = Qt.ItemDataRole.UserRole          # was gesendet wird (project_id)
LABEL_ROLE = Qt.ItemDataRole.UserRole + 1      # Klarname
CODE_ROLE = Qt.ItemDataRole.UserRole + 2       # Kuerzel rechts
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 3     # vorberechneter Suchtext

# So viele Zeilen zeigt die aufgeklappte Karte hoechstens; darueber wird
# gescrollt. Neun passt auf kleine Bildschirme und ist genug zum Ueberblicken.
MAX_ROWS = 9


class RowDelegate(QStyledItemDelegate):
    """Zeichnet eine Zeile: runder Anker, Klarname, gedaempftes Kuerzel rechts."""

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: D102
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        ausgewaehlt = bool(option.state & QStyle.StateFlag.State_Selected)
        schwebt = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Hintergrund der Zeile als abgerundete Karte.
        feld = rect.adjusted(2, 1, -2, -1)
        if ausgewaehlt:
            painter.setBrush(theme.qcolor(theme.ACCENT_BG))
            painter.setPen(theme.qcolor(theme.ACCENT))
            painter.drawRoundedRect(feld, theme.RADIUS, theme.RADIUS)
        elif schwebt:
            painter.setBrush(theme.qcolor(theme.SURFACE))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(feld, theme.RADIUS, theme.RADIUS)

        code = index.data(CODE_ROLE) or ""
        name = index.data(LABEL_ROLE) or ""

        # Runder Anker links.
        d = theme.DOT_SIZE
        punkt = QRect(feld.left() + 10, feld.center().y() - d // 2 + 1, d, d)
        painter.setBrush(theme.dot_color(code))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(punkt)

        metrik = QFontMetrics(option.font)
        code_breite = metrik.horizontalAdvance(code) + 16

        # Kuerzel rechts, gedaempft.
        painter.setPen(theme.qcolor(theme.TEXT_MUTED))
        painter.drawText(
            QRect(feld.right() - code_breite, feld.top(), code_breite, feld.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            code,
        )

        # Klarname dazwischen, bei Bedarf gekuerzt.
        links = punkt.right() + 12
        breite = feld.right() - code_breite - links - 8
        painter.setPen(theme.qcolor(theme.TEXT))
        painter.drawText(
            QRect(links, feld.top(), max(breite, 0), feld.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrik.elidedText(name, Qt.TextElideMode.ElideRight, max(breite, 0)),
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: D102
        return QSize(option.rect.width(), theme.ROW_HEIGHT)


class SearchableSelect(QWidget):
    """Schaltflaeche mit aufklappbarer, durchsuchbarer Liste.

    ``entries`` ist eine Liste von ``{"value", "label", "code"}``. Gesendet wird
    immer ``value``; gesucht wird ueber ``code`` und ``value`` — der Klarname
    ist Beschriftung, kein Suchbegriff.
    """

    selection_changed = Signal(str)

    def __init__(self, entries: list[dict[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._button = QPushButton()
        self._button.setObjectName(theme.OBJ_SELECT_BUTTON)
        self._button.clicked.connect(self.toggle_popup)
        layout.addWidget(self._button)

        # Qt.Popup: schliesst sich beim Klick daneben und bei Escape von selbst.
        self._popup = QFrame(self, Qt.WindowType.Popup)
        self._popup.setObjectName(theme.OBJ_POPUP)
        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        popup_layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setObjectName(theme.OBJ_SEARCH)
        # Der Platzhalter nennt das Suchmuster ausdruecklich: seit die Suche nur
        # das Kuerzel trifft, wuerde "lung" sonst kommentarlos leer ausgehen.
        self._search.setPlaceholderText("Kuerzel suchen, z. B. BRCA …")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        self._search.installEventFilter(self)
        popup_layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName(theme.OBJ_PICKER)
        self._list.setItemDelegate(RowDelegate(self._list))
        self._list.setMouseTracking(True)          # fuer den Schwebe-Zustand
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._choose)
        popup_layout.addWidget(self._list)

        # Eigener Hinweis statt einer leeren Liste: ein Kasten ohne Inhalt sieht
        # kaputt aus, nicht wie "nichts gefunden".
        self._empty = QLabel("Kein Kuerzel passt")
        self._empty.setObjectName(theme.OBJ_ROW_CODE)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()
        popup_layout.addWidget(self._empty)

        self._fill(entries)

    # -- Aufbau ------------------------------------------------------------
    def _fill(self, entries: list[dict[str, str]]) -> None:
        for entry in entries:
            value = entry.get("value") or ""
            label = entry.get("label") or value
            code = entry.get("code") or ""
            item = QListWidgetItem()
            item.setData(VALUE_ROLE, value)
            item.setData(LABEL_ROLE, label)
            item.setData(CODE_ROLE, code)
            # Bewusst NUR Kuerzel und Wert, nicht der Klarname: gesucht wird mit
            # der offiziellen Studienabkuerzung (BRCA, LUAD, KIRC). Der Klarname
            # steht weiter in der Zeile, damit man sieht, was sich hinter dem
            # Kuerzel verbirgt — er ist Beschriftung, kein Suchbegriff.
            item.setData(SEARCH_ROLE, f"{code} {value}".lower())
            item.setSizeHint(QSize(0, theme.ROW_HEIGHT))
            item.setToolTip(f"{label}  ({value})")
            self._list.addItem(item)

    # -- Auswahl -----------------------------------------------------------
    def current_value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(VALUE_ROLE) == value:
                self._value = value
                self._list.setCurrentItem(item)
                self._button.setText(f"{item.data(LABEL_ROLE)}   ·   {item.data(CODE_ROLE)}")
                self.selection_changed.emit(value)
                return

    def _choose(self, item: QListWidgetItem) -> None:
        self.set_value(item.data(VALUE_ROLE) or "")
        self._popup.hide()

    # -- Aufklappen --------------------------------------------------------
    def toggle_popup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
            return
        self._search.clear()          # loest _filter aus: alles wieder sichtbar
        self._popup.setFixedWidth(max(self._button.width(), 320))
        self._passe_hoehe_an()
        self._popup.move(self._button.mapToGlobal(QPoint(0, self._button.height() + 4)))
        self._popup.show()
        self._search.setFocus()
        aktuell = self._list.currentItem()
        if aktuell is not None:
            self._list.scrollToItem(aktuell)

    def _filter(self, text: str) -> None:
        muster = text.strip().lower()
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(bool(muster) and muster not in (item.data(SEARCH_ROLE) or ""))
        if self._popup.isVisible():
            self._passe_hoehe_an()

    def _sichtbare(self) -> int:
        return sum(not self._list.item(r).isHidden() for r in range(self._list.count()))

    def _passe_hoehe_an(self) -> None:
        """Die Karte auf die Trefferzahl schrumpfen (hoechstens MAX_ROWS Zeilen).

        Ohne das behaelt das Menue bei zwei Treffern die Hoehe von neun und
        zeigt eine grosse leere Flaeche.
        """
        treffer = self._sichtbare()
        self._empty.setVisible(treffer == 0)
        self._list.setVisible(treffer > 0)
        if treffer:
            self._list.setFixedHeight(min(treffer, MAX_ROWS) * theme.ROW_HEIGHT + 8)
            # Leiste nur zeigen, wenn wirklich mehr da ist als hineinpasst —
            # sonst blitzt sie bei knapp passendem Inhalt neben den Kuerzeln auf.
            self._list.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded if treffer > MAX_ROWS
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        self._popup.adjustSize()

    def eventFilter(self, obj: Any, event: QEvent) -> bool:  # noqa: D102
        """Pfeiltasten und Enter aus dem Suchfeld an die Liste weiterreichen —
        sonst muesste man zum Auswaehlen zur Maus greifen."""
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            taste = event.key()
            if taste in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._springe(1 if taste == Qt.Key.Key_Down else -1)
                return True
            if taste in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item is not None and not item.isHidden():
                    self._choose(item)
                return True
        return super().eventFilter(obj, event)

    def _springe(self, richtung: int) -> None:
        """Zur naechsten sichtbaren Zeile in ``richtung`` wechseln."""
        reihe = self._list.currentRow()
        for _ in range(self._list.count()):
            reihe += richtung
            if not 0 <= reihe < self._list.count():
                return
            if not self._list.item(reihe).isHidden():
                self._list.setCurrentRow(reihe)
                self._list.scrollToItem(self._list.item(reihe))
                return
