"""QThread-Worker fuer die Mediator-Aufrufe.

**Threading ist Pflicht, nicht Feinschliff** (ADR-0004, "Zu tragen"):
``/selection/generate`` laedt Rohdaten herunter und dauert Minuten. Liefe der
Aufruf im GUI-Thread, wuerde das Fenster einfrieren und abgestuerzt wirken.

Der Worker kennt nur ``mediator_client`` und gibt dessen :class:`Result`
unveraendert per Signal in den GUI-Thread zurueck. Er entscheidet nichts und
formatiert nichts — das gehoert ins Fenster.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

import mediator_client as mc


class SelectionWorker(QObject):
    """Fuehrt **einen** Mediator-Aufruf aus und meldet das Ergebnis.

    Lebt in einem eigenen ``QThread``; ``run`` wird ueber dessen
    ``started``-Signal angestossen, damit der Aufruf wirklich dort laeuft und
    nicht im GUI-Thread.
    """

    finished = Signal(object, str)  # (Result, "preview" | "generate")

    def __init__(self, payload: dict[str, Any], mode: str) -> None:
        super().__init__()
        self._payload = payload
        self._mode = mode

    def run(self) -> None:
        if self._mode == "generate":
            result = mc.generate(self._payload)
        else:
            result = mc.preview(self._payload)
        self.finished.emit(result, self._mode)


def start_call(payload: dict[str, Any], mode: str, on_finished) -> tuple[QThread, SelectionWorker]:
    """Worker in einem neuen Thread starten und beides zurueckgeben.

    Der Aufrufer muss die Rueckgabe festhalten, **bis der Thread sein
    ``finished``-Signal gesendet hat**: faellt die letzte Python-Referenz auf
    einen noch laufenden QThread, beendet Qt den Prozess hart. ``on_finished``
    laeuft noch VOR diesem Zeitpunkt — dort also nicht freigeben (siehe
    ``MainWindow._release_thread``). Thread und Worker raeumen sich danach
    selbst ab (``quit``/``deleteLater``).
    """
    thread = QThread()
    worker = SelectionWorker(payload, mode)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread, worker


class DownloadWorker(QObject):
    """Laedt **eine** Datei vom Mediator herunter und meldet das Ergebnis.

    Eigener Worker statt Wiederverwendung von :class:`SelectionWorker`: ein
    Download braucht ``download_url``/``dest_path`` statt eines
    Auswahl-Auftrags, und liefert kein ``mode`` zurueck — beides passt nicht
    in dessen Signatur. Grund fuer den eigenen Thread ist derselbe wie beim
    Generieren: die Datei kann gross sein, das Schreiben darf den GUI-Thread
    nicht blockieren.
    """

    finished = Signal(object)  # mediator_client.Result

    def __init__(self, download_url: str, dest_path: str) -> None:
        super().__init__()
        self._download_url = download_url
        self._dest_path = dest_path

    def run(self) -> None:
        result = mc.download(self._download_url, self._dest_path)
        self.finished.emit(result)


def start_download(download_url: str, dest_path: str, on_finished) -> tuple[QThread, DownloadWorker]:
    """Wie :func:`start_call`, aber fuer einen Datei-Download (siehe dort fuer
    die Regeln zum Freigeben der Rueckgabe)."""
    thread = QThread()
    dl_worker = DownloadWorker(download_url, dest_path)
    dl_worker.moveToThread(thread)

    thread.started.connect(dl_worker.run)
    dl_worker.finished.connect(on_finished)
    dl_worker.finished.connect(thread.quit)
    dl_worker.finished.connect(dl_worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread, dl_worker
