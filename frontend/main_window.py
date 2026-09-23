"""Fenster, Auswahlpanel, Signals und Slots.

Aufbau nach der Handskizze (ADR-0004, Punkt 2): links die Anzeigeflaeche, rechts
das Auswahlpanel, unter der Anzeigeflaeche die beiden Schaltflaechen, unten die
Statusleiste.

**Diese Fassung liest NICHT aus dem Wissensnetz.** Kein ``GraphStore``, kein
``cases_for_selection`` — die Anzeigeflaeche zeigt genau das, was der Mediator
selbst zurueckgibt. Einzige Ausnahme beim Import: die Kohorten-Konstante
``wissensnetz.cohorts.COHORT_PROJECT_IDS``, damit Ladeskript, MP-Lite und
Oberflaeche dieselbe Wahrheit nutzen (Aufgabe 17, Deliverable 11).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import mediator_client as mc
import store_reader as sr
import theme
import worker
from netz_view import NetzPanel
from projektion_view import ProjektionPanel
from searchable_select import KIND_HEADER, MultiSelect

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "panel.json"

# Wie viele Turtle-Zeilen als Ausschnitt angehaengt werden.
TURTLE_PREVIEW_LINES = 40

# Wie hoch die aufgeklappte Attributkarte hoechstens wird. Elf Attribute und
# drei Gruppenueberschriften passen damit ohne Scrollen hinein und bleiben auch
# auf einem 768 Pixel hohen Bildschirm unter der Schaltflaeche sichtbar.
_ATTRIBUTE_CARD_HEIGHT = 520



def load_panel_config() -> dict[str, Any]:
    """``config/panel.json`` lesen. Fehlt sie, bleibt die Oberflaeche leer,
    statt beim Start abzustuerzen."""
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def load_cohorts(config: dict[str, Any]) -> tuple[list[str], str | None]:
    """Kohortenliste beschaffen. Gibt ``(kohorten, hinweis)`` zurueck.

    Fuehrend ist ``wissensnetz.cohorts.COHORT_PROJECT_IDS`` — nur eine Konstante
    aus einem installierten Paket, **kein** Zugriff auf den Store. Schlaegt der
    Import fehl, greift die Liste aus ``panel.json``, und der Hinweis wandert in
    die Statusleiste.
    """
    try:
        from wissensnetz.cohorts import COHORT_PROJECT_IDS

        return list(COHORT_PROJECT_IDS), None
    except ImportError:
        fallback = list(config.get("cohorts") or [])
        return fallback, (
            "wissensnetz nicht installiert — Kohorten aus config/panel.json "
            "(pip install -e ./wissensnetz)"
        )


def _kontext_aus_store(barcode: str) -> dict[str, Any] | None:
    """Kontext einer Probe aus dem Wissensnetz — laeuft im Worker-Thread.

    Der Schluessel ist ``obs["submitter_id"]`` gegen ``db:submitterId``;
    ``case_context`` nimmt beides, Case-IRI oder ``submitterId``. Der Store kommt
    aus ``store_reader``, es wird keine zweite Instanz angelegt.
    """
    from wissensnetz.enrichment import case_context

    store = sr.default_store()
    if not sr.is_reachable(store):
        raise RuntimeError(
            f"Fuseki unter {sr.store_url(store)} nicht erreichbar. "
            "Laeuft `docker compose up`? Die Karte bleibt bedienbar."
        )
    return case_context(store, barcode)


class MainWindow(QMainWindow):
    """Das Hauptfenster: Auswahl zusammenstellen, abschicken, Antwort zeigen."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DataBridge Explorer")
        self.resize(1200, 760)
        self.setMinimumSize(900, 600)

        self._config = load_panel_config()
        self._cohorts, cohort_note = load_cohorts(self._config)
        # Thread und Worker festhalten, solange der Aufruf laeuft. Faellt die
        # letzte Python-Referenz, waehrend der QThread noch laeuft, beendet Qt
        # den Prozess hart ("Destroyed while thread is still running").
        self._thread = None
        self._worker = None
        # Dieselbe Regel fuer den separaten Download-Thread (siehe worker.py).
        self._dl_thread = None
        self._dl_worker = None
        # Ebenso fuer das Laden einer .h5ad und die Kontextabfrage der Projektion.
        self._h5_thread = None
        self._h5_worker = None
        self._kontext_thread = None
        self._kontext_worker = None
        # Zuletzt gespeicherte .h5ad — die Projektion laedt sie, sobald man auf
        # sie umschaltet (nicht vorher, siehe _wechsle_ansicht).
        self._offene_h5ad = ""
        # Ebenen des letzten erfolgreichen 'Generieren'-Laufs mit .h5ad —
        # Grundlage fuer das Download-Menue (siehe _update_download_menu).
        self._downloadable: list[dict[str, Any]] = []

        self._build_menu()
        self._build_ui()
        self._fill_panel()

        if cohort_note:
            self.set_status(cohort_note, "warning")
        else:
            self.set_status(
                f"Bereit. Mediator: {mc.default_base_url()}  ·  "
                f"{len(self._cohorts)} Kohorten geladen.",
                "info",
            )

        # Abzug A des laufenden Aufrufs und der zuletzt gezeichnete Stand.
        # Beide werden im Worker-Thread gesetzt und erst danach im GUI-Thread
        # gelesen (siehe _abzug_vorher/_abzug_nachher und _on_finished).
        self._abzug_a: dict[str, Any] | None = None
        self._letzter_abzug: dict[str, Any] | None = None
        self._netz_aktualisieren()

        # Das Netz zieht mit der Auswahl mit, ohne den Store erneut zu fragen:
        # gezeichnet wird aus dem zuletzt gelesenen Abzug.
        self._cohort_select.selection_changed.connect(self._auswahl_geaendert)
        self._attribute_select.selection_changed.connect(self._auswahl_geaendert)

    # -- Menue ---------------------------------------------------------------
    def _build_menu(self) -> None:
        """Menueleiste mit dem Download-Eintrag.

        Das ``.h5ad`` entsteht im Mediator-Container und ist von dort aus
        nicht als Host-Pfad sichtbar (siehe ``mediator_client.download``) —
        dieses Menue ist der Weg, es ohne Docker-Kommandozeile auf die
        eigene Platte zu bekommen. Ein Untermenue statt einer einzelnen
        Aktion, weil mehrere angehakte Datenquellen mehrere Ebenen und damit
        mehrere ``.h5ad``-Dateien liefern koennen (ADR-0003, Entscheidung
        7.2) — mit nur einer Ebene steht dort eben genau ein Eintrag.
        Deaktiviert, bis ein 'Generieren'-Lauf etwas Herunterladbares
        liefert (siehe ``_update_download_menu``).
        """
        file_menu = self.menuBar().addMenu("&Datei")
        self._download_menu = QMenu("Als .h5ad speichern", self)
        self._download_menu.setEnabled(False)
        file_menu.addMenu(self._download_menu)

        # Der Store aendert sich auch ohne diese Oberflaeche, etwa durch
        # scripts/run_selection.py oder start_all.ps1 -FullLoad. Ohne diesen
        # Eintrag altert das Bild still.
        view_menu = self.menuBar().addMenu("&Ansicht")
        refresh = QAction("Netz aktualisieren", self)
        refresh.setShortcut("F5")
        refresh.triggered.connect(self._netz_aktualisieren)
        view_menu.addAction(refresh)

    def _collect_downloadable(self, levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ebenen mit erfolgreich erzeugtem ``.h5ad`` aus einer Mediator-Antwort.

        Nur ``status="ok"`` UND vorhandene ``anndata.download_url`` zaehlen —
        eine fehlgeschlagene Ebene oder eine Vorschau hat keine Datei zum
        Holen (siehe ``SelectionLevelResult`` im Mediator).
        """
        entries: list[dict[str, Any]] = []
        for level in levels:
            anndata = level.get("anndata") or {}
            url = anndata.get("download_url")
            if level.get("status") != "ok" or not url:
                continue
            sel = level.get("selection") or {}
            cohorts = ", ".join(sel.get("cohorts") or []) or "?"
            entries.append({
                "label": f"{sel.get('source') or '?'} — {cohorts}",
                "download_url": url,
                "filename": anndata.get("filename") or "export.h5ad",
            })
        return entries

    def _update_download_menu(self, entries: list[dict[str, Any]]) -> None:
        """Download-Untermenue UND den Download-Button neu einrichten (nach
        jedem 'Generieren') — beide teilen sich dieselbe Liste, damit sie nie
        auseinanderlaufen."""
        self._downloadable = entries
        self._download_menu.clear()
        self._download_menu.setEnabled(bool(entries))
        self._download_button.setEnabled(bool(entries))
        for entry in entries:
            action = QAction(f"{entry['label']}  ({entry['filename']}) …", self)
            action.triggered.connect(lambda checked=False, e=entry: self._download_h5ad(e))
            self._download_menu.addAction(action)

    def _on_download_button_clicked(self) -> None:
        """Bei genau einer Ebene direkt den Speichern-Dialog oeffnen, bei
        mehreren (mehrere angehakte Datenquellen) dieselbe Auswahl wie im
        Menue als Popup unter dem Button zeigen."""
        if not self._downloadable:
            return
        if len(self._downloadable) == 1:
            self._download_h5ad(self._downloadable[0])
            return
        self._download_menu.exec(
            self._download_button.mapToGlobal(QPoint(0, self._download_button.height()))
        )

    def _download_h5ad(self, entry: dict[str, Any]) -> None:
        """Speichern-Dialog zeigen und die Datei im Hintergrund herunterladen.

        Vorschlag fuer Ordner/Name: ``wissensnetz/data/<filename>`` — dieselbe
        Konvention wie ``start_all.ps1 -DemoGenerate``/``run_selection.py --out``,
        damit MP-Lite/Explorer dieselben Ablagen kennen. Der Nutzer kann das
        im Dialog jederzeit aendern.
        """
        if self._dl_thread is not None:
            self.set_status("Es laeuft bereits ein Download — bitte warten.", "warning")
            return

        default_dir = Path(__file__).resolve().parent.parent / "wissensnetz" / "data"
        suggested = str(default_dir / entry["filename"])
        path, _ = QFileDialog.getSaveFileName(
            self, "Als .h5ad speichern", suggested, "AnnData (*.h5ad);;Alle Dateien (*)"
        )
        if not path:
            return

        self.set_status(f"Lade {entry['filename']} herunter … Das Fenster bleibt bedienbar.", "busy")
        self._dl_thread, self._dl_worker = worker.start_download(
            entry["download_url"], path, self._on_download_finished
        )
        self._dl_thread.finished.connect(self._release_download_thread)

    def _on_download_finished(self, result: mc.Result) -> None:
        if result.ok:
            # Die gerade erzeugte Datei ist der erste der drei Wege zur
            # Projektion (geladen wird sie erst beim Umschalten).
            self._offene_h5ad = str(result.data.get("path") or "")
            self.set_status(f"Gespeichert: {result.data.get('path')}", "success")
        else:
            self.set_status(result.error or "Download fehlgeschlagen.", "error")

    def _release_download_thread(self) -> None:
        """Wie ``_release_thread``, aber fuer den Download-Thread (siehe dort)."""
        self._dl_thread = None
        self._dl_worker = None

    # -- Aufbau ------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._build_display_side())
        self._splitter.addWidget(self._build_panel())
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([1200 - theme.PANEL_WIDTH, theme.PANEL_WIDTH])
        body_layout.addWidget(self._splitter)

        root_layout.addWidget(body, stretch=1)
        self.setCentralWidget(root)

        self._status = QStatusBar()
        # Zusaetzlich rechts ein dauerhaftes Feld mit dem Stand des Stores:
        # set_status() schreibt weiterhin links, die beiden kollidieren nicht.
        self._store_label = QLabel("Store: —")
        self._status.addPermanentWidget(self._store_label)
        self.setStatusBar(self._status)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName(theme.OBJ_HEADER)
        header.setFixedHeight(theme.HEADER_HEIGHT)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        title = QLabel("DataBridge")
        title.setObjectName(theme.OBJ_HEADER_TITLE)
        subtitle = QLabel("Explorer")
        subtitle.setObjectName(theme.OBJ_HEADER_SUBTITLE)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)
        return header

    def _build_display_side(self) -> QWidget:
        """Anzeigeflaeche plus die beiden Schaltflaechen darunter."""
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(12)

        self._output = QPlainTextEdit()
        self._output.setObjectName(theme.OBJ_OUTPUT)
        self._output.setReadOnly(True)
        self._output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._output.setPlainText(
            "Noch keine Anfrage gestellt.\n\n"
            "Rechts eine Auswahl zusammenstellen, dann 'Vorschau' (nur Metadaten)\n"
            "oder 'Generieren' (zusaetzlich Rohdaten und .h5ad).\n\n"
            "Angezeigt wird genau die Antwort des Mediators."
        )
        # Senkrechter Splitter statt der einen Zeile: oben die Ansichten, unten
        # unveraendert self._output (dasselbe Widget, nicht neu gebaut). Ein
        # Splitter im Splitter — gewollt und der kleinstmoegliche Eingriff.
        # Die Stellung wird bewusst nicht gespeichert.
        self._netz = NetzPanel(self._attribut_namen())
        self._projektion = ProjektionPanel()
        self._projektion.datei_gewuenscht.connect(self._lade_h5ad)
        self._projektion.probe_geklickt.connect(self._hole_kontext)

        self._ansichten = QStackedWidget()
        self._ansichten.addWidget(self._netz)
        self._ansichten.addWidget(self._projektion)
        self._ansichten.setMinimumHeight(260)
        self._output.setMinimumHeight(120)

        self._anzeige = anzeige = QSplitter(Qt.Orientation.Vertical)
        anzeige.addWidget(self._baue_umschalter())
        anzeige.addWidget(self._ansichten)
        anzeige.addWidget(self._output)
        # Die Titelzeile ist kein Feld zum Ziehen: nur die beiden Flaechen
        # darunter teilen sich den Platz.
        anzeige.setStretchFactor(1, 3)
        anzeige.setStretchFactor(2, 2)
        anzeige.setSizes([28, 360, 240])
        anzeige.handle(1).setEnabled(False)
        layout.addWidget(anzeige, stretch=1)

        self._aktionen = buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)

        self._preview_button = QPushButton("Vorschau")
        self._preview_button.clicked.connect(lambda: self._start("preview"))
        self._generate_button = QPushButton("Generieren")
        self._generate_button.setObjectName(theme.OBJ_PRIMARY_BUTTON)
        self._generate_button.clicked.connect(lambda: self._start("generate"))
        # Sichtbarer Button statt nur des "Datei"-Menues: ein Menueintrag
        # allein wurde beim Testen nicht gefunden ("steht nur die download_url
        # da, aber nirgendwo wo ich es herunterladen kann") — der Button steht
        # direkt neben den anderen beiden Aktionen und ist daher nicht zu
        # uebersehen. Deaktiviert, bis 'Generieren' etwas Herunterladbares
        # liefert (siehe _update_download_menu).
        self._download_button = QPushButton("Als .h5ad speichern")
        self._download_button.setEnabled(False)
        self._download_button.clicked.connect(self._on_download_button_clicked)

        button_layout.addWidget(self._preview_button)
        button_layout.addWidget(self._generate_button)
        button_layout.addWidget(self._download_button)
        button_layout.addStretch(1)
        layout.addWidget(buttons)
        return side

    def _baue_umschalter(self) -> QWidget:
        """Die Titelzeile ueber der Anzeige: links der Umschalter, rechts ein
        Hinweis, der zur jeweiligen Ansicht passt.

        Umschalten ist rein optisch und hat **keine Nebenwirkung**: es stoesst
        keinen Abruf an, laedt keine Datei und verwirft keinen Zustand.
        """
        zeile = QWidget()
        layout = QHBoxLayout(zeile)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        self._knopf_netz = QPushButton("Wissensnetz")
        self._knopf_netz.setObjectName(theme.OBJ_SWITCH_LEFT)
        self._knopf_projektion = QPushButton("Projektion")
        self._knopf_projektion.setObjectName(theme.OBJ_SWITCH_RIGHT)
        for knopf in (self._knopf_netz, self._knopf_projektion):
            knopf.setCheckable(True)
        self._knopf_netz.setChecked(True)

        self._ansichtsgruppe = QButtonGroup(self)
        self._ansichtsgruppe.setExclusive(True)
        self._ansichtsgruppe.addButton(self._knopf_netz, 0)
        self._ansichtsgruppe.addButton(self._knopf_projektion, 1)
        self._ansichtsgruppe.idClicked.connect(self._wechsle_ansicht)

        layout.addWidget(self._knopf_netz)
        layout.addWidget(self._knopf_projektion)
        layout.addStretch(1)

        self._ansicht_hinweis = QLabel("Struktur und Zaehlungen, keine Messdaten")
        self._ansicht_hinweis.setObjectName(theme.OBJ_NETZ_NOTE)
        layout.addWidget(self._ansicht_hinweis)
        return zeile

    # -- Projektion ----------------------------------------------------------
    def _wechsle_ansicht(self, index: int) -> None:
        self._ansichten.setCurrentIndex(index)
        self._raum_fuer_projektion(index == 1)
        if index == 0:
            self._ansicht_hinweis.setText("Struktur und Zaehlungen, keine Messdaten")
            return
        self._ansicht_hinweis.setText(self._projektion_hinweis())
        # Erst beim Umschalten laden, nicht vorher: 44 MB sollen nicht ungefragt
        # von der Platte kommen, nur weil ein Auftrag fertig wurde.
        if not self._projektion.hat_modell() and self._offene_h5ad:
            self._lade_h5ad(self._offene_h5ad)

    def _raum_fuer_projektion(self, ganz: bool) -> None:
        """In der Projektion das ganze Fenster freimachen.

        Die Karte braucht Flaeche: bei 900 x 600 blieb neben Auswahlpanel und
        Antworttext ein Streifen uebrig, in dem der Kreis der Kohorten kaum zu
        erkennen war. Auswahl und Antwort gehoeren ausserdem zum Auftrag, nicht
        zur Karte — sie stehen im Wissensnetz wieder da, wo sie waren.

        Zurueckgeschaltet wird nichts verworfen: die Splitterstellungen werden
        gemerkt und unveraendert wiederhergestellt.
        """
        panel = self._splitter.widget(1)
        if ganz:
            self._breiten = self._splitter.sizes()
            self._hoehen = self._anzeige.sizes()
            panel.hide()
            self._output.hide()
            self._aktionen.hide()
            return
        panel.show()
        self._output.show()
        self._aktionen.show()
        if getattr(self, "_breiten", None):
            self._splitter.setSizes(self._breiten)
            self._anzeige.setSizes(self._hoehen)

    def _projektion_hinweis(self) -> str:
        name = self._projektion.dateiname()
        return f"Messdaten aus {name}" if name else "Keine Datei geladen"

    def _lade_h5ad(self, pfad: str) -> None:
        """Eine ``.h5ad`` im Worker-Thread laden (siehe ``worker.H5adWorker``)."""
        if self._h5_thread is not None:
            self.set_status("Es wird bereits eine Datei geladen — bitte warten.",
                            "warning")
            return
        self._offene_h5ad = pfad
        name = Path(pfad).name
        self._projektion.zeige_laden(name)
        self.set_status(f"Lade {name} … Das Fenster bleibt bedienbar.", "busy")
        self._h5_thread, self._h5_worker = worker.start_h5ad(pfad, self._h5ad_fertig)
        self._h5_thread.finished.connect(self._release_h5_thread)

    def _h5ad_fertig(self, modell, fehler: str) -> None:
        if modell is None:
            self._projektion.zeige_fehler(fehler)
            self.set_status(fehler, "error")
        elif modell.hat_basis:
            self._projektion.zeige_modell(modell)
            self.set_status(
                f"{modell.anzahl} Proben aus {modell.dateiname} geladen.", "success")
        else:
            # Kein 2D-Layout: kein Absturz, aber auch kein Erfolg.
            self._projektion.zeige_modell(modell)
            self.set_status(
                f"{modell.dateiname} enthaelt kein 2D-Layout — keine Karte.",
                "warning")
        self._ansicht_hinweis.setText(self._projektion_hinweis())

    def _release_h5_thread(self) -> None:
        """Wie ``_release_thread``, aber fuer den .h5ad-Thread (siehe dort)."""
        self._h5_thread = None
        self._h5_worker = None

    def _hole_kontext(self, schluessel: str) -> None:
        """Kontext einer angeklickten Probe aus dem Wissensnetz holen.

        Im Worker, damit ein Klick nicht haengt, wenn Fuseki langsam antwortet.
        Der Store kommt aus ``store_reader``; eine zweite Instanz wird nicht
        angelegt.
        """
        if not schluessel or self._kontext_thread is not None:
            return
        self._projektion.zeige_kontext(f"{schluessel} — Kontext wird geholt …")
        self._kontext_thread, self._kontext_worker = worker.start_kontext(
            schluessel, _kontext_aus_store, self._kontext_fertig
        )
        self._kontext_thread.finished.connect(self._release_kontext_thread)

    def _kontext_fertig(self, schluessel: str, kontext, fehler: str) -> None:
        self._projektion.zeige_kontext(self._kontext_text(schluessel, kontext, fehler))

    @staticmethod
    def _kontext_text(schluessel: str, kontext, fehler: str) -> str:
        """Der Kontextblock unter der Karte — beide leeren Faelle ehrlich benannt."""
        if fehler:
            return fehler
        if not kontext:
            # Die .h5ad kann aelter sein als der Storeinhalt oder aus einer
            # anderen Auswahl stammen. Das ist normal, kein Fehler.
            return (f"{schluessel}: Dieser Fall liegt nicht im Store. "
                    "Eine Vorschau mit dieser Kohorte laedt ihn nachtraeglich.")
        teile = [str(schluessel)]
        projekt = kontext.get("project_id")
        if projekt:
            teile.append(f"Projekt {projekt}")
        diagnosen = kontext.get("diagnoses") or []
        if diagnosen:
            erste = diagnosen[0]
            beschriftung = erste.get("label") or erste.get("primary_diagnosis")
            if beschriftung:
                teile.append(str(beschriftung))
        for feld in ("sex_at_birth", "race", "ethnicity", "vital_status"):
            wert = kontext.get(feld)
            if wert:
                teile.append(f"{feld}: {wert}")
        return "  ·  ".join(teile)

    def _release_kontext_thread(self) -> None:
        """Wie ``_release_thread``, aber fuer den Kontext-Thread (siehe dort)."""
        self._kontext_thread = None
        self._kontext_worker = None

    def _build_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName(theme.OBJ_PANEL)
        panel.setMinimumWidth(theme.PANEL_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        # Kohorte: aufklappende Haekchenliste mit Suchfeld. Mehrere Kohorten
        # sind der Normalfall, sobald man vergleicht — der Mediator nimmt sie in
        # DERSELBEN Ebene entgegen (``SingleSelection.cohorts`` ist eine Liste)
        # und holt je Kohorte ``size`` Proben. 32 Eintraege sind zum
        # Durchscrollen zu viele, und gesucht wird ueber das Studienkuerzel —
        # deshalb steht der Klarname vorn und das Kuerzel rechts.
        self._cohort_select = MultiSelect(
            self._cohort_entries(),
            mit_suche=True,
            platzhalter="Kuerzel suchen, z. B. BRCA …",
            leer_text="Kein Kuerzel passt",
            mit_punkt=True,
        )

        self._modality_box = QComboBox()

        # Obj und Datenquelle klappen ebenso auf wie die Kohorte, sind aber
        # Haekchenlisten: dauerhaft sichtbar haben sie das Panel gefuellt,
        # obwohl vier der fuenf Zeilen selten angefasst werden — und die
        # Attributliste war in ihren 240 Pixeln immer abgeschnitten.
        # Ein Suchfeld nur bei den Attributen; drei Datenquellen brauchen keines.
        self._attribute_select = MultiSelect(
            self._attribute_entries(),
            mit_suche=True,
            platzhalter="Attribut oder Knoten suchen, z. B. stage …",
            leer_text="Kein Attribut passt",
            max_hoehe=_ATTRIBUTE_CARD_HEIGHT,
        )
        self._source_select = MultiSelect(self._source_entries())

        self._size_spin = QSpinBox()
        self._size_spin.setRange(mc.SIZE_MIN, mc.SIZE_MAX)
        self._size_spin.setValue(20)

        # Alle fuenf Zeilen sind einzeilig. Was das an Platz freimacht, bekommt
        # die Anzeigeflaeche links ueber den Splitter — nicht ein wachsendes
        # Panel; deshalb steht unten ein Dehnfeld und keine Zeile dehnt sich.
        for label, widgets, stretch in (
            ("Krebs", (self._cohort_select,), 0),
            ("Var", (self._modality_box,), 0),
            ("Obj", (self._attribute_select,), 0),
            ("Datenquelle", (self._source_select,), 0),
            ("Proben", (self._size_spin,), 0),
        ):
            caption = QLabel(label)
            caption.setObjectName(theme.OBJ_PANEL_LABEL)
            layout.addWidget(caption)
            for i, widget in enumerate(widgets):
                # Nur das letzte Widget einer Zeile darf wachsen (bei "Krebs"
                # also die Liste, nicht das Suchfeld darueber).
                layout.addWidget(widget, stretch=stretch if i == len(widgets) - 1 else 0)
            layout.addSpacing(10)

        layout.addStretch(1)
        return panel

    # -- Panel befuellen ----------------------------------------------------
    def _fill_panel(self) -> None:
        # Keine Vorauswahl — weder Kohorte noch Attribute noch Quelle. Die
        # Oberflaeche waehlt nicht fuer den Forscher; was im Auftrag landet,
        # hat er selbst angehakt. (Die Listen 'default_attributes' und
        # 'default_sources' in config/panel.json stehen als Schalter weiter
        # bereit, sind aber leer.)
        self._fill_choice_box(self._modality_box, self._config.get("modalities") or [])

    @staticmethod
    def _fill_choice_box(box: QComboBox, entries: list[dict[str, Any]]) -> None:
        """Eintraege setzen; nicht angebundene bleiben sichtbar, aber deaktiviert.

        Ehrliche Luecke statt unsichtbarer Grenze — dasselbe Prinzip wie bei den
        MP-Lite-Slidern. Der Hinweistext aus ``panel.json`` steht im Eintrag und
        im Tooltip.
        """
        first_enabled = -1
        for entry in entries:
            enabled = bool(entry.get("enabled", True))
            note = entry.get("note")
            label = entry.get("label", entry.get("value", ""))
            if not enabled and note:
                label = f"{label}  ({note})"
            box.addItem(label, entry.get("value"))
            index = box.count() - 1
            if not enabled:
                item = box.model().item(index)
                if item is not None:
                    item.setEnabled(False)
                box.setItemData(index, note or "noch nicht angebunden",
                                Qt.ItemDataRole.ToolTipRole)
            elif first_enabled < 0:
                first_enabled = index
        if first_enabled >= 0:
            box.setCurrentIndex(first_enabled)

    def _cohort_entries(self) -> list[dict[str, str]]:
        """Die Kohorten als Eintraege fuer :class:`MultiSelect`.

        Gesendet wird die ``project_id``; angezeigt wird der Klarname aus
        ``config/panel.json`` (einmalig von GDC geholt), rechts das Kuerzel.
        Fehlt ein Name, steht dort die ``project_id`` — dann ist die Liste
        karger, aber nichts kaputt.
        """
        labels = self._config.get("cohort_labels") or {}
        entries = []
        for project_id in self._cohorts:
            code = project_id.split("-", 1)[-1] if "-" in project_id else project_id
            entries.append({
                "value": project_id,
                "label": labels.get(project_id) or project_id,
                "code": code,
                # Bewusst NUR Kuerzel und project_id, nicht der Klarname:
                # gesucht wird mit der offiziellen Studienabkuerzung (BRCA,
                # LUAD, KIRC). Der Klarname steht weiter in der Zeile, damit man
                # sieht, was sich hinter dem Kuerzel verbirgt.
                "search": f"{code} {project_id}",
            })
        return entries

    def current_cohorts(self) -> list[str]:
        """Die angehakten ``project_id`` in Panel-Reihenfolge."""
        return self._cohort_select.checked_values()

    def _source_entries(self) -> list[dict[str, Any]]:
        """Die Datenquellen als Eintraege fuer :class:`MultiSelect`.

        Nicht angebundene Quellen stehen sichtbar drin, sind aber nicht
        anhakbar und tragen den Grund als Hinweis rechts in der Zeile und als
        Tooltip — ehrliche Luecke statt unsichtbarer Grenze. ``POST /selection/*``
        kennt inzwischen ``gdc``, ``cbioportal`` und ``geo`` (Back-Mediator M9,
        siehe ``mediator/app/main.py::_fetch_selection_level``); ``ena`` bleibt
        bewusst deaktiviert (siehe ``config/panel.json``).
        """
        preselected = set(self._config.get("default_sources") or [])
        entries: list[dict[str, Any]] = []
        for entry in self._config.get("sources") or []:
            value = entry.get("value") or ""
            enabled = bool(entry.get("enabled", True))
            entries.append({
                "value": value,
                "label": entry.get("label") or value,
                # Der kurze Hinweis steht rechts in der Zeile, der ausfuehrliche
                # Grund im Tooltip - das Panel ist nur rund 360 Pixel breit.
                "code": "" if enabled else (entry.get("note") or ""),
                "enabled": enabled,
                "checked": enabled and value in preselected,
                "tooltip": entry.get("detail") or entry.get("note") or "",
                "search": value,
            })
        return entries

    def _attribute_entries(self) -> list[dict[str, Any]]:
        """Die Attribute als Eintraege fuer :class:`MultiSelect`, nach Knoten
        gruppiert.

        Die Gruppenueberschriften tragen keinen Attributnamen und landen deshalb
        nie im Auftrag. Gesucht wird ueber Attributname **und** Knoten: ``diag``
        findet die Diagnose-Gruppe, ``stage`` findet ``tumor_stage``.
        """
        preselected = set(self._config.get("default_attributes") or [])
        entries: list[dict[str, Any]] = []
        for group in self._config.get("attribute_groups") or []:
            knoten = group.get("node") or ""
            entries.append({"kind": KIND_HEADER, "label": knoten})
            for eintrag in group.get("attributes") or []:
                # Ein Eintrag ist entweder ein blosser Name oder {value, label}.
                # Die zweite Form braucht es, wenn der an den Mediator gesendete
                # Wert und der angezeigte Name auseinanderfallen — siehe
                # "_sex_at_birth_hinweis" in panel.json.
                if isinstance(eintrag, dict):
                    attribute = eintrag.get("value") or ""
                    beschriftung = eintrag.get("label") or attribute
                else:
                    attribute = beschriftung = eintrag
                if not attribute:
                    continue
                entries.append({
                    "value": attribute,
                    "label": beschriftung,
                    # Nur fuer die Netzansicht; auf den Auftrag ohne Einfluss.
                    "store_property": (eintrag.get("store_property")
                                       if isinstance(eintrag, dict) else None),
                    "checked": attribute in preselected,
                    "tooltip": f"{knoten}.{attribute}" if knoten else attribute,
                    "search": f"{attribute} {beschriftung} {knoten}",
                })
        return entries

    # -- Auswahl auslesen ---------------------------------------------------
    def checked_attributes(self) -> list[str]:
        """Die angehakten Attributnamen in Panel-Reihenfolge.

        Reihenfolge, nicht Klick-Reihenfolge: der Client reicht sie unveraendert
        an den Mediator durch (siehe ``MultiSelect.checked_values``).
        """
        return self._attribute_select.checked_values()

    def checked_sources(self) -> list[str]:
        """Die angehakten Datenquellen in Panel-Reihenfolge."""
        return self._source_select.checked_values()

    def current_payload(self) -> dict[str, Any]:
        return mc.build_selection_request(
            cohorts=self.current_cohorts(),
            modality=self._modality_box.currentData(),
            attributes=self.checked_attributes(),
            sources=self.checked_sources(),
            size=self._size_spin.value(),
        )

    # -- Netzansicht ---------------------------------------------------------
    def _attribut_namen(self) -> list[str]:
        """Die Panel-Namen der Attribute — Grundlage der Namensregel im Netz
        (siehe ``store_reader.panel_name``)."""
        return [e["value"] for e in self._attribute_entries() if e.get("value")]

    def _store_zuordnung(self) -> dict[str, str]:
        """Panel-Name -> Store-Property, soweit sie nicht mechanisch folgt.

        Nur ``primary_diagnosis`` und ``has_metastasis`` stehen dafuer in
        ``config/panel.json``; die uebrigen neun ergeben sich aus dem camelCase
        (siehe ``store_reader.store_property``).
        """
        return {e["value"]: e["store_property"]
                for e in self._attribute_entries()
                if e.get("value") and e.get("store_property")}

    def _abzug_vorher(self) -> dict[str, Any]:
        """Abzug A, **bevor** die Anfrage abgeschickt wird. Laeuft im
        Worker-Thread (siehe ``worker.SelectionWorker``)."""
        self._abzug_a = None
        self._abzug_a = sr.snapshot(sr.default_store())
        return self._abzug_a

    def _abzug_nachher(self) -> dict[str, Any] | None:
        """Abzug B, nachdem die Antwort da ist, und der Vergleich.

        Verglichen wird hier und nicht im Worker: der kennt den Store nicht.
        Ohne Abzug A gibt es keinen Vergleich — sonst saehe nach einem
        zwischenzeitlich gestarteten Fuseki alles neu aus, was laengst da war.
        """
        abzug = sr.snapshot(sr.default_store())
        self._letzter_abzug = abzug
        if self._abzug_a is None:
            return None
        return sr.diff(self._abzug_a, abzug)

    def _auswahl_geaendert(self, *_: Any) -> None:
        """Auswahl im Panel geaendert — Netz neu zeichnen, ohne neue Abfrage.

        Ohne Markierung: die Wachstumsfarben gehoeren zum letzten **Aufruf**,
        nicht zum letzten Klick im Panel.
        """
        if self._letzter_abzug is not None:
            self._netz_zeigen(self._letzter_abzug)

    def _netz_aktualisieren(self) -> None:
        """Das Netz frisch lesen — beim Start und ueber ``Ansicht > Netz
        aktualisieren`` (F5).

        Bewusst geradeaus im GUI-Thread: hier laeuft kein Mediator-Aufruf
        daneben, auf den gewartet werden muesste. Der teure Weg — Abzug vor und
        nach einem Aufruf — liegt im Worker (Deliverable 4).
        """
        store = sr.default_store()
        url = sr.store_url(store)
        if not sr.is_reachable(store):
            self._netz_zeigen(None)
            # Nicht erreichbar heisst NICHT blockiert: Vorschau und Generieren
            # sprechen mit dem Mediator, nicht mit Fuseki.
            self.set_status(
                f"Fuseki unter {url} nicht erreichbar. Laeuft `docker compose up`?",
                "error",
            )
            return
        try:
            self._letzter_abzug = sr.snapshot(store)
        except Exception as fehler:          # noqa: BLE001 - jede Stoerung gleich
            self._netz_zeigen(None)
            self.set_status(f"Netz konnte nicht gelesen werden: {fehler}", "error")
            return
        self._netz_zeigen(self._letzter_abzug)

    def _netz_zeigen(self, abzug: dict[str, Any] | None,
                     unterschied: dict[str, Any] | None = None) -> None:
        """Netzflaeche und Statusfeld rechts auf denselben Stand bringen."""
        if abzug is None:
            self._netz.zeige_nicht_erreichbar(sr.store_url(sr.default_store()))
            self._store_label.setText("Store: nicht erreichbar")
            return
        if not self.current_cohorts():
            # Ohne Auswahl hat das Netz nichts zu zeigen — und "leer" hiesse
            # hier faelschlich, im Store liege nichts.
            self._netz.zeige_hinweis(
                "Noch nichts ausgewaehlt.\n"
                "Rechts Kohorten anhaken und Attribute waehlen."
            )
            self._store_label.setText(self._store_stand(abzug))
            return
        # Das Netz zeigt die Auswahl aus dem Panel, nicht den ganzen Store —
        # der Gesamtstand steht rechts in der Statusleiste.
        kohorten = self.current_cohorts()
        self._netz.zeige_abzug(
            sr.auswahl_abzug(abzug, kohorten, self.checked_attributes(),
                             self._store_zuordnung()),
            unterschied,
            # Aufgeklappt bleibt, was aufgeklappt war. Sonst KEINE: die
            # Attribute gelten der ganzen Auswahl, und eine willkuerlich
            # aufgeklappte erste Kohorte liess sie aussehen, als gaelten sie nur
            # fuer diese.
            offen=(self._netz.offene_kohorte()
                   if self._netz.offene_kohorte() in kohorten else ""),
        )
        self._store_label.setText(self._store_stand(abzug))

    @staticmethod
    def _store_stand(abzug: dict[str, Any]) -> str:
        faelle = abzug.get("cases", 0)
        kohorten = len(abzug.get("cohorts") or {})
        return (f"Store: {faelle} {'Fall' if faelle == 1 else 'Faelle'} · "
                f"{kohorten} {'Kohorte' if kohorten == 1 else 'Kohorten'}")

    # -- Aufruf -------------------------------------------------------------
    def _start(self, mode: str) -> None:
        if not self.current_cohorts():
            self.set_status("Keine Kohorte angehakt.", "warning")
            return
        if not self.checked_sources():
            self.set_status("Keine Datenquelle angehakt.", "warning")
            self._output.setPlainText("\n".join([
                "Keine Datenquelle angehakt.",
                "",
                "Rechts unter 'Datenquelle' mindestens eine Quelle ankreuzen.",
                "Je angehakter Quelle entsteht eine eigene Ebene im Auftrag.",
            ]))
            return
        payload = self.current_payload()

        self._set_busy(True)
        was = "Vorschau" if mode == "preview" else "Generieren"
        quellen = ", ".join(lvl["source"] for lvl in payload["levels"])
        kohorten = payload["levels"][0]["cohorts"]
        self.set_status(
            f"{was} laeuft … {', '.join(kohorten)}, "
            f"{payload['size']} Proben je Kohorte, Quelle(n): {quellen}. "
            f"Das Fenster bleibt bedienbar.",
            "busy",
        )
        self._output.setPlainText(f"{was} laeuft, bitte warten …")
        self._thread, self._worker = worker.start_call(
            payload, mode, self._on_finished,
            vorher=self._abzug_vorher, nachher=self._abzug_nachher,
        )
        self._thread.finished.connect(self._release_thread)

    def _on_finished(self, result: mc.Result, mode: str, unterschied=None) -> None:
        """Ergebnis anzeigen. Gibt die Thread-Referenz **nicht** frei.

        ``worker.finished`` erreicht diesen Slot, bevor der QThread seine
        Ereignisschleife verlassen hat. Wuerde hier ``self._thread = None``
        stehen, faellt die letzte Python-Referenz auf einen noch laufenden
        QThread und Qt beendet den Prozess (0xC0000409). Das Aufraeumen
        uebernimmt :meth:`_release_thread` am ``finished``-Signal des Threads.
        """
        self._set_busy(False)
        self._render(result, mode)
        self._netz_zeigen(self._letzter_abzug, unterschied)

    def _release_thread(self) -> None:
        """Referenzen freigeben, sobald der Thread wirklich gestoppt ist."""
        self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        self._preview_button.setEnabled(not busy)
        self._generate_button.setEnabled(not busy)

    # -- Anzeige ------------------------------------------------------------
    def set_status(self, message: str, state: str = "info") -> None:
        self._status.setStyleSheet(theme.status_style(state))
        self._status.showMessage(message)

    def _render(self, result: mc.Result, mode: str) -> None:
        """Antwort des Mediators anzeigen — Fehler sichtbar, nie stille Leere."""
        if not result.ok:
            self._output.setPlainText(f"FEHLER\n\n{result.error}")
            self.set_status((result.error or "Fehler").splitlines()[0], "error")
            return

        levels = result.levels()
        if not levels:
            self._output.setPlainText(
                "Der Mediator hat keine Auswahl-Ebene zurueckgegeben.\n\n"
                + json.dumps(result.data, indent=2, ensure_ascii=False)[:4000]
            )
            self.set_status("Antwort ohne Ebenen.", "warning")
            return

        # Download-Menue nur nach 'Generieren' aktualisieren: eine Vorschau
        # liefert kein .h5ad und soll ein zuvor erzeugtes nicht aus dem Menue
        # werfen (die Datei bleibt ja abrufbar).
        if mode == "generate":
            self._update_download_menu(self._collect_downloadable(levels))

        # Eine Ebene je gewaehlter Datenquelle: alle anzeigen, nicht nur die
        # erste — eine Ebene kann scheitern, ohne die anderen zu beeintraechtigen.
        blocks: list[str] = []
        for index, level in enumerate(levels):
            if len(levels) > 1:
                quelle = (level.get("selection") or {}).get("source") or "?"
                blocks.append(f"### Ebene {index + 1} von {len(levels)} — Quelle: {quelle}")
            blocks += self._format_level(level, mode)
            blocks.append("")
        self._output.setPlainText("\n".join(blocks).rstrip())

        self.set_status(*self._summarize(levels, mode))

    @staticmethod
    def _summarize(levels: list[dict[str, Any]], mode: str) -> tuple[str, str]:
        """Eine Zeile fuer die Statusleiste plus deren Zustand.

        Mehrere Ebenen koennen unabhaengig voneinander gelingen oder scheitern
        (ADR-0003, Entscheidung 7.2) — die Zeile muss das unterscheiden, sonst
        sieht ein Teilausfall wie ein voller Erfolg aus.
        """
        was = "Vorschau" if mode == "preview" else "Generieren"
        ok = [lvl for lvl in levels if lvl.get("status") == "ok"]
        failed = [lvl for lvl in levels if lvl.get("status") != "ok"]
        ausgefallen = sorted({c for lvl in levels for c in (lvl.get("failed_cohorts") or [])})

        if not ok:
            grund = failed[0].get("error") if failed else "unbekannt"
            return f"{was} fehlgeschlagen: {grund}", "error"
        if failed:
            quellen = ", ".join((lvl.get("selection") or {}).get("source") or "?" for lvl in failed)
            return f"{was}: {len(ok)} von {len(levels)} Ebenen ok — fehlgeschlagen: {quellen}", "warning"
        if ausgefallen:
            return f"{was} fertig, aber ausgefallen: {', '.join(ausgefallen)}", "warning"
        if len(ok) > 1:
            return f"{was} fertig — {len(ok)} Ebenen", "success"
        return f"{was} fertig — recipe_key {ok[0].get('recipe_key')}", "success"

    def _format_level(self, level: dict[str, Any], mode: str) -> list[str]:
        was = "VORSCHAU" if mode == "preview" else "GENERIEREN"
        lines = [was, "=" * len(was), ""]
        lines.append(f"recipe_key       {level.get('recipe_key') or '—'}")
        lines.append(f"status           {level.get('status') or '—'}")
        if level.get("status") != "ok" and level.get("error"):
            lines.append(f"Fehlermeldung    {level['error']}")

        fields = level.get("requested_fields") or []
        lines.append(f"requested_fields ({len(fields)})")
        lines += [f"                 - {f}" for f in fields]

        count = level.get("triple_count")
        lines.append(f"triple_count     {count if count is not None else '—'}")

        failed = level.get("failed_cohorts") or []
        if failed:
            lines.append(f"failed_cohorts   {', '.join(failed)}")
            lines.append("                 (diese Kohorte(n) lieferten nichts)")

        anndata = level.get("anndata") or {}
        if anndata:
            lines += ["", "anndata", "-------"]
            lines.append(f"filename         {anndata.get('filename') or '—'}")
            lines.append(f"n_obs            {anndata.get('n_obs')}")
            lines.append(f"n_vars           {anndata.get('n_vars')}")
            columns = anndata.get("obs_columns") or []
            lines.append(f"obs_columns ({len(columns)})")
            lines += [f"                 - {c}" for c in columns]
            lines.append(f"download_url     {anndata.get('download_url') or '—'}")

        turtle = level.get("turtle") or ""
        if turtle.strip():
            turtle_lines = turtle.splitlines()
            shown = turtle_lines[:TURTLE_PREVIEW_LINES]
            lines += [
                "",
                f"turtle — Ausschnitt, erste {len(shown)} von {len(turtle_lines)} Zeilen",
                "-" * 60,
            ]
            lines += shown
            if len(turtle_lines) > len(shown):
                lines.append(f"… ({len(turtle_lines) - len(shown)} weitere Zeilen)")
        return lines
