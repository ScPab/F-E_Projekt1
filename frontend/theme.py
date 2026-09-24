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

# --- Netzansicht (netz_view.py) --------------------------------------------
# Masse des gezeichneten Netzes. Sie stehen hier aus demselben Grund wie die
# Kaestchenmasse: was gezeichnet statt per Stylesheet gesetzt wird, gehoert
# trotzdem an die eine Stelle.
NETZ_NODE_WIDTH = 132        # Breite eines Knotens
NETZ_ROOT_WIDTH = 190        # die Wurzel traegt zwei Zahlen und ist breiter
NETZ_NODE_WIDTH_3 = 162      # Attributknoten: Faelle, Werte und der Zuwachs
NETZ_NODE_HEIGHT = 46        # Hoehe eines Knotens (Wurzel, Kohorte)
NETZ_NODE_HEIGHT_3 = 62      # Attributknoten: eine Zeile mehr (Panel-Name)
NETZ_NODE_GAP = 12           # Abstand zwischen zwei Knoten einer Reihe
NETZ_ROW_GAP = 58            # senkrechter Abstand zwischen zwei Reihen
NETZ_MAX_NODES = 7           # mehr Knoten je Reihe werden zu "… N weitere"
NETZ_BORDER_OPEN = 2         # dickerer Rand des aufgeklappten Knotens

# --- Projektion (projektion_view.py) ---------------------------------------
SLIDER_COLUMN_WIDTH = 240    # Breite der Reglerspalte rechts neben der Karte
SCATTER_POINT_SIZE = 8       # Durchmesser eines Punktes in der Karte
SCATTER_HOVER_PLUS = 4       # so viel groesser wird er unter der Maus
MAP_MIN_HEIGHT = 220         # so gross bleibt die Karte mindestens
LEGEND_WIDTH = 96            # Breite der Kohorten-Legende rechts der Karte
# Achsen und Gitter der Karte bewusst dunkler als BORDER: der Rahmen einer
# Eingabe darf zurueckhaltend sein, eine Achse muss man ablesen koennen.
AXIS = "#6b7280"             # Achsenlinie, Beschriftung und Gitter
GRID_ALPHA = 0.6             # Deckkraft des Gitters in der Karte
NEUTRAL = "#9E9E9E"          # Kohorte unbekannt oder fehlend

# --- Architekturansicht (architektur_view.py) ------------------------------
ARCH_BOX_WIDTH = 250         # Breite einer Station (Symbol, Komponente, Beleg)
ARCH_BOX_HEIGHT = 62         # deren Hoehe
ARCH_ICON = 30               # Kantenlaenge des Symbols links im Kasten
ARCH_ICON_MARGIN = 12        # dessen Abstand zum Rand
# Die Linie, die waehrend eines Aufrufs am Rand entlanglaeuft ("border line
# overlay"): Laenge des leuchtenden Stuecks, Breite, Tempo und wie weit der
# Schein darunter ausblutet.
ARCH_PULS_LAENGE = 48        # Laenge des wandernden Stuecks in Szeneneinheiten
ARCH_PULS_BREITE = 3         # Strichstaerke
ARCH_PULS_TEMPO = 150.0      # Einheiten je Sekunde
ARCH_PULS_SCHEIN = 3         # so viele Lagen Schein unter der Linie
ARCH_PULS_SCHWEIF = 7        # so viele Glieder hat der Schweif hinter dem Kopf
ARCH_TAKT_MS = 40            # Bildtakt der Animation (25 Bilder je Sekunde)
ARCH_PRO_ZEILE = 3           # so viele Stationen stehen nebeneinander
ARCH_ZEILEN_ABSTAND = 58     # senkrechter Abstand zwischen den beiden Zeilen
# Die Pfeile bewusst in Textfarbe statt in BORDER: in BORDER (dem Ton fuer
# Rahmen von Eingabefeldern) waren sie auf hellem Grund kaum zu sehen.
ARCH_PFEIL = TEXT
ARCH_PFEIL_BREITE = 2
ARCH_GAP = 26                # Abstand zwischen zwei Stationen (Platz fuer den Pfeil)

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
OBJ_NETZ = "NetzView"               # die gezeichnete Netzansicht
OBJ_NETZ_TITLE = "NetzTitle"        # fette Ueberschrift ueber dem Netz
OBJ_NETZ_NOTE = "NetzNote"          # gedaempfter Zusatz rechts daneben
OBJ_SWITCH_LEFT = "ViewSwitchLeft"    # linke Haelfte des Ansichts-Umschalters
OBJ_SWITCH_RIGHT = "ViewSwitchRight"  # rechte Haelfte desselben
OBJ_SLIDER_NAME = "SliderName"        # Beschriftung eines Projektions-Reglers
OBJ_SLIDER_VALUE = "SliderValue"      # dessen Zahlenwert rechts
OBJ_PROJ_HINT = "ProjektionHinweis"   # Meldung anstelle der Karte


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

/* --- Netzansicht -------------------------------------------------------- */
/* Die Szene malt ihre Flaeche selbst (setBackgroundBrush); hier nur der Rahmen,
   damit das Netz wie die Anzeigeflaeche darunter als Karte wirkt. */
QGraphicsView#{OBJ_NETZ} {{
    border: {BORDER_WIDTH}px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QLabel#{OBJ_NETZ_TITLE} {{
    color: {TEXT};
    font-weight: 600;
    background-color: transparent;
}}
QLabel#{OBJ_NETZ_NOTE} {{
    color: {TEXT_MUTED};
    background-color: transparent;
}}

/* --- Umschalter Wissensnetz / Projektion -------------------------------- */
/* Zwei Schaltflaechen, die wie ein Stueck aussehen: aussen gerundet, in der
   Mitte stossen sie ohne doppelte Linie aneinander. */
QPushButton#{OBJ_SWITCH_LEFT}, QPushButton#{OBJ_SWITCH_RIGHT} {{
    background-color: {SURFACE};
    color: {TEXT};
    border: {BORDER_WIDTH}px solid {BORDER};
    padding: 5px 16px;
    min-width: 0;
    font-weight: 600;
}}
QPushButton#{OBJ_SWITCH_LEFT} {{
    border-top-left-radius: {RADIUS}px;
    border-bottom-left-radius: {RADIUS}px;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    border-right: none;
}}
QPushButton#{OBJ_SWITCH_RIGHT} {{
    border-top-right-radius: {RADIUS}px;
    border-bottom-right-radius: {RADIUS}px;
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
}}
QPushButton#{OBJ_SWITCH_LEFT}:checked, QPushButton#{OBJ_SWITCH_RIGHT}:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: {ON_ACCENT};
}}
QPushButton#{OBJ_SWITCH_LEFT}:hover:!checked, QPushButton#{OBJ_SWITCH_RIGHT}:hover:!checked {{
    border-color: {ACCENT};
}}

/* --- Regler der Projektion ---------------------------------------------- */
QLabel#{OBJ_SLIDER_NAME} {{
    background-color: transparent;
    color: {TEXT};
}}
QLabel#{OBJ_SLIDER_NAME}:disabled {{
    color: {TEXT_MUTED};
}}
QLabel#{OBJ_SLIDER_VALUE} {{
    background-color: transparent;
    color: {TEXT_MUTED};
}}
QLabel#{OBJ_PROJ_HINT} {{
    background-color: transparent;
    color: {TEXT_MUTED};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {WINDOW_BG};
    border: {BORDER_WIDTH}px solid {ACCENT};
    width: 12px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:disabled {{
    border-color: {BORDER};
    background: {SURFACE};
}}
QSlider::sub-page:horizontal:disabled {{
    background: {BORDER};
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


def mit_deckkraft(farbe: str, anteil: float) -> QColor:
    """Eine Farbkonstante mit Deckkraft — fuer den Schein unter der Laufschrift.

    Auch das gehoert hierher: ausserhalb dieser Datei soll niemand an Farben
    rechnen muessen.
    """
    c = QColor(farbe)
    c.setAlphaF(max(0.0, min(1.0, anteil)))
    return c


def cohort_colors() -> dict[str, str]:
    """Farbe je Krebsart, stabil ueber die Position in ``OVIEDO_COHORTS``.

    matplotlibs ``nipy_spectral`` wie im Oviedo-Original und wie in MP-Lite,
    damit dieselbe Kohorte dort und hier dieselbe Farbe hat. Fehlt matplotlib,
    ein HSV-Faecher als Rueckfall — die Karte soll nicht an einer Colormap
    scheitern.
    """
    from wissensnetz.cohorts import OVIEDO_COHORTS

    codes = list(OVIEDO_COHORTS)
    n = len(codes)
    try:
        from matplotlib import colormaps
        from matplotlib.colors import to_hex

        cmap = colormaps["nipy_spectral"]
        return {c: to_hex(cmap((i + 0.5) / n)) for i, c in enumerate(codes)}
    except Exception:      # noqa: BLE001 - kein matplotlib -> HSV-Faecher
        import colorsys

        farben = {}
        for i, c in enumerate(codes):
            r, g, b = colorsys.hsv_to_rgb(i / n, 0.65, 0.9)
            farben[c] = "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255),
                                                     int(b * 255))
        return farben


_COHORT_COLORS: dict[str, str] | None = None


def cohort_color(code: str | None) -> QColor:
    """Die Farbe einer Kohorte; unbekannt oder fehlend -> neutrales Grau.

    Das ist **nicht** ``dot_color``: der farbige Punkt in den Auswahllisten ist
    rein optisch und kodiert nichts, diese Palette hier kodiert die Kohorte und
    ist dieselbe wie in MP-Lite.
    """
    global _COHORT_COLORS
    if _COHORT_COLORS is None:
        _COHORT_COLORS = cohort_colors()
    return QColor(_COHORT_COLORS.get(code, NEUTRAL) if code else NEUTRAL)


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
