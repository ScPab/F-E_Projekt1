"""Aufklappbare Auswahlmenues — einwertig (Kohorte) und mehrwertig (Obj, Quelle).

Muster: eine Schaltflaeche zeigt die aktuelle Wahl, ein Klick klappt eine Karte
darunter auf, die oben ein Suchfeld und darunter die gefilterte Liste enthaelt.

Warum nicht ``QComboBox`` mit ``setEditable(True)``: dessen Completer ersetzt den
Text im Feld und laesst keine zweizeilige Zeile mit Kuerzel rechts zu. Und warum
keine dauerhaft sichtbare Liste im Panel: 32 Kohorten brauchen Platz, den das
schmale Auswahlpanel nicht hat — die Liste hat die darunterliegenden Zeilen
ueberlagert. Dasselbe galt fuer die Attribut- und Quellenlisten (Aufgabe 18):
elf Attribute in einem 240 Pixel hohen Kasten waren immer abgeschnitten.

Die Zeilen zeichnet ein :class:`RowDelegate` statt eigener Widgets je Zeile
(``setItemWidget``). Ein Delegate kennt die tatsaechlich verfuegbare Breite,
kuerzt den Namen bei Bedarf und kann das Kuerzel zuverlaessig rechts ausrichten;
Zeilen-Widgets waren breiter als der Sichtbereich, wodurch das Kuerzel aus dem
Bild geschoben wurde.

Aufbau: :class:`_AufklappAuswahl` haelt Karte, Suchfeld, Hoehenanpassung und
Tastatur; :class:`SearchableSelect` (einwertig) und :class:`MultiSelect`
(Haekchenliste) leiten davon ab. **Kein zweites Popup-Geruest daneben** — die
Eigenheiten von :class:`PopupCard` sind teuer erarbeitet (siehe deren Docstring)
und sollen genau einmal gepflegt werden.

English: Popup selection menus — single-valued (cohort) and multi-valued
(object, source).

Pattern: a button shows the current choice, a click expands a card below it
that has a search field at the top and the filtered list below.

Why not ``QComboBox`` with ``setEditable(True)``: its completer replaces the
text in the field and does not allow a two-line row with a code on the
right. And why not a permanently visible list in the panel: 32 cohorts need
space that the narrow selection panel does not have — the list would
overlap the rows underneath it. The same was true for the attribute and
source lists (task 18): eleven attributes in a 240-pixel-high box were
always cut off.

The rows are painted by a :class:`RowDelegate` instead of per-row widgets
(``setItemWidget``). A delegate knows the actually available width, elides
the name if needed, and can reliably right-align the code; row widgets were
wider than the visible area, pushing the code out of view.

Structure: :class:`_AufklappAuswahl` holds the card, search field, height
adjustment and keyboard handling; :class:`SearchableSelect` (single-valued)
and :class:`MultiSelect` (checkbox list) derive from it. **No second popup
scaffold next to it** — the quirks of :class:`PopupCard` were expensively
worked out (see its docstring) and are meant to be maintained in exactly one
place.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
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
# EN: Roles per list entry.
VALUE_ROLE = Qt.ItemDataRole.UserRole          # was gesendet wird (project_id) / EN: what gets sent (project_id)
LABEL_ROLE = Qt.ItemDataRole.UserRole + 1      # Klarname / EN: display name
CODE_ROLE = Qt.ItemDataRole.UserRole + 2       # Kuerzel/Hinweis rechts / EN: code/hint on the right
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 3     # vorberechneter Suchtext / EN: precomputed search text
KIND_ROLE = Qt.ItemDataRole.UserRole + 4       # KIND_ROW oder KIND_HEADER / EN: KIND_ROW or KIND_HEADER

KIND_ROW = "row"
KIND_HEADER = "header"

# So viele Zeilen zeigt die aufgeklappte Karte hoechstens; darueber wird
# gescrollt. Neun passt auf kleine Bildschirme und ist genug zum Ueberblicken.
# EN: The expanded card shows at most this many rows; beyond that it
# scrolls. Nine fits small screens and is enough to get an overview.
MAX_ROWS = 9
# Dieselbe Schranke als Hoehe — die Mehrfachauswahl mischt hohe Zeilen mit
# niedrigen Gruppenueberschriften, da traegt eine Zeilenzahl nicht mehr.
# EN: The same limit expressed as a height — the multi-select mixes tall
# rows with short group headings, so a row count no longer works.
MAX_CARD_HEIGHT = MAX_ROWS * theme.ROW_HEIGHT


def _ist_angehakt(index) -> bool:
    """Haekchenzustand eines Index — Qt liefert ihn je nach Fassung als
    ``Qt.CheckState`` oder als ``int``.

    English: Checked state of an index — depending on the Qt version, Qt
    returns it as ``Qt.CheckState`` or as ``int``.
    """
    zustand = index.data(Qt.ItemDataRole.CheckStateRole)
    if zustand is None:
        return False
    return int(zustand) == int(Qt.CheckState.Checked.value)


class RowDelegate(QStyledItemDelegate):
    """Zeichnet eine Zeile: Kaestchen und/oder runden Anker, Name, Kuerzel rechts.

    Was gezeichnet wird, entscheiden ``mit_punkt`` und ``mit_kaestchen``: die
    Kohorte hat den farbigen Anker, die Haekchenlisten das Kaestchen. Der Anker
    ist rein optisch (siehe ``theme.dot_color``) und haette in ``Obj`` und
    ``Datenquelle`` ohnehin keine Bedeutung.

    Das Kaestchen kommt bewusst **nicht** aus ``QListWidget::indicator``: in der
    aufklappenden Karte greifen Stylesheet-Hintergruende nicht (siehe
    :class:`PopupCard`), es bliebe unsichtbar oder schwarz. Also wird es gemalt
    wie alles andere in der Zeile auch. Farben und Masse stehen in ``theme``.

    English: Paints a row: checkbox and/or round marker, name, code on the
    right.

    What gets painted is decided by ``mit_punkt`` and ``mit_kaestchen``: the
    cohort has the colored marker, the checkbox lists have the checkbox. The
    marker is purely visual (see ``theme.dot_color``) and would have no
    meaning in ``Obj`` and ``Datenquelle`` anyway.

    The checkbox deliberately does **not** come from ``QListWidget::indicator``:
    in the popup card, stylesheet backgrounds have no effect (see
    :class:`PopupCard`), it would remain invisible or black. So it is painted
    like everything else in the row. Colors and sizes live in ``theme``.
    """

    def __init__(self, parent: QWidget | None = None, *,
                 mit_punkt: bool = True, mit_kaestchen: bool = False) -> None:
        super().__init__(parent)
        self._mit_punkt = mit_punkt
        self._mit_kaestchen = mit_kaestchen

    # -- Zeichnen ----------------------------------------------------------
    def paint(self, painter: QPainter, option, index) -> None:  # noqa: D102
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if index.data(KIND_ROLE) == KIND_HEADER:
            self._male_ueberschrift(painter, option, index)
            painter.restore()
            return

        rect = option.rect
        aktiv = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        ausgewaehlt = bool(option.state & QStyle.StateFlag.State_Selected)
        # Kein Schwebe-Zustand auf deaktivierten Zeilen: sie sehen sonst
        # anklickbar aus, obwohl sie es nicht sind.
        # EN: No hover state on disabled rows: otherwise they look clickable
        # even though they are not.
        schwebt = aktiv and bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Hintergrund der Zeile als abgerundete Karte.
        # EN: Row background as a rounded card.
        feld = rect.adjusted(2, 1, -2, -1)
        if ausgewaehlt and aktiv:
            painter.setBrush(theme.qcolor(theme.ACCENT_BG))
            painter.setPen(theme.qcolor(theme.ACCENT))
            painter.drawRoundedRect(feld, theme.RADIUS, theme.RADIUS)
        elif schwebt:
            painter.setBrush(theme.qcolor(theme.SURFACE))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(feld, theme.RADIUS, theme.RADIUS)

        code = index.data(CODE_ROLE) or ""
        name = index.data(LABEL_ROLE) or ""

        links = feld.left() + 10
        if self._mit_kaestchen:
            links = self._male_kaestchen(painter, feld, index, aktiv) + theme.CHECK_GAP
        if self._mit_punkt:
            d = theme.DOT_SIZE
            punkt = QRect(links, feld.center().y() - d // 2 + 1, d, d)
            painter.setBrush(theme.dot_color(code))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(punkt)
            links = punkt.right() + 12

        metrik = QFontMetrics(option.font)
        code_breite = metrik.horizontalAdvance(code) + 16 if code else 0

        # Kuerzel (Kohorte) bzw. Hinweis (deaktivierte Quelle) rechts, gedaempft.
        # EN: Code (cohort) or hint (disabled source) on the right, muted.
        if code:
            painter.setPen(theme.qcolor(theme.TEXT_MUTED))
            painter.drawText(
                QRect(feld.right() - code_breite, feld.top(), code_breite, feld.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                code,
            )

        # Klarname dazwischen, bei Bedarf gekuerzt.
        # EN: Display name in between, elided if needed.
        breite = feld.right() - code_breite - links - 8
        painter.setPen(theme.qcolor(theme.TEXT if aktiv else theme.TEXT_MUTED))
        painter.drawText(
            QRect(links, feld.top(), max(breite, 0), feld.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrik.elidedText(name, Qt.TextElideMode.ElideRight, max(breite, 0)),
        )
        painter.restore()

    def _male_ueberschrift(self, painter: QPainter, option, index) -> None:
        """Gruppenueberschrift: fett, gedaempft, ohne Kaestchen und Hintergrund.

        English: Group heading: bold, muted, without checkbox or background.
        """
        schrift = QFont(option.font)
        schrift.setBold(True)
        painter.setFont(schrift)
        painter.setPen(theme.qcolor(theme.TEXT_MUTED))
        painter.drawText(
            option.rect.adjusted(12, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
            index.data(LABEL_ROLE) or "",
        )

    def _male_kaestchen(self, painter: QPainter, feld: QRect, index, aktiv: bool) -> int:
        """Das Haekchen-Kaestchen malen; gibt dessen rechten Rand zurueck.

        Drei Zustaende: leer, angehakt (Akzentfarbe), deaktiviert (gedaempft).
        Dass ENA und GEO nicht anhakbar sind, muss man *sehen*.

        English: Paint the checkbox; returns its right edge.

        Three states: empty, checked (accent color), disabled (muted). That
        ENA and GEO cannot be checked must be *visible*.
        """
        s = theme.CHECK_SIZE
        kasten = QRect(feld.left() + 12, feld.center().y() - s // 2, s, s)
        angehakt = _ist_angehakt(index)

        if angehakt and aktiv:
            painter.setBrush(theme.qcolor(theme.ACCENT))
            painter.setPen(theme.qcolor(theme.ACCENT))
        elif aktiv:
            painter.setBrush(theme.qcolor(theme.WINDOW_BG))
            painter.setPen(theme.qcolor(theme.TEXT_MUTED))
        else:
            painter.setBrush(theme.qcolor(theme.SURFACE))
            painter.setPen(theme.qcolor(theme.BORDER))
        painter.drawRoundedRect(kasten, theme.CHECK_RADIUS, theme.CHECK_RADIUS)

        if angehakt:
            stift = QPen(theme.qcolor(theme.ON_ACCENT if aktiv else theme.TEXT_MUTED))
            stift.setWidth(theme.CHECK_MARK_WIDTH)
            stift.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(stift)
            painter.drawLine(kasten.left() + 4, kasten.center().y(),
                             kasten.center().x() - 1, kasten.bottom() - 4)
            painter.drawLine(kasten.center().x() - 1, kasten.bottom() - 4,
                             kasten.right() - 3, kasten.top() + 5)
        return kasten.right()

    def sizeHint(self, option, index) -> QSize:  # noqa: D102
        hoehe = (theme.GROUP_ROW_HEIGHT if index.data(KIND_ROLE) == KIND_HEADER
                 else theme.ROW_HEIGHT)
        return QSize(option.rect.width(), hoehe)

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: D102
        """Das Umschalten macht die Liste, nicht der Delegate.

        ``QStyledItemDelegate`` schaltet ein Haekchen selbst um, sobald der
        Klick im Kaestchen-Rechteck des Stils liegt. Zusammen mit
        ``itemClicked`` waere das ein doppeltes Umschalten — die Zeile bliebe
        scheinbar unveraendert, und zwar nur in einem schmalen Streifen links.

        English: The toggling is done by the list, not the delegate.

        ``QStyledItemDelegate`` toggles a checkbox by itself as soon as the
        click lands inside the style's checkbox rectangle. Together with
        ``itemClicked`` that would be a double toggle — the row would appear
        unchanged, and only within a narrow strip on the left.
        """
        return False


class PopupCard(QFrame):
    """Die aufklappende Karte — malt ihren Hintergrund selbst.

    Noetig, weil dieses Top-Level-Fenster unter Windows 11 nichts fuellt, was
    Qt fuellen muesste: weder die Stylesheet-Hintergruende noch die Palette
    kamen an, die Karte blieb schwarz und der dunkle Text darauf unlesbar.
    Raender und Text wurden dagegen gezeichnet — also malen wir die Flaeche
    ebenso ausdruecklich, wie :class:`RowDelegate` es fuer die Zeilen tut.
    Nachgestellt mit drei Varianten (ohne border-radius, nur Palette,
    Transluzenz abgeschaltet); keine davon half.

    English: The popup card — paints its own background.

    Necessary because this top-level window fills nothing under Windows 11
    that Qt should be filling: neither the stylesheet backgrounds nor the
    palette were applied, the card stayed black and the dark text on it
    unreadable. Borders and text, by contrast, were drawn — so we paint the
    surface just as explicitly as :class:`RowDelegate` does for the rows.
    Reproduced with three variants (without border-radius, palette only,
    translucency disabled); none of them helped.
    """

    def paintEvent(self, event) -> None:  # noqa: D102
        painter = QPainter(self)
        # ERST die ganze Flaeche fuellen, DANN den runden Rahmen daraufmalen.
        # Wuerde nur das abgerundete Rechteck gefuellt, blieben an den Ecken
        # schwarze Zwickel stehen: was hier nicht gemalt wird, fuellt niemand,
        # und Transluzenz hat daran nichts geaendert.
        # EN: FIRST fill the entire surface, THEN paint the rounded border on
        # top. If only the rounded rectangle were filled, black wedges would
        # remain in the corners: whatever is not painted here, nobody fills,
        # and translucency changed nothing about that.
        painter.fillRect(self.rect(), theme.qcolor(theme.WINDOW_BG))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(theme.qcolor(theme.BORDER))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1),
                                theme.RADIUS, theme.RADIUS)
        painter.end()
        super().paintEvent(event)


class _AufklappAuswahl(QWidget):
    """Gemeinsame Mechanik von :class:`SearchableSelect` und :class:`MultiSelect`.

    Enthaelt Schaltflaeche, Karte, optionales Suchfeld, Liste, Leermeldung,
    Hoehenanpassung und Tastaturbedienung. Was eine Zeile *bedeutet* — Wert
    setzen oder Haekchen umschalten — steht in den Unterklassen
    (:meth:`_aktiviere`).

    English: Shared mechanics of :class:`SearchableSelect` and
    :class:`MultiSelect`.

    Contains the button, card, optional search field, list, empty message,
    height adjustment and keyboard handling. What a row *means* — setting a
    value or toggling a checkbox — lives in the subclasses
    (:meth:`_aktiviere`).
    """

    def __init__(
        self,
        *,
        mit_suche: bool,
        platzhalter: str = "",
        leer_text: str = "Kein Eintrag passt",
        mit_punkt: bool = True,
        mit_kaestchen: bool = False,
        max_hoehe: int = MAX_CARD_HEIGHT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._max_hoehe = max_hoehe
        # Wird beim Aufklappen gesetzt (siehe _platz_nach_unten).
        # EN: Set when expanding (see _platz_nach_unten).
        self._platz = max_hoehe

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._button = QPushButton()
        self._button.setObjectName(theme.OBJ_SELECT_BUTTON)
        self._button.clicked.connect(self.toggle_popup)
        layout.addWidget(self._button)

        # Qt.Popup: schliesst sich beim Klick daneben und bei Escape von selbst.
        # EN: Qt.Popup: closes itself on a click elsewhere and on Escape.
        self._popup = PopupCard(self, Qt.WindowType.Popup)
        self._popup.setObjectName(theme.OBJ_POPUP)
        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        popup_layout.setSpacing(8)

        # Suchfeld nur, wo es sich lohnt: ueber drei Datenquellen waere es
        # Ballast, ueber elf Attributen mit Namen wie
        # 'site_of_resection_or_biopsy' ist es der schnellste Weg.
        # EN: Search field only where it pays off: over three data sources it
        # would be dead weight, over eleven attributes with names like
        # 'site_of_resection_or_biopsy' it is the fastest way.
        self._search: QLineEdit | None = None
        if mit_suche:
            self._search = QLineEdit()
            self._search.setObjectName(theme.OBJ_SEARCH)
            self._search.setPlaceholderText(platzhalter)
            self._search.setClearButtonEnabled(True)
            self._search.textChanged.connect(self._filter)
            self._search.installEventFilter(self)
            popup_layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName(theme.OBJ_PICKER)
        self._list.setItemDelegate(
            RowDelegate(self._list, mit_punkt=mit_punkt, mit_kaestchen=mit_kaestchen)
        )
        self._list.setMouseTracking(True)          # fuer den Schwebe-Zustand / EN: for the hover state
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.installEventFilter(self)
        self._list.itemClicked.connect(self._geklickt)
        popup_layout.addWidget(self._list)

        # Eigener Hinweis statt einer leeren Liste: ein Kasten ohne Inhalt sieht
        # kaputt aus, nicht wie "nichts gefunden".
        # EN: A dedicated message instead of an empty list: a box with no
        # content looks broken, not like "nothing found".
        self._empty = QLabel(leer_text)
        self._empty.setObjectName(theme.OBJ_ROW_CODE)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()
        popup_layout.addWidget(self._empty)

    # -- Aufbau ------------------------------------------------------------
    @staticmethod
    def _zeile(entry: dict[str, Any]) -> QListWidgetItem:
        """Eine gewoehnliche Zeile aus ``{"value", "label", "code", ...}``.

        English: An ordinary row built from ``{"value", "label", "code", ...}``.
        """
        value = entry.get("value") or ""
        item = QListWidgetItem()
        item.setData(KIND_ROLE, KIND_ROW)
        item.setData(VALUE_ROLE, value)
        item.setData(LABEL_ROLE, entry.get("label") or value)
        item.setData(CODE_ROLE, entry.get("code") or "")
        item.setSizeHint(QSize(0, theme.ROW_HEIGHT))
        return item

    # -- Auswahl -----------------------------------------------------------
    def _geklickt(self, item: QListWidgetItem) -> None:
        """Klick auf eine Zeile. Ueberschriften und deaktivierte Eintraege
        ignorieren — Qt meldet den Klick auch fuer sie.

        English: Click on a row. Ignore headings and disabled entries — Qt
        reports the click for them too.
        """
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self._aktiviere(item)

    def _aktiviere(self, item: QListWidgetItem) -> None:
        """Was ein Klick oder Enter auf dieser Zeile bedeutet.

        English: What a click or Enter on this row means.
        """
        raise NotImplementedError

    # -- Aufklappen --------------------------------------------------------
    def toggle_popup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
            return
        if self._search is not None:
            self._search.clear()      # loest _filter aus: alles wieder sichtbar / EN: triggers _filter: everything visible again
        else:
            self._filter("")
        self._popup.setFixedWidth(max(self._button.width(), 320))
        self._platz = self._platz_nach_unten()
        self._passe_hoehe_an()
        self._popup.move(self._button.mapToGlobal(QPoint(0, self._button.height() + 4)))
        self._popup.show()
        if self._search is not None:
            self._search.setFocus()
        else:
            self._list.setFocus()
        aktuell = self._list.currentItem()
        if aktuell is not None:
            self._list.scrollToItem(aktuell)

    def _grenze(self) -> int:
        """Nie hoeher als erlaubt und nie ueber den Bildschirmrand hinaus; drei
        Zeilen bleiben aber immer stehen, sonst waere die Karte unbrauchbar.

        English: Never taller than allowed and never beyond the screen edge;
        but three rows always remain, otherwise the card would be unusable.
        """
        return max(min(self._max_hoehe, self._platz), 3 * theme.ROW_HEIGHT)

    def _platz_nach_unten(self) -> int:
        """Wie hoch die Liste unter der Schaltflaeche noch werden darf.

        Die Karte ist ein eigenes Fenster und wuerde sonst unten aus dem
        Bildschirm laufen — die Attributkarte ist mit elf Zeilen und drei
        Ueberschriften hoch genug dafuer. Abgezogen wird, was ausser der Liste
        noch in der Karte steckt (Raender, Suchfeld) und ein Rand nach unten.

        English: How tall the list is still allowed to become below the
        button.

        The card is its own window and would otherwise run off the bottom of
        the screen — the attribute card, with eleven rows and three headings,
        is tall enough for that to happen. What is subtracted is whatever else
        is in the card besides the list (margins, search field) and a bottom
        margin.
        """
        bildschirm = self.screen()
        if bildschirm is None:
            return self._max_hoehe
        unterkante = self._button.mapToGlobal(QPoint(0, self._button.height() + 4)).y()
        drumherum = 16 + (self._search.sizeHint().height() + 8 if self._search else 0)
        return bildschirm.availableGeometry().bottom() - unterkante - drumherum - 12

    def _filter(self, text: str) -> None:
        muster = text.strip().lower()
        for row in range(self._list.count()):
            item = self._list.item(row)
            item.setHidden(bool(muster) and muster not in (item.data(SEARCH_ROLE) or ""))
        self._ueberschriften_nachziehen()
        if self._popup.isVisible():
            self._passe_hoehe_an()

    def _ueberschriften_nachziehen(self) -> None:
        """Hook: in :class:`MultiSelect` verschwinden leere Gruppen.

        English: Hook: in :class:`MultiSelect` empty groups disappear.
        """

    def _passe_hoehe_an(self) -> None:
        """Die Karte auf die Trefferzahl schrumpfen (hoechstens ``max_hoehe``).

        Ohne das behaelt das Menue bei zwei Treffern die Hoehe von neun und
        zeigt eine grosse leere Flaeche. Gezaehlt wird in Pixeln und **inklusive
        der Gruppenueberschriften**: nach Zeilenzahl waere die Karte in ``Obj``
        zu klein und wuerde scrollen, obwohl alles hineinpasst.

        English: Shrink the card to the hit count (at most ``max_hoehe``).

        Without this, the menu keeps the height for nine rows even with two
        hits, showing a large empty area. Counted in pixels and **including
        the group headings**: by row count alone the card in ``Obj`` would be
        too small and would scroll even though everything fits.
        """
        hoehe = 0
        treffer = 0
        # Die groesste Hoehe, bei der die Karte mit GANZEN Zeilen endet — sonst
        # steht unten eine halbe Zeile, und genau daran hat man in Aufgabe 17
        # gesehen, dass eine Liste abgeschnitten ist.
        # EN: The greatest height at which the card ends with WHOLE rows —
        # otherwise a half row would sit at the bottom, and that is exactly
        # how, in task 17, a list was seen to be cut off.
        ganze_zeilen = 0
        grenze = self._grenze()
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.isHidden():
                continue
            treffer += 1
            hoehe += item.sizeHint().height()
            if hoehe <= grenze:
                ganze_zeilen = hoehe

        self._empty.setVisible(treffer == 0)
        self._list.setVisible(treffer > 0)
        if treffer:
            self._list.setFixedHeight(min(hoehe, ganze_zeilen or grenze) + 8)
            # Leiste nur zeigen, wenn wirklich mehr da ist als hineinpasst —
            # sonst blitzt sie bei knapp passendem Inhalt neben den Kuerzeln auf.
            # EN: Only show the scrollbar when there really is more than
            # fits — otherwise it flashes next to the codes when the content
            # just barely fits.
            self._list.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded if hoehe > grenze
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        self._popup.adjustSize()

    # -- Tastatur ----------------------------------------------------------
    def eventFilter(self, obj: Any, event: QEvent) -> bool:  # noqa: D102
        """Pfeiltasten und Enter aus dem Suchfeld an die Liste weiterreichen —
        sonst muesste man zum Auswaehlen zur Maus greifen.

        English: Forward arrow keys and Enter from the search field to the
        list — otherwise one would have to reach for the mouse to select.
        """
        # ``getattr``, weil dieser Filter schon waehrend des Aufbaus Ereignisse
        # bekommt — da gibt es die Liste noch nicht.
        # EN: ``getattr`` because this filter already receives events during
        # construction — the list does not exist yet at that point.
        if (event.type() == QEvent.Type.KeyPress
                and obj in (self._search, getattr(self, "_list", None))):
            if self._taste(event.key()):
                return True
        return super().eventFilter(obj, event)

    def _taste(self, taste: int) -> bool:
        """``True``, wenn die Taste hier verbraucht wurde.

        English: ``True`` if the key was consumed here.
        """
        if taste in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._springe(1 if taste == Qt.Key.Key_Down else -1)
            return True
        if taste in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._list.currentItem()
            if item is not None and not item.isHidden():
                self._geklickt(item)
            return True
        return False

    def _springe(self, richtung: int) -> None:
        """Zur naechsten anwaehlbaren, sichtbaren Zeile in ``richtung`` wechseln.

        Uebersprungen werden versteckte Zeilen und Gruppenueberschriften; sonst
        bliebe der Cursor auf einer Zeile stehen, die nichts tut.

        English: Move to the next selectable, visible row in ``richtung``
        (direction).

        Hidden rows and group headings are skipped; otherwise the cursor
        would stay on a row that does nothing.
        """
        reihe = self._list.currentRow()
        for _ in range(self._list.count()):
            reihe += richtung
            if not 0 <= reihe < self._list.count():
                return
            item = self._list.item(reihe)
            if not item.isHidden() and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self._list.setCurrentRow(reihe)
                self._list.scrollToItem(item)
                return


class SearchableSelect(_AufklappAuswahl):
    """Schaltflaeche mit aufklappbarer, durchsuchbarer Liste — **ein** Wert.

    ``entries`` ist eine Liste von ``{"value", "label", "code"}``. Gesendet wird
    immer ``value``; gesucht wird ueber ``code`` und ``value`` — der Klarname
    ist Beschriftung, kein Suchbegriff.

    English: Button with an expandable, searchable list — a **single** value.

    ``entries`` is a list of ``{"value", "label", "code"}``. What is always
    sent is ``value``; the search covers ``code`` and ``value`` — the display
    name is a label, not a search term.
    """

    selection_changed = Signal(str)

    def __init__(self, entries: list[dict[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(
            mit_suche=True,
            # Der Platzhalter nennt das Suchmuster ausdruecklich: seit die Suche
            # nur das Kuerzel trifft, wuerde "lung" sonst kommentarlos leer
            # ausgehen.
            # EN: The placeholder names the search pattern explicitly: since
            # the search only matches the code, "lung" would otherwise come
            # back empty without explanation.
            platzhalter="Kürzel suchen, z. B. BRCA …",
            leer_text="Kein Kürzel passt",
            mit_punkt=True,
            parent=parent,
        )
        self._value = ""
        self._fill(entries)
        # Ohne Vorauswahl starten: die Oberflaeche waehlt nicht fuer den
        # Forscher. Eine vorbelegte Kohorte wird sonst leicht uebersehen und
        # landet im Auftrag, ohne dass jemand sie gewollt hat.
        # EN: Start without a preselection: the UI does not choose for the
        # researcher. Otherwise a preset cohort is easily overlooked and ends
        # up in the request without anyone having wanted it.
        self._beschrifte()

    def _fill(self, entries: list[dict[str, str]]) -> None:
        for entry in entries:
            item = self._zeile(entry)
            item.setToolTip(f"{item.data(LABEL_ROLE)}  ({item.data(VALUE_ROLE)})")
            # Bewusst NUR Kuerzel und Wert, nicht der Klarname: gesucht wird mit
            # der offiziellen Studienabkuerzung (BRCA, LUAD, KIRC). Der Klarname
            # steht weiter in der Zeile, damit man sieht, was sich hinter dem
            # Kuerzel verbirgt — er ist Beschriftung, kein Suchbegriff.
            # EN: Deliberately ONLY code and value, not the display name: the
            # search uses the official study abbreviation (BRCA, LUAD, KIRC).
            # The display name still appears in the row so one can see what
            # is behind the code — it is a label, not a search term.
            item.setData(SEARCH_ROLE,
                         f"{item.data(CODE_ROLE)} {item.data(VALUE_ROLE)}".lower())
            self._list.addItem(item)

    def current_value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        """Einen Wert waehlen; ``""`` setzt die Auswahl zurueck.

        English: Choose a value; ``""`` resets the selection.
        """
        if not value:
            self._value = ""
            self._list.setCurrentRow(-1)
            self._beschrifte()
            self.selection_changed.emit("")
            return
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(VALUE_ROLE) == value:
                self._value = value
                self._list.setCurrentItem(item)
                self._beschrifte(f"{item.data(LABEL_ROLE)}   ·   {item.data(CODE_ROLE)}")
                self.selection_changed.emit(value)
                return

    def _beschrifte(self, text: str = "") -> None:
        """Die Schaltflaeche beschriften — ohne Auswahl gedaempft, wie bei der
        Mehrfachauswahl.

        English: Label the button — muted without a selection, as with the
        multi-select.
        """
        self._button.setText(text or "Keine Auswahl")
        self._button.setStyleSheet(theme.select_button_style(not text))

    def _aktiviere(self, item: QListWidgetItem) -> None:
        self.set_value(item.data(VALUE_ROLE) or "")
        self._popup.hide()


class MultiSelect(_AufklappAuswahl):
    """Schaltflaeche mit aufklappbarer Haekchenliste — **mehrere** Werte.

    ``entries`` sind Zeilen ``{"value", "label", "code", "enabled", "tooltip",
    "search"}`` und Gruppenueberschriften ``{"kind": "header", "label"}``. Der
    Unterschied zu :class:`SearchableSelect`:

    - Ein Klick schaltet das Haekchen um, **die Karte bleibt offen** — sonst
      muesste man sie fuer jedes Attribut neu aufklappen.
    - Die Beschriftung der Schaltflaeche fasst mehrere Werte zusammen.
    - ``checked_values()`` liefert **Panel-Reihenfolge**, nicht Klick-Reihenfolge:
      der Client reicht die Reihenfolge unveraendert an den Mediator durch
      (``test_build_request_takes_the_checked_attributes_in_order``), eine
      Klick-Reihenfolge landete also unbemerkt im Auftrag.

    Geschlossen wird ueber Escape, Klick daneben oder erneuten Klick auf die
    Schaltflaeche.

    English: Button with an expandable checkbox list — **multiple** values.

    ``entries`` are rows ``{"value", "label", "code", "enabled", "tooltip",
    "search"}`` and group headings ``{"kind": "header", "label"}``. The
    difference from :class:`SearchableSelect`:

    - A click toggles the checkbox, **the card stays open** — otherwise it
      would have to be reopened for every attribute.
    - The button's label summarizes multiple values.
    - ``checked_values()`` returns **panel order**, not click order: the
      client passes the order through unchanged to the mediator
      (``test_build_request_takes_the_checked_attributes_in_order``), so a
      click order would silently end up in the request.

    Closed via Escape, a click elsewhere, or clicking the button again.
    """

    selection_changed = Signal(list)

    def __init__(
        self,
        entries: list[dict[str, Any]],
        *,
        mit_suche: bool = False,
        platzhalter: str = "",
        leer_text: str = "Kein Eintrag passt",
        mit_punkt: bool = False,
        max_hoehe: int = MAX_CARD_HEIGHT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            mit_suche=mit_suche,
            platzhalter=platzhalter,
            leer_text=leer_text,
            # In ``Obj`` und ``Datenquelle`` haette der farbige Anker keine
            # Bedeutung; die Kohortenliste behaelt ihn, sie hatte ihn schon.
            # EN: In ``Obj`` and ``Datenquelle`` the colored marker would have
            # no meaning; the cohort list keeps it, it already had it.
            mit_punkt=mit_punkt,
            mit_kaestchen=True,
            max_hoehe=max_hoehe,
            parent=parent,
        )
        self._fill(entries)
        self._beschrifte()

    # -- Aufbau ------------------------------------------------------------
    def _fill(self, entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            if entry.get("kind") == KIND_HEADER:
                item = QListWidgetItem()
                item.setData(KIND_ROLE, KIND_HEADER)
                item.setData(LABEL_ROLE, entry.get("label") or "")
                item.setData(SEARCH_ROLE, "")
                item.setSizeHint(QSize(0, theme.GROUP_ROW_HEIGHT))
                # Nicht anwaehlbar, kein Haekchen: eine Ueberschrift traegt
                # keinen Wert und darf nie im Auftrag landen.
                # EN: Not selectable, no checkbox: a heading carries no value
                # and must never end up in the request.
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self._list.addItem(item)
                continue

            item = self._zeile(entry)
            item.setData(SEARCH_ROLE, (entry.get("search") or entry.get("value") or "").lower())
            item.setToolTip(entry.get("tooltip") or "")
            if entry.get("enabled", True):
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if entry.get("checked")
                    else Qt.CheckState.Unchecked
                )
            else:
                # Sichtbar, aber nicht anhakbar — ehrliche Luecke statt
                # unsichtbarer Grenze. Der Grund steht als Hinweis rechts in der
                # Zeile (``code``) und im Tooltip.
                # EN: Visible but not checkable — an honest gap instead of an
                # invisible limit. The reason is shown as a hint on the right
                # of the row (``code``) and in the tooltip.
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)

    # -- Auswahl -----------------------------------------------------------
    def checked_values(self) -> list[str]:
        """Die angehakten Werte in Panel-Reihenfolge.

        English: The checked values in panel order.
        """
        werte = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            wert = item.data(VALUE_ROLE)
            if wert and item.checkState() == Qt.CheckState.Checked:
                werte.append(wert)
        return werte

    def set_checked(self, values: list[str]) -> None:
        gewuenscht = set(values)
        for row in range(self._list.count()):
            item = self._list.item(row)
            wert = item.data(VALUE_ROLE)
            if not wert or not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                continue
            item.setCheckState(
                Qt.CheckState.Checked if wert in gewuenscht else Qt.CheckState.Unchecked
            )
        self._beschrifte()

    def _aktiviere(self, item: QListWidgetItem) -> None:
        """Haekchen umschalten — und die Karte **offen lassen**.

        English: Toggle the checkbox — and **leave the card open**.
        """
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        item.setCheckState(
            Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        self._list.setCurrentItem(item)
        self._beschrifte()

    def _taste(self, taste: int) -> bool:
        # Leertaste schaltet die Zeile unter dem Cursor um — auch wenn der
        # Fokus im Suchfeld steht: ein Leerzeichen taugt dort ohnehin nicht als
        # Suchbegriff (Attributnamen tragen Unterstriche), und ohne das muesste
        # man zum Anhaken zur Maus greifen.
        # EN: Space toggles the row under the cursor — even when the focus is
        # in the search field: a space is useless there as a search term
        # anyway (attribute names contain underscores), and without this one
        # would have to reach for the mouse to check a box.
        if taste == Qt.Key.Key_Space:
            item = self._list.currentItem()
            if item is not None and not item.isHidden():
                self._geklickt(item)
            return True
        return super()._taste(taste)

    # -- Beschriftung ------------------------------------------------------
    def _beschrifte(self) -> None:
        """Die Schaltflaeche zeigt die Auswahl, ohne umzubrechen.

        Das Panel ist rund 360 Pixel breit: ab drei Werten stehen dort die
        ersten beiden plus ``+N``, der vollstaendige Satz im Tooltip.

        English: The button shows the selection without wrapping.

        The panel is around 360 pixels wide: from three values onward it
        shows the first two plus ``+N``, with the full set in the tooltip.
        """
        kurz, namen = [], []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(VALUE_ROLE) and item.checkState() == Qt.CheckState.Checked:
                name = item.data(LABEL_ROLE) or item.data(VALUE_ROLE)
                namen.append(name)
                # Auf der Schaltflaeche steht das Kuerzel, wo es eines gibt:
                # "BRCA · KIRC +1" passt ins Panel, drei Klarnamen nicht. Der
                # volle Satz steht im Tooltip.
                # EN: The button shows the code where one exists: "BRCA ·
                # KIRC +1" fits the panel, three display names do not. The
                # full set is in the tooltip.
                kurz.append(item.data(CODE_ROLE) or name)

        if not namen:
            self._button.setText("Keine Auswahl")
            self._button.setToolTip("")
        elif len(kurz) <= 2:
            self._button.setText(" · ".join(kurz))
            self._button.setToolTip(", ".join(namen))
        else:
            self._button.setText(f"{kurz[0]} · {kurz[1]} +{len(kurz) - 2}")
            self._button.setToolTip(", ".join(namen))
        self._button.setStyleSheet(theme.select_button_style(not namen))
        self.selection_changed.emit(self.checked_values())

    # -- Filtern -----------------------------------------------------------
    def _ueberschriften_nachziehen(self) -> None:
        """Eine Gruppenueberschrift verschwindet, wenn keines ihrer Attribute
        mehr passt — sonst steht 'Sample' allein ueber einer leeren Flaeche und
        sieht nach einem Fehler aus.

        English: A group heading disappears when none of its attributes
        still match — otherwise 'Sample' would stand alone over an empty
        area and look like a bug.
        """
        kopf: QListWidgetItem | None = None
        treffer = False
        for row in range(self._list.count() + 1):
            item = self._list.item(row) if row < self._list.count() else None
            if item is None or item.data(KIND_ROLE) == KIND_HEADER:
                if kopf is not None:
                    kopf.setHidden(not treffer)
                kopf, treffer = item, False
                continue
            if not item.isHidden():
                treffer = True
