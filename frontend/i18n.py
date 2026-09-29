"""Mehrsprachigkeit der Auswahl-Oberflaeche (Deutsch/Englisch/Spanisch).

Bewusst kein Qt-Linguist-Workflow (``self.tr()`` + ``.ts``/``.qm`` + ``lupdate``):
das waere für drei feste Sprachen und eine Handvoll Oberflaechen-Texte mehr
Maschinerie als Nutzen. Stattdessen ein einfaches Woerterbuch
``TRANSLATIONS[key][sprache]`` plus ``tr(key)``, das gegen die aktuell
gewaehlte Sprache aufloest (Vorgabe Englisch, siehe ``DEFAULT_LANGUAGE``) und
sonst auf Englisch, dann auf den Schluessel selbst zurueckfaellt — eine neue
Zeile ist also nie ein Absturz, nur ein sichtbarer Platzhalter.

Uebersetzt werden bewusst nur feste Oberflaechen-Texte (Knoepfe, Beschriftungen,
Menue, Spaltenkoepfe, Platzhalter, Leer-Zustaende) — keine Lauftext-/
Fehlermeldungen, die Zahlen, Dateinamen oder Serverantworten einbetten; die
bleiben Deutsch (siehe Gespraech vom 2026-09-29).

``translator`` ist ein Singleton mit einem Qt-Signal ``language_changed``: wer
uebersetzten Text zeigt, verbindet sich einmal darauf und baut seinen eigenen
Text bei jedem Sprachwechsel neu auf (siehe ``MainWindow.retranslate_ui``
sowie ``_AufklappAuswahl.retranslate`` in ``searchable_select.py``).

English: Multilingual support for the selection UI (German/English/Spanish).

Deliberately not the Qt Linguist workflow (``self.tr()`` + ``.ts``/``.qm`` +
``lupdate``): for three fixed languages and a handful of UI strings that
would be more machinery than benefit. Instead a plain dictionary
``TRANSLATIONS[key][language]`` plus ``tr(key)``, which resolves against the
currently selected language (default English, see ``DEFAULT_LANGUAGE``) and
otherwise falls back to English, then to the key itself — a new line is
therefore never a crash, only a visible placeholder.

Only fixed UI chrome is translated on purpose (buttons, labels, menu, column
headers, placeholders, empty states) — not running status/error text that
embeds numbers, filenames, or server responses; that stays German (see the
2026-09-29 conversation).

``translator`` is a singleton with a Qt signal ``language_changed``: whoever
displays translated text connects to it once and rebuilds its own text on
every language change (see ``MainWindow.retranslate_ui`` and
``_AufklappAuswahl.retranslate`` in ``searchable_select.py``).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

ENGLISH = "en"
GERMAN = "de"
SPANISH = "es"

DEFAULT_LANGUAGE = ENGLISH

# Anzeigename je Sprache — steht selbst nicht im Woerterbuch unten, weil er in
# JEDER Sprache in seiner eigenen Sprache erscheinen soll (Menue zum
# Sprachwechsel zeigt "Deutsch"/"English"/"Español" gleichzeitig).
# EN: Display name per language — not itself in the dictionary below,
# because it should appear in its OWN language regardless of the current
# one (the language-switch menu shows "Deutsch"/"English"/"Español" at the
# same time).
LANGUAGE_NAMES: dict[str, str] = {
    ENGLISH: "English",
    GERMAN: "Deutsch",
    SPANISH: "Español",
}

_SETTINGS_ORG = "DataBridge"
_SETTINGS_APP = "Explorer"
_SETTINGS_KEY = "language"

# TRANSLATIONS[schluessel][sprache] = Text. Deutsch ist der Ursprungstext, an
# dem sich Englisch/Spanisch orientieren; die Aufteilung nach Bereich folgt
# main_window.py/searchable_select.py/projektion_view.py.
# EN: TRANSLATIONS[key][language] = text. German is the original text that
# English/Spanish are checked against; the grouping by area follows
# main_window.py/searchable_select.py/projektion_view.py.
TRANSLATIONS: dict[str, dict[str, str]] = {
    # -- Menue / EN: Menu -----------------------------------------------
    "menu_file": {ENGLISH: "&File", GERMAN: "&Datei", SPANISH: "&Archivo"},
    "menu_view": {ENGLISH: "&View", GERMAN: "&Ansicht", SPANISH: "&Ver"},
    "menu_refresh_net": {ENGLISH: "Refresh job", GERMAN: "Suchauftrag aktualisieren", SPANISH: "Actualizar solicitud"},
    "menu_save_h5ad": {ENGLISH: "Save as .h5ad", GERMAN: "Als .h5ad speichern", SPANISH: "Guardar como .h5ad"},
    "menu_language": {ENGLISH: "Language", GERMAN: "Sprache", SPANISH: "Idioma"},

    # -- Dialoge / EN: Dialogs --------------------------------------------
    "dialog_save_h5ad_title": {
        ENGLISH: "Save as .h5ad", GERMAN: "Als .h5ad speichern", SPANISH: "Guardar como .h5ad",
    },
    "dialog_file_filter": {
        ENGLISH: "AnnData (*.h5ad);;All files (*)",
        GERMAN: "AnnData (*.h5ad);;Alle Dateien (*)",
        SPANISH: "AnnData (*.h5ad);;Todos los archivos (*)",
    },

    # -- Kopfzeile / EN: Header --------------------------------------------
    "store_prefix": {ENGLISH: "Store: —", GERMAN: "Store: —", SPANISH: "Store: —"},

    # -- Aktionsknoepfe / EN: Action buttons -------------------------------
    "button_preview": {ENGLISH: "Preview", GERMAN: "Vorschau", SPANISH: "Vista previa"},
    "button_generate": {ENGLISH: "Generate", GERMAN: "Generieren", SPANISH: "Generar"},
    "button_save_h5ad": {ENGLISH: "Save as .h5ad", GERMAN: "Als .h5ad speichern", SPANISH: "Guardar como .h5ad"},

    # -- Ansichts-Umschalter / EN: View switch -----------------------------
    "view_net": {ENGLISH: "Job", GERMAN: "Suchauftrag", SPANISH: "Solicitud"},
    "view_projection": {ENGLISH: "Projection", GERMAN: "Projektion", SPANISH: "Proyección"},
    "view_net_hint": {
        ENGLISH: "Structure and counts, no measurement data",
        GERMAN: "Struktur und Zählungen, keine Messdaten",
        SPANISH: "Estructura y recuentos, sin datos de medición",
    },
    "view_no_file_loaded": {
        ENGLISH: "No file loaded", GERMAN: "Keine Datei geladen", SPANISH: "Ningún archivo cargado",
    },
    "view_projection_empty_hint": {
        ENGLISH: "No file loaded.\nChoose a .h5ad via `Open file …`.",
        GERMAN: "Keine Datei geladen.\nÜber `Datei öffnen …` eine .h5ad wählen.",
        SPANISH: "Ningún archivo cargado.\nElige un .h5ad con `Abrir archivo …`.",
    },
    "button_open_file": {
        ENGLISH: "Open file …", GERMAN: "Datei öffnen …", SPANISH: "Abrir archivo …",
    },
    "button_open_job_from_h5ad": {
        ENGLISH: "Job from .h5ad …", GERMAN: "Auftrag aus .h5ad …", SPANISH: "Solicitud desde .h5ad …",
    },
    "button_open_job_from_h5ad_tooltip": {
        ENGLISH: "Open a finished .h5ad and restore the selection from it",
        GERMAN: "Eine fertige .h5ad öffnen und die Auswahl daraus wiederherstellen",
        SPANISH: "Abrir un .h5ad terminado y restaurar la selección a partir de él",
    },
    "dialog_open_job_title": {
        ENGLISH: "Read job from AnnData",
        GERMAN: "Auftrag aus AnnData lesen",
        SPANISH: "Leer solicitud desde AnnData",
    },
    "dialog_open_h5ad_title": {
        ENGLISH: "Open AnnData", GERMAN: "AnnData öffnen", SPANISH: "Abrir AnnData",
    },

    # -- Unterer Umschalter / EN: Bottom switch ----------------------------
    "bottom_architecture": {ENGLISH: "Architecture", GERMAN: "Architektur", SPANISH: "Arquitectura"},
    "bottom_text_output": {ENGLISH: "Text output", GERMAN: "Textausgabe", SPANISH: "Salida de texto"},
    "bottom_hint_architecture": {
        ENGLISH: "What is happening in the background",
        GERMAN: "Was im Hintergrund passiert",
        SPANISH: "Qué está pasando en segundo plano",
    },
    "bottom_hint_text": {
        ENGLISH: "The mediator's response, unchanged",
        GERMAN: "Die Antwort des Mediators, unverändert",
        SPANISH: "La respuesta del mediador, sin cambios",
    },

    # -- Ausgabe-Platzhalter (Ausgangszustand) / EN: Output placeholder (initial state) --
    "output_placeholder": {
        ENGLISH: "No request made yet.\n\n"
                 "Assemble a selection on the right, then 'Preview' (metadata only)\n"
                 "or 'Generate' (also raw data and .h5ad).\n\n"
                 "Exactly the mediator's response is shown.",
        GERMAN: "Noch keine Anfrage gestellt.\n\n"
                "Rechts eine Auswahl zusammenstellen, dann 'Vorschau' (nur Metadaten)\n"
                "oder 'Generieren' (zusätzlich Rohdaten und .h5ad).\n\n"
                "Angezeigt wird genau die Antwort des Mediators.",
        SPANISH: "Aún no se ha realizado ninguna solicitud.\n\n"
                 "Monta una selección a la derecha, luego 'Vista previa' (solo metadatos)\n"
                 "o 'Generar' (además datos en bruto y .h5ad).\n\n"
                 "Se muestra exactamente la respuesta del mediador.",
    },

    # -- Auswahlpanel: Spaltenkoepfe / EN: Selection panel: column headers --
    "panel_cancer": {ENGLISH: "Cancer", GERMAN: "Krebs", SPANISH: "Cáncer"},
    "panel_variable": {ENGLISH: "Var", GERMAN: "Var", SPANISH: "Var"},
    "panel_object": {ENGLISH: "Obj", GERMAN: "Obj", SPANISH: "Obj"},
    "panel_data_source": {ENGLISH: "Data source", GERMAN: "Datenquelle", SPANISH: "Fuente de datos"},
    "panel_samples": {ENGLISH: "Samples", GERMAN: "Proben", SPANISH: "Muestras"},

    # -- Auswahlpanel: Suchfelder/Leerzustaende / EN: Selection panel: search fields/empty states --
    "cohort_search_placeholder": {
        ENGLISH: "Search code, e.g. BRCA …",
        GERMAN: "Kürzel suchen, z. B. BRCA …",
        SPANISH: "Buscar código, p. ej. BRCA …",
    },
    "cohort_search_empty": {
        ENGLISH: "No code matches", GERMAN: "Kein Kürzel passt", SPANISH: "Ningún código coincide",
    },
    "attribute_search_placeholder": {
        ENGLISH: "Search attribute or node, e.g. stage …",
        GERMAN: "Attribut oder Knoten suchen, z. B. stage …",
        SPANISH: "Buscar atributo o nodo, p. ej. stage …",
    },
    "attribute_search_empty": {
        ENGLISH: "No attribute matches", GERMAN: "Kein Attribut passt", SPANISH: "Ningún atributo coincide",
    },

    # -- Aufklapp-Auswahl (allgemein) / EN: Popup selection (generic) -----
    "select_no_selection": {
        ENGLISH: "No selection", GERMAN: "Keine Auswahl", SPANISH: "Sin selección",
    },
    "select_no_entry_matches": {
        ENGLISH: "No entry matches", GERMAN: "Kein Eintrag passt", SPANISH: "Ninguna entrada coincide",
    },

    # -- Sprachauswahl selbst / EN: The language picker itself ------------
    "language_button_tooltip": {
        ENGLISH: "Change language", GERMAN: "Sprache ändern", SPANISH: "Cambiar idioma",
    },

    # -- Netzansicht (netz_view.py) — die gezeichneten Knoten / EN: Net view — the drawn nodes --
    "net_root_title": {ENGLISH: "Selection", GERMAN: "Auswahl", SPANISH: "Selección"},
    "net_store_empty": {
        ENGLISH: "Nothing in the store for this selection yet.\nEvery preview extends the store.",
        GERMAN: "Zu dieser Auswahl liegt noch nichts im Store.\nJede Vorschau erweitert den Store.",
        SPANISH: "Aún no hay nada en el store para esta selección.\nCada vista previa amplía el store.",
    },
    "net_attributes_apply_hint": {
        ENGLISH: "Attributes apply to all selected cohorts",
        GERMAN: "Attribute gelten für alle gewählten Kohorten",
        SPANISH: "Los atributos se aplican a todas las cohortes seleccionadas",
    },
    "net_more_items": {
        ENGLISH: "… {n} more {items}", GERMAN: "… {n} weitere {items}", SPANISH: "… {n} {items} más",
    },
    "count_cohort_1": {ENGLISH: "cohort", GERMAN: "Kohorte", SPANISH: "cohorte"},
    "count_cohort_n": {ENGLISH: "cohorts", GERMAN: "Kohorten", SPANISH: "cohortes"},
    "count_case_1": {ENGLISH: "case", GERMAN: "Fall", SPANISH: "caso"},
    "count_case_n": {ENGLISH: "cases", GERMAN: "Fälle", SPANISH: "casos"},
    "count_value_1": {ENGLISH: "value", GERMAN: "Wert", SPANISH: "valor"},
    "count_value_n": {ENGLISH: "values", GERMAN: "Werte", SPANISH: "valores"},
    "count_attribute_1": {ENGLISH: "attribute", GERMAN: "Attribut", SPANISH: "atributo"},
    "count_attribute_n": {ENGLISH: "attributes", GERMAN: "Attribute", SPANISH: "atributos"},

    # -- Architekturansicht: Stationsnamen (architektur_view.py) ----------
    # EN: Architecture view: station names (architektur_view.py) ---------
    # Die Werte von ablauf.AUFTRAG/MEDIATOR/... bleiben als Identitaet
    # unveraendert (Stationssuche/Tests vergleichen dagegen) — hier wird nur
    # die ANZEIGE uebersetzt, ueber architektur_view._stationsname().
    # EN: The values of ablauf.AUFTRAG/MEDIATOR/... stay unchanged as
    # identity (station lookup/tests compare against them) — only the
    # DISPLAY is translated here, via architektur_view._stationsname().
    "station_auftrag": {ENGLISH: "Selection → JSON", GERMAN: "Auswahl → JSON", SPANISH: "Selección → JSON"},
    "station_mediator": {ENGLISH: "Mediator", GERMAN: "Mediator", SPANISH: "Mediador"},
    "station_wrapper": {
        ENGLISH: "Wrapper → data source", GERMAN: "Wrapper → Datenquelle", SPANISH: "Wrapper → fuente de datos",
    },
    "station_mapping": {ENGLISH: "GDC JSON → RDF", GERMAN: "GDC-JSON → RDF", SPANISH: "GDC JSON → RDF"},
    "station_fuseki": {ENGLISH: "graph-db (Fuseki)", GERMAN: "graph-db (Fuseki)", SPANISH: "graph-db (Fuseki)"},
    "station_wissensnetz": {ENGLISH: "Knowledge net", GERMAN: "Wissensnetz", SPANISH: "Red de conocimiento"},

    # -- Kurze, feste Statusmeldungen (keine eingebetteten Laufzeitwerte) --
    # EN: Short, fixed status messages (no embedded runtime values) -------
    "status_no_cohort": {
        ENGLISH: "No cohort checked.", GERMAN: "Keine Kohorte angehakt.", SPANISH: "Ninguna cohorte marcada.",
    },
    "status_no_source": {
        ENGLISH: "No data source checked.", GERMAN: "Keine Datenquelle angehakt.",
        SPANISH: "Ninguna fuente de datos marcada.",
    },
    "status_no_source_hint_1": {
        ENGLISH: "Check at least one source on the right under 'Data source'.",
        GERMAN: "Rechts unter 'Datenquelle' mindestens eine Quelle ankreuzen.",
        SPANISH: "Marca al menos una fuente a la derecha bajo 'Fuente de datos'.",
    },
    "status_no_source_hint_2": {
        ENGLISH: "Every checked source becomes its own level in the request.",
        GERMAN: "Je angehakter Quelle entsteht eine eigene Ebene im Auftrag.",
        SPANISH: "Cada fuente marcada genera su propio nivel en la solicitud.",
    },
    "status_download_running": {
        ENGLISH: "A download is already running — please wait.",
        GERMAN: "Es läuft bereits ein Download — bitte warten.",
        SPANISH: "Ya hay una descarga en curso — espera, por favor.",
    },
    "status_file_loading": {
        ENGLISH: "A file is already being loaded — please wait.",
        GERMAN: "Es wird bereits eine Datei geladen — bitte warten.",
        SPANISH: "Ya se está cargando un archivo — espera, por favor.",
    },
    "status_download_failed": {
        ENGLISH: "Download failed.", GERMAN: "Download fehlgeschlagen.", SPANISH: "Error al descargar.",
    },
    "status_no_levels": {
        ENGLISH: "Response without levels.", GERMAN: "Antwort ohne Ebenen.", SPANISH: "Respuesta sin niveles.",
    },
    "status_no_levels_body": {
        ENGLISH: "The mediator returned no selection level.",
        GERMAN: "Der Mediator hat keine Auswahl-Ebene zurückgegeben.",
        SPANISH: "El mediador no devolvió ningún nivel de selección.",
    },
    "status_error_fallback": {
        ENGLISH: "Error", GERMAN: "Fehler", SPANISH: "Error",
    },
    "status_store_unreachable": {
        ENGLISH: "Store: unreachable", GERMAN: "Store: nicht erreichbar", SPANISH: "Store: inaccesible",
    },
    "net_nothing_selected": {
        ENGLISH: "Nothing selected yet.\nCheck cohorts and choose attributes on the right.",
        GERMAN: "Noch nichts ausgewählt.\nRechts Kohorten anhaken und Attribute wählen.",
        SPANISH: "Aún no se ha seleccionado nada.\nMarca cohortes y elige atributos a la derecha.",
    },
    "wissensnetz_not_installed": {
        ENGLISH: "wissensnetz not installed — cohorts from config/panel.json (pip install -e ./wissensnetz)",
        GERMAN: "wissensnetz nicht installiert — Kohorten aus config/panel.json (pip install -e ./wissensnetz)",
        SPANISH: "wissensnetz no instalado — cohortes desde config/panel.json (pip install -e ./wissensnetz)",
    },
}


class Translator(QObject):
    """Haelt die aktuell gewaehlte Sprache und meldet Aenderungen per Signal.

    English: Holds the currently selected language and reports changes via
    signal.
    """

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        stored = settings.value(_SETTINGS_KEY, DEFAULT_LANGUAGE)
        self._language = stored if stored in LANGUAGE_NAMES else DEFAULT_LANGUAGE

    def language(self) -> str:
        return self._language

    def set_language(self, code: str) -> None:
        """Sprache wechseln, in ``QSettings`` merken und ``language_changed``
        senden. Unbekannter Code oder unveraenderte Sprache: No-op.

        English: Switch language, remember it in ``QSettings`` and emit
        ``language_changed``. Unknown code or unchanged language: no-op.
        """
        if code not in LANGUAGE_NAMES or code == self._language:
            return
        self._language = code
        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY, code)
        self.language_changed.emit(code)

    def tr(self, key: str) -> str:
        """Text zum Schluessel in der aktuellen Sprache; faellt auf Englisch,
        dann auf den Schluessel selbst zurueck (siehe Modul-Docstring).

        English: Text for the key in the current language; falls back to
        English, then to the key itself (see module docstring).
        """
        entry = TRANSLATIONS.get(key)
        if entry is None:
            return key
        return entry.get(self._language) or entry.get(DEFAULT_LANGUAGE) or key


# Ein Singleton fuers ganze Fenster — dieselbe Instanz wie bei jedem Import.
# EN: One singleton for the whole window — the same instance on every import.
translator = Translator()


def tr(key: str) -> str:
    """Kurzform fuer ``translator.tr(key)``.

    English: Shorthand for ``translator.tr(key)``.
    """
    return translator.tr(key)
