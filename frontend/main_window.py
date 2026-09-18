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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "panel.json"

# Wie viele Turtle-Zeilen als Ausschnitt angehaengt werden.
TURTLE_PREVIEW_LINES = 40

# Rolle, unter der ein Listeneintrag seinen Attributnamen traegt (Gruppen-
# ueberschriften haben keinen).
_ATTR_ROLE = Qt.ItemDataRole.UserRole


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

        button_layout.addWidget(self._preview_button)
        button_layout.addWidget(self._generate_button)
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

        self._cohort_box = QComboBox()
        self._modality_box = QComboBox()
        self._attribute_list = QListWidget()
        self._attribute_list.setMinimumHeight(260)
        self._source_box = QComboBox()
        self._size_spin = QSpinBox()
        self._size_spin.setRange(mc.SIZE_MIN, mc.SIZE_MAX)
        self._size_spin.setValue(20)

        for label, widget, stretch in (
            ("Krebs", self._cohort_box, 0),
            ("Var", self._modality_box, 0),
            ("Obj", self._attribute_list, 1),
            ("Datenquelle", self._source_box, 0),
            ("Proben", self._size_spin, 0),
        ):
            caption = QLabel(label)
            caption.setObjectName(theme.OBJ_PANEL_LABEL)
            layout.addWidget(caption)
            layout.addWidget(widget, stretch=stretch)
            layout.addSpacing(10)

        layout.addStretch(0)
        return panel

    # -- Panel befuellen ----------------------------------------------------
    def _fill_panel(self) -> None:
        self._cohort_box.addItems(self._cohorts)
        default_cohort = self._cohort_box.findText("TCGA-BRCA")
        if default_cohort >= 0:
            self._cohort_box.setCurrentIndex(default_cohort)

        self._fill_choice_box(self._modality_box, self._config.get("modalities") or [])
        self._fill_choice_box(self._source_box, self._config.get("sources") or [])
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

            for attribute in group.get("attributes") or []:
                item = QListWidgetItem(f"    {attribute}")
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

    def current_payload(self) -> dict[str, Any]:
        return mc.build_selection_request(
            cohort=self._cohort_box.currentText(),
            modality=self._modality_box.currentData(),
            attributes=self.checked_attributes(),
            source=self._source_box.currentData(),
            size=self._size_spin.value(),
        )

    # -- Aufruf -------------------------------------------------------------
    def _start(self, mode: str) -> None:
        if not self._cohort_box.currentText():
            self.set_status("Keine Kohorte gewaehlt.", "warning")
            return
        payload = self.current_payload()

        self._set_busy(True)
        was = "Vorschau" if mode == "preview" else "Generieren"
        self.set_status(
            f"{was} laeuft … {payload['levels'][0]['cohorts'][0]}, "
            f"{payload['size']} Proben. Das Fenster bleibt bedienbar.",
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

        level = result.first_level()
        if not level:
            self._output.setPlainText(
                "Der Mediator hat keine Auswahl-Ebene zurueckgegeben.\n\n"
                + json.dumps(result.data, indent=2, ensure_ascii=False)[:4000]
            )
            self.set_status("Antwort ohne Ebenen.", "warning")
            return

        lines = self._format_level(level, mode)
        self._output.setPlainText("\n".join(lines))

        status = level.get("status")
        failed = level.get("failed_cohorts") or []
        if status != "ok":
            self.set_status(f"Ebene fehlgeschlagen: {level.get('error') or 'unbekannt'}", "error")
        elif failed:
            self.set_status(f"Fertig, aber ausgefallen: {', '.join(failed)}", "warning")
        else:
            was = "Vorschau" if mode == "preview" else "Generieren"
            self.set_status(f"{was} fertig — recipe_key {level.get('recipe_key')}", "success")

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
