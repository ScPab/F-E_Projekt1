"""Farben und Stylesheet an genau **einer** Stelle.

Ausserhalb dieser Datei steht kein Farbwert im Code (Aufgabe 17, Deliverable 5).
Wer das Aussehen aendert, aendert es hier — nicht verstreut in ``main_window``.

Das Stylesheet wird in ``app.py`` einmal auf die ``QApplication`` gesetzt und
gilt damit fuer alle Fenster.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# --- Farben ----------------------------------------------------------------
HEADER_BG = "#101827"
HEADER_TEXT = "#ffffff"
HEADER_TEXT_MUTED = "#8b95a6"

WINDOW_BG = "#ffffff"
SURFACE = "#f6f7f9"          # Panel- und Kartenflaeche
BORDER = "#dfe3e9"
TEXT = "#1b2230"
TEXT_MUTED = "#6b7280"

ACCENT = "#2563eb"           # Auswahl, aktiver Rand, Schaltflaeche "Generieren"
ACCENT_BG = "#e6eefc"
ON_ACCENT = "#ffffff"        # was auf der Akzentflaeche liegt (Haekchen, Text)

SUCCESS = "#0d8a5f"
SUCCESS_BG = "#dff5ec"
WARNING = "#b45309"
WARNING_BG = "#fdf0dc"
ERROR = "#b42318"
ERROR_BG = "#fde8e6"

# --- Masse und Schriften ---------------------------------------------------
RADIUS = 8                   # Eckenradius in Pixel
BORDER_WIDTH = 1
FONT_FAMILY = '"Segoe UI", "Noto Sans", sans-serif'
FONT_SIZE_PT = 10
MONO_FAMILY = '"Consolas", "Cascadia Mono", monospace'

HEADER_HEIGHT = 56
PANEL_WIDTH = 360
ROW_HEIGHT = 38              # Zeilenhoehe in den Auswahllisten
GROUP_ROW_HEIGHT = 26        # Gruppenueberschrift in einer Auswahlliste
DOT_SIZE = 12                # runder Anker links in einer Zeile

# Haekchen-Kaestchen in den Mehrfachauswahl-Zeilen. Es wird gezeichnet, nicht
# per Stylesheet gesetzt (QListWidget::indicator greift in der aufklappenden
# Karte nicht, siehe PopupCard) — Groesse und Abstand gehoeren deshalb hierher
# und nicht in den Delegate.
CHECK_SIZE = 16              # Kantenlaenge des Kaestchens
CHECK_RADIUS = 4             # dessen Eckenradius
CHECK_GAP = 12               # Abstand zwischen Kaestchen und Text
CHECK_MARK_WIDTH = 2         # Strichstaerke des Hakens

# Objektnamen, ueber die das Stylesheet einzelne Widgets adressiert. Als
# Konstanten, damit ein Tippfehler nicht zu stillem Stilverlust fuehrt.
OBJ_HEADER = "Header"
OBJ_HEADER_TITLE = "HeaderTitle"
OBJ_HEADER_SUBTITLE = "HeaderSubtitle"
OBJ_PANEL = "Panel"
OBJ_PANEL_LABEL = "PanelLabel"
OBJ_OUTPUT = "Output"
OBJ_PRIMARY_BUTTON = "PrimaryButton"
OBJ_SEARCH = "SearchField"
OBJ_PICKER = "PickerList"          # Liste mit Suchfeld darueber (Kohorten)
OBJ_ROW_LABEL = "RowLabel"         # Hauptbeschriftung einer Listenzeile
OBJ_ROW_CODE = "RowCode"           # gedaempftes Kuerzel rechts
OBJ_ROW_DOT = "RowDot"             # runder Anker links
OBJ_SELECT_BUTTON = "SelectButton"  # Schaltflaeche, die die Auswahl aufklappt
OBJ_POPUP = "SelectPopup"           # die aufklappende Karte selbst


def stylesheet() -> str:
    """Das vollstaendige Qt-Stylesheet der Anwendung."""
    return f"""
QWidget {{
    background-color: {WINDOW_BG};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_PT}pt;
}}

/* --- Kopfzeile --------------------------------------------------------- */
QFrame#{OBJ_HEADER} {{
    background-color: {HEADER_BG};
    border: none;
}}
QLabel#{OBJ_HEADER_TITLE} {{
    background-color: transparent;
    color: {HEADER_TEXT};
    font-size: {FONT_SIZE_PT + 4}pt;
    font-weight: 600;
}}
QLabel#{OBJ_HEADER_SUBTITLE} {{
    background-color: transparent;
    color: {HEADER_TEXT_MUTED};
    font-size: {FONT_SIZE_PT + 4}pt;
}}

/* --- Auswahlpanel ------------------------------------------------------ */
QFrame#{OBJ_PANEL} {{
    background-color: {SURFACE};
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QFrame#{OBJ_PANEL} QWidget {{
    background-color: transparent;
}}
QLabel#{OBJ_PANEL_LABEL} {{
    color: {TEXT_MUTED};
    font-weight: 600;
    background-color: transparent;
}}

/* --- Anzeigeflaeche ---------------------------------------------------- */
QPlainTextEdit#{OBJ_OUTPUT} {{
    background-color: {SURFACE};
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 10px;
    font-family: {MONO_FAMILY};
    selection-background-color: {ACCENT_BG};
    selection-color: {TEXT};
}}

/* --- Eingaben ---------------------------------------------------------- */
QComboBox, QSpinBox, QListWidget {{
    background-color: {WINDOW_BG};
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 5px 8px;
}}
QComboBox:focus, QSpinBox:focus, QListWidget:focus {{
    border-color: {ACCENT};
}}
QComboBox:disabled, QSpinBox:disabled {{
    color: {TEXT_MUTED};
    background-color: {SURFACE};
}}
/* Aufklappliste einer QComboBox. Ohne diese Regeln erbt das Popup unter
   Windows 11 die dunkle Systempalette und wird mit unserer dunklen Schriftfarbe
   unlesbar. Deshalb Hintergrund UND Textfarbe hier explizit, je Zustand. */
QComboBox QAbstractItemView {{
    background-color: {WINDOW_BG};
    color: {TEXT};
    border: {BORDER_WIDTH}px solid {BORDER};
    selection-background-color: {ACCENT_BG};
    selection-color: {TEXT};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    background-color: {WINDOW_BG};
    color: {TEXT};
    padding: 4px 8px;
}}
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {{
    background-color: {ACCENT_BG};
    color: {TEXT};
}}
QComboBox QAbstractItemView::item:disabled {{
    background-color: {WINDOW_BG};
    color: {TEXT_MUTED};
}}
/* --- Aufklappbare Auswahl (searchable_select.py) ------------------------ */
/* Sieht aus wie ein Eingabefeld, nicht wie eine Schaltflaeche: es zeigt einen
   Wert an, es loest keine Aktion aus. */
QPushButton#{OBJ_SELECT_BUTTON} {{
    background-color: {WINDOW_BG};
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 7px 12px;
    text-align: left;
    font-weight: 400;
}}
QPushButton#{OBJ_SELECT_BUTTON}:hover {{
    border-color: {ACCENT};
}}
/* Flaeche und Rahmen malt PopupCard.paintEvent selbst (siehe dort, warum);
   hier deshalb nichts als "nicht dazwischenmalen". */
QFrame#{OBJ_POPUP} {{
    background: transparent;
    border: none;
}}

/* --- Suchfeld ueber einer Auswahlliste ---------------------------------- */
QLineEdit#{OBJ_SEARCH} {{
    background-color: {WINDOW_BG};
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 7px 10px;
    selection-background-color: {ACCENT_BG};
    selection-color: {TEXT};
}}
QLineEdit#{OBJ_SEARCH}:focus {{
    border-color: {ACCENT};
}}

/* --- Zeilen in den Auswahllisten --------------------------------------- */
/* Abgerundete, grosszuegige Zeilen statt der Qt-Standardleiste: die
   Auswahlhervorhebung soll wie eine Karte wirken, nicht wie ein Balken. */
/* Durchscheinend: die Flaeche darunter malt PopupCard. Ein eigener
   Hintergrund wuerde im Popup-Fenster ohnehin nicht gefuellt. */
QListWidget#{OBJ_PICKER} {{
    background: transparent;
    border: none;
    outline: none;
}}
/* Zeilenhintergrund und -rahmen malt RowDelegate selbst (es braucht die
   Breite, um Name zu kuerzen und Kuerzel rechts zu setzen) — hier deshalb
   KEINE ::item-Regeln, sonst wird zweimal gemalt. */
QLabel#{OBJ_ROW_LABEL} {{
    background-color: transparent;
    color: {TEXT};
}}
QLabel#{OBJ_ROW_CODE} {{
    background-color: transparent;
    color: {TEXT_MUTED};
    font-weight: 600;
}}
QLabel#{OBJ_ROW_DOT} {{
    background-color: transparent;
}}

QListWidget::item {{
    padding: 3px 2px;
}}
/* Haekchen: der Fusion-Stil zeichnet das Kaestchen sonst als dunkle Flaeche,
   weil QWidget oben nur Hintergrund und Textfarbe setzt. Deshalb hier
   ausdruecklich, je Zustand. */
QListWidget::indicator {{
    width: 14px;
    height: 14px;
    margin-right: 6px;
    border: {BORDER_WIDTH}px solid {TEXT_MUTED};
    border-radius: 3px;
    background-color: {WINDOW_BG};
}}
QListWidget::indicator:hover {{
    border-color: {ACCENT};
}}
QListWidget::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QListWidget::indicator:disabled {{
    background-color: {SURFACE};
    border-color: {BORDER};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_BG};
    color: {TEXT};
}}

/* --- Schaltflaechen ---------------------------------------------------- */
QPushButton {{
    background-color: {WINDOW_BG};
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 7px 18px;
    min-width: 110px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: {SURFACE};
    border-color: {BORDER};
}}
QPushButton#{OBJ_PRIMARY_BUTTON} {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: {HEADER_TEXT};
    font-weight: 600;
}}
QPushButton#{OBJ_PRIMARY_BUTTON}:hover {{
    background-color: {HEADER_BG};
    border-color: {HEADER_BG};
}}
QPushButton#{OBJ_PRIMARY_BUTTON}:disabled {{
    background-color: {ACCENT_BG};
    border-color: {ACCENT_BG};
    color: {TEXT_MUTED};
}}

/* --- Bildlaufleisten ---------------------------------------------------- */
/* Schlank und ohne Pfeilkaestchen: der Fusion-Standard ist breit, kantig und
   draengt sich in den Inhalt (in der Kohortenliste bis in die Kuerzel hinein). */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 2px 2px 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0 2px 2px 2px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{ min-height: 28px; }}
QScrollBar::handle:horizontal {{ min-width: 28px; }}
QScrollBar::handle:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0; border: none; background: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* --- Statusleiste und Splitter ----------------------------------------- */
QStatusBar {{
    background-color: {SURFACE};
    border-top: {BORDER_WIDTH}px solid {BORDER};
    color: {TEXT_MUTED};
}}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background-color: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
"""


# --- Zustandsfarben fuer die Statusleiste ----------------------------------
# Die Statusleiste wird je Meldung eingefaerbt; auch diese Zuordnung gehoert
# hierher und nicht ins Fenster.
_STATE_COLORS = {
    "info": (TEXT_MUTED, SURFACE),
    "busy": (ACCENT, ACCENT_BG),
    "success": (SUCCESS, SUCCESS_BG),
    "warning": (WARNING, WARNING_BG),
    "error": (ERROR, ERROR_BG),
}


def qcolor(value: str) -> QColor:
    """Eine der Farbkonstanten oben als ``QColor`` — fuer alles, was gezeichnet
    statt per Stylesheet gesetzt wird (z. B. der Zeilen-Delegate)."""
    return QColor(value)


def dot_color(key: str) -> QColor:
    """Farbe des runden Ankers links in einer Kohortenzeile.

    **Rein optisch**: sie macht die Liste scanbar, so wie die Flagge in der
    Vorlage, und kodiert nichts. Insbesondere ist es NICHT die MP-Lite-Palette —
    sollen die Farben dort und hier dieselben sein, muss die Palette aus dem
    Prototyp herkommen, nicht neu erfunden werden.

    Deterministisch aus dem Schluessel, damit dieselbe Kohorte immer dieselbe
    Farbe hat; Sattheit und Helligkeit fest, damit nichts grell wird.
    """
    farbton = (sum(ord(c) * (i + 1) for i, c in enumerate(key)) * 47) % 360
    return QColor.fromHsl(farbton, 150, 150)


def select_button_style(leer: bool) -> str:
    """Stylesheet-Fragment fuer die Schaltflaeche einer aufklappenden Auswahl.

    Zeigt sie eine Auswahl, steht sie in normaler Textfarbe; zeigt sie
    ``Keine Auswahl``, in gedaempfter — sonst liest sich der Platzhalter wie ein
    gewaehlter Wert. Als Funktion hier, damit auch diese Fallunterscheidung
    keinen Farbwert in ``searchable_select.py`` braucht.
    """
    return f"QPushButton#{OBJ_SELECT_BUTTON} {{ color: {TEXT_MUTED if leer else TEXT}; }}"


def palette() -> QPalette:
    """Helle Palette, unabhaengig vom Windows-Hell/Dunkel-Modus.

    Das Stylesheet allein genuegt nicht: Aufklapplisten und andere Popups
    bekommen unter Windows 11 eigene Fenster und erben dort die dunkle
    Systempalette. Zusammen mit ``setStyle("Fusion")`` in ``app.py`` ist die
    Darstellung damit auf jedem Rechner dieselbe.
    """
    pal = QPalette()
    text, muted = QColor(TEXT), QColor(TEXT_MUTED)
    window, base, surface = QColor(WINDOW_BG), QColor(WINDOW_BG), QColor(SURFACE)
    accent, on_accent = QColor(ACCENT), QColor(HEADER_TEXT)

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        pal.setColor(group, QPalette.ColorRole.Window, window)
        pal.setColor(group, QPalette.ColorRole.WindowText, text)
        pal.setColor(group, QPalette.ColorRole.Base, base)
        pal.setColor(group, QPalette.ColorRole.AlternateBase, surface)
        pal.setColor(group, QPalette.ColorRole.Text, text)
        pal.setColor(group, QPalette.ColorRole.Button, window)
        pal.setColor(group, QPalette.ColorRole.ButtonText, text)
        pal.setColor(group, QPalette.ColorRole.ToolTipBase, surface)
        pal.setColor(group, QPalette.ColorRole.ToolTipText, text)
        pal.setColor(group, QPalette.ColorRole.Highlight, accent)
        pal.setColor(group, QPalette.ColorRole.HighlightedText, on_accent)
        pal.setColor(group, QPalette.ColorRole.PlaceholderText, muted)

    disabled = QPalette.ColorGroup.Disabled
    pal.setColor(disabled, QPalette.ColorRole.Window, window)
    pal.setColor(disabled, QPalette.ColorRole.Base, window)
    pal.setColor(disabled, QPalette.ColorRole.Button, surface)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText, QPalette.ColorRole.HighlightedText):
        pal.setColor(disabled, role, muted)
    return pal


def status_style(state: str) -> str:
    """Stylesheet-Fragment fuer die Statusleiste im gegebenen Zustand."""
    fg, bg = _STATE_COLORS.get(state, _STATE_COLORS["info"])
    return (
        f"QStatusBar {{ background-color: {bg}; color: {fg}; "
        f"border-top: {BORDER_WIDTH}px solid {BORDER}; }}"
    )
