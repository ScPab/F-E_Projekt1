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
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import mediator_client as mc
import theme
import worker
from searchable_select import SearchableSelect

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "panel.json"

# Wie viele Turtle-Zeilen als Ausschnitt angehaengt werden.
TURTLE_PREVIEW_LINES = 40

# Rolle, unter der ein Listeneintrag seinen Attributnamen traegt (Gruppen-
# ueberschriften haben keinen).
_ATTR_ROLE = Qt.ItemDataRole.UserRole
# Rolle fuer den Quellen-Wert eines Listeneintrags (gdc, ena, geo).
_SOURCE_ROLE = Qt.ItemDataRole.UserRole



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
        layout.addWidget(self._output, stretch=1)

        buttons = QWidget()
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

    def _build_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName(theme.OBJ_PANEL)
        panel.setMinimumWidth(theme.PANEL_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        # Kohorte: aufklappende Auswahl mit Suchfeld. 32 Eintraege sind zum
        # Durchscrollen zu viele, und gesucht wird nach Krebsart, nicht nach
        # Projektkuerzel — deshalb steht der Klarname vorn und das Kuerzel rechts.
        # Eine dauerhaft sichtbare Liste hat das schmale Panel gesprengt.
        self._cohort_select = SearchableSelect(self._cohort_entries())

        self._modality_box = QComboBox()
        self._attribute_list = QListWidget()
        self._attribute_list.setMinimumHeight(240)
        self._attribute_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Datenquellen sind mehrfach waehlbar: je Haekchen eine eigene Ebene.
        self._source_list = QListWidget()
        self._source_list.setMaximumHeight(110)
        # Lange Hinweise sollen nicht waagerecht scrollen, sondern abschneiden;
        # der vollstaendige Text steht im Tooltip.
        self._source_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._source_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._size_spin = QSpinBox()
        self._size_spin.setRange(mc.SIZE_MIN, mc.SIZE_MAX)
        self._size_spin.setValue(20)

        for label, widgets, stretch in (
            ("Krebs", (self._cohort_select,), 0),
            ("Var", (self._modality_box,), 0),
            ("Obj", (self._attribute_list,), 3),
            ("Datenquelle", (self._source_list,), 0),
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

        layout.addStretch(0)
        return panel

    # -- Panel befuellen ----------------------------------------------------
    def _fill_panel(self) -> None:
        self._cohort_select.set_value("TCGA-BRCA")

        self._fill_choice_box(self._modality_box, self._config.get("modalities") or [])
        self._fill_sources()
        self._fill_attributes()

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
        """Die Kohorten als Eintraege fuer :class:`SearchableSelect`.

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
            })
        return entries

    def current_cohort(self) -> str:
        """Die gewaehlte ``project_id``, oder '' wenn nichts ausgewaehlt ist."""
        return self._cohort_select.current_value()

    def _fill_sources(self) -> None:
        """Datenquellen als Haekchen-Liste (Mehrfachauswahl).

        Nicht angebundene Quellen stehen sichtbar drin, sind aber nicht
        anhakbar und tragen den Grund als Text und Tooltip — ehrliche Luecke
        statt unsichtbarer Grenze. ``POST /selection/*`` kennt heute nur
        ``gdc``; ENA und GEO haben eigene Endpunkte, sind aber nicht an die
        Auswahl angebunden (siehe ``config/panel.json``).
        """
        preselected = set(self._config.get("default_sources") or [])
        for entry in self._config.get("sources") or []:
            value = entry.get("value")
            enabled = bool(entry.get("enabled", True))
            note = entry.get("note")
            label = entry.get("label", value or "")
            if not enabled and note:
                label = f"{label}  ({note})"

            item = QListWidgetItem(label)
            item.setData(_SOURCE_ROLE, value)
            if enabled:
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if value in preselected
                    else Qt.CheckState.Unchecked
                )
            else:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setCheckState(Qt.CheckState.Unchecked)
            # Der ausfuehrliche Grund gehoert in den Tooltip, nicht in die
            # Beschriftung - das Panel ist nur rund 360 Pixel breit.
            item.setToolTip(entry.get("detail") or note or "")
            self._source_list.addItem(item)

    def _fill_attributes(self) -> None:
        """Attribute nach Knoten gruppiert, mit Haekchen je Eintrag.

        Die Gruppenueberschriften sind nicht anwaehlbare Eintraege in
        gedaempfter Farbe — sie tragen keinen Attributnamen und landen deshalb
        nie im Auftrag.
        """
        from PySide6.QtGui import QBrush, QColor, QFont

        muted = QBrush(QColor(theme.TEXT_MUTED))
        preselected = set(self._config.get("default_attributes") or [])

        for group in self._config.get("attribute_groups") or []:
            header = QListWidgetItem(group.get("node", ""))
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(muted)
            font = QFont()
            font.setBold(True)
            header.setFont(font)
            self._attribute_list.addItem(header)

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
                item = QListWidgetItem(f"    {beschriftung}")
                item.setData(_ATTR_ROLE, attribute)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if attribute in preselected
                    else Qt.CheckState.Unchecked
                )
                self._attribute_list.addItem(item)

    # -- Auswahl auslesen ---------------------------------------------------
    def checked_attributes(self) -> list[str]:
        """Die angehakten Attributnamen in Panel-Reihenfolge."""
        result = []
        for row in range(self._attribute_list.count()):
            item = self._attribute_list.item(row)
            name = item.data(_ATTR_ROLE)
            if name and item.checkState() == Qt.CheckState.Checked:
                result.append(name)
        return result

    def checked_sources(self) -> list[str]:
        """Die angehakten Datenquellen in Panel-Reihenfolge."""
        result = []
        for row in range(self._source_list.count()):
            item = self._source_list.item(row)
            value = item.data(_SOURCE_ROLE)
            if value and item.checkState() == Qt.CheckState.Checked:
                result.append(value)
        return result

    def current_payload(self) -> dict[str, Any]:
        return mc.build_selection_request(
            cohort=self.current_cohort(),
            modality=self._modality_box.currentData(),
            attributes=self.checked_attributes(),
            sources=self.checked_sources(),
            size=self._size_spin.value(),
        )

    # -- Aufruf -------------------------------------------------------------
    def _start(self, mode: str) -> None:
        if not self.current_cohort():
            self.set_status("Keine Kohorte gewaehlt.", "warning")
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
        self.set_status(
            f"{was} laeuft … {payload['levels'][0]['cohorts'][0]}, "
            f"{payload['size']} Proben, Quelle(n): {quellen}. "
            f"Das Fenster bleibt bedienbar.",
            "busy",
        )
        self._output.setPlainText(f"{was} laeuft, bitte warten …")
        self._thread, self._worker = worker.start_call(payload, mode, self._on_finished)
        self._thread.finished.connect(self._release_thread)

    def _on_finished(self, result: mc.Result, mode: str) -> None:
        """Ergebnis anzeigen. Gibt die Thread-Referenz **nicht** frei.

        ``worker.finished`` erreicht diesen Slot, bevor der QThread seine
        Ereignisschleife verlassen hat. Wuerde hier ``self._thread = None``
        stehen, faellt die letzte Python-Referenz auf einen noch laufenden
        QThread und Qt beendet den Prozess (0xC0000409). Das Aufraeumen
        uebernimmt :meth:`_release_thread` am ``finished``-Signal des Threads.
        """
        self._set_busy(False)
        self._render(result, mode)

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
