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

    finished = Signal(object, str, object)  # (Result, mode, diff | None)

    def __init__(self, payload: dict[str, Any], mode: str, *,
                 vorher=None, nachher=None) -> None:
        super().__init__()
        self._payload = payload
        self._mode = mode
        # Zwei parameterlose Rueckrufe, die das Fenster uebergibt. Der Worker
        # ruft sie auf und weiss nicht, was sie tun — damit bleibt der Grundsatz
        # oben in Kraft: er entscheidet nichts und kennt den Store nicht.
        # ``store_reader`` wird hier ausdruecklich NICHT importiert.
        self._vorher = vorher
        self._nachher = nachher

    def run(self) -> None:
        # Abzug A **vor** dem Aufruf. Nebenlaeufig geholt koennte er bereits
        # geladene Daten enthalten und der Unterschied fiele zu klein aus; im
        # GUI-Thread wuerde das Fenster genau im Moment des Klicks einfrieren.
        self._rufe(self._vorher)

        if self._mode == "generate":
            result = mc.generate(self._payload)
        else:
            result = mc.preview(self._payload)

        # Was ``nachher`` zurueckgibt, reicht der Worker unbesehen weiter — was
        # dort verglichen wird, geht ihn nichts an.
        self.finished.emit(result, self._mode, self._rufe(self._nachher))

    @staticmethod
    def _rufe(rueckruf):
        """Einen Rueckruf ausfuehren; scheitert er, ist das Ergebnis ``None``.

        Ein nicht erreichbarer Store darf einen Auftrag nie verhindern.
        """
        if rueckruf is None:
            return None
        try:
            return rueckruf()
        except Exception:      # noqa: BLE001 - jede Store-Stoerung ist hier gleich
            return None


def start_call(payload: dict[str, Any], mode: str, on_finished, *,
               vorher=None, nachher=None) -> tuple[QThread, SelectionWorker]:
    """Worker in einem neuen Thread starten und beides zurueckgeben.

    Der Aufrufer muss die Rueckgabe festhalten, **bis der Thread sein
    ``finished``-Signal gesendet hat**: faellt die letzte Python-Referenz auf
    einen noch laufenden QThread, beendet Qt den Prozess hart. ``on_finished``
    laeuft noch VOR diesem Zeitpunkt — dort also nicht freigeben (siehe
    ``MainWindow._release_thread``). Thread und Worker raeumen sich danach
    selbst ab (``quit``/``deleteLater``).
    """
    thread = QThread()
    worker = SelectionWorker(payload, mode, vorher=vorher, nachher=nachher)
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


class H5adWorker(QObject):
    """Laedt **eine** ``.h5ad`` und baut daraus das Morphmodell.

    Eigener Worker aus demselben Grund wie :class:`DownloadWorker`: das Lesen
    von ``wissensnetz/data/pancancer.h5ad`` (44 MB) samt tSNE-Skalierung dauert
    mehrere Sekunden, im GUI-Thread friert das Fenster genau dann ein, wenn der
    Forscher gerade eine Datei gewaehlt hat.

    Der Worker kennt ``morph`` und sonst nichts von der Oberflaeche; was mit dem
    Modell geschieht, entscheidet das Fenster. Fuer die Regeln zum Festhalten
    der Thread-Referenz siehe :func:`start_call`.
    """

    finished = Signal(object, str)  # (Morphmodell | None, Fehlertext)

    def __init__(self, pfad: str) -> None:
        super().__init__()
        self._pfad = pfad

    def run(self) -> None:
        import morph

        modell, fehler = morph.lade_modell(self._pfad)
        self.finished.emit(modell, fehler)


def start_h5ad(pfad: str, on_finished) -> tuple[QThread, H5adWorker]:
    """Wie :func:`start_call`, aber fuer das Laden einer ``.h5ad`` (siehe dort
    fuer die Regeln zum Freigeben der Rueckgabe)."""
    thread = QThread()
    h5_worker = H5adWorker(pfad)
    h5_worker.moveToThread(thread)

    thread.started.connect(h5_worker.run)
    h5_worker.finished.connect(on_finished)
    h5_worker.finished.connect(thread.quit)
    h5_worker.finished.connect(h5_worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread, h5_worker


class KontextWorker(QObject):
    """Holt den Kontext **einer** Probe aus dem Wissensnetz.

    Eigener Thread, damit ein Klick in die Karte nicht haengt, wenn Fuseki
    langsam antwortet oder gar nicht laeuft. Der Worker bekommt eine fertige
    Funktion und ruft sie nur auf — er kennt den Store so wenig wie
    :class:`SelectionWorker`.
    """

    finished = Signal(str, object, str)  # (schluessel, kontext | None, Fehlertext)

    def __init__(self, schluessel: str, holen) -> None:
        super().__init__()
        self._schluessel = schluessel
        self._holen = holen

    def run(self) -> None:
        try:
            self.finished.emit(self._schluessel, self._holen(self._schluessel), "")
        except Exception as fehler:      # noqa: BLE001 - jede Stoerung gleich
            self.finished.emit(self._schluessel, None, str(fehler))


def start_kontext(schluessel: str, holen, on_finished) -> tuple[QThread, KontextWorker]:
    """Wie :func:`start_call`, aber fuer eine Kontextabfrage (siehe dort fuer
    die Regeln zum Freigeben der Rueckgabe)."""
    thread = QThread()
    kontext_worker = KontextWorker(schluessel, holen)
    kontext_worker.moveToThread(thread)

    thread.started.connect(kontext_worker.run)
    kontext_worker.finished.connect(on_finished)
    kontext_worker.finished.connect(thread.quit)
    kontext_worker.finished.connect(kontext_worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread, kontext_worker
