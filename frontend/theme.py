"""Farben und Stylesheet an genau **einer** Stelle.

Ausserhalb dieser Datei steht kein Farbwert im Code (Aufgabe 17, Deliverable 5).
Wer das Aussehen aendert, aendert es hier — nicht verstreut in ``main_window``.

Das Stylesheet wird in ``app.py`` einmal auf die ``QApplication`` gesetzt und
gilt damit fuer alle Fenster.
"""

from __future__ import annotations

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

# Objektnamen, ueber die das Stylesheet einzelne Widgets adressiert. Als
# Konstanten, damit ein Tippfehler nicht zu stillem Stilverlust fuehrt.
OBJ_HEADER = "Header"
OBJ_HEADER_TITLE = "HeaderTitle"
OBJ_HEADER_SUBTITLE = "HeaderSubtitle"
OBJ_PANEL = "Panel"
OBJ_PANEL_LABEL = "PanelLabel"
OBJ_OUTPUT = "Output"
OBJ_PRIMARY_BUTTON = "PrimaryButton"


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
QComboBox QAbstractItemView {{
    background-color: {WINDOW_BG};
    border: {BORDER_WIDTH}px solid {BORDER};
    selection-background-color: {ACCENT_BG};
    selection-color: {TEXT};
    outline: none;
}}
QListWidget::item {{
    padding: 3px 2px;
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


def status_style(state: str) -> str:
    """Stylesheet-Fragment fuer die Statusleiste im gegebenen Zustand."""
    fg, bg = _STATE_COLORS.get(state, _STATE_COLORS["info"])
    return (
        f"QStatusBar {{ background-color: {bg}; color: {fg}; "
        f"border-top: {BORDER_WIDTH}px solid {BORDER}; }}"
    )
