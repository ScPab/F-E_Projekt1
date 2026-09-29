"""QThread-Worker fuer die Mediator-Aufrufe.

**Threading ist Pflicht, nicht Feinschliff** (ADR-0004, "Zu tragen"):
``/selection/generate`` laedt Rohdaten herunter und dauert Minuten. Liefe der
Aufruf im GUI-Thread, wuerde das Fenster einfrieren und abgestuerzt wirken.

Der Worker kennt nur ``mediator_client`` und gibt dessen :class:`Result`
unveraendert per Signal in den GUI-Thread zurueck. Er entscheidet nichts und
formatiert nichts — das gehoert ins Fenster.

English: QThread worker for the mediator calls.

**Threading is mandatory, not polish** (ADR-0004, "To bear in mind"):
``/selection/generate`` downloads raw data and takes minutes. If the
call ran on the GUI thread, the window would freeze and look crashed.

The worker only knows ``mediator_client`` and passes its :class:`Result`
back into the GUI thread unchanged via signal. It decides nothing and
formats nothing — that belongs in the window.
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

    English: Executes **one** mediator call and reports the result.

    Lives in its own ``QThread``; ``run`` is triggered via its
    ``started`` signal, so the call really runs there and not on the GUI
    thread.
    """

    finished = Signal(object, str, object)  # (Result, mode, diff | None)

    def __init__(self, payload: dict[str, Any], mode: str, *,
                 vorher=None, nachher=None, progress_id: str = "") -> None:
        super().__init__()
        self._payload = payload
        self._mode = mode
        # Kennung, unter der der Mediator seinen Fortschritt fuehrt (P2). Nur
        # beim Generieren; die Vorschau ist zu kurz, um sie zu verfolgen, und
        # der Mediator nimmt den Header dort auch nicht entgegen.
        self._progress_id = progress_id
        # Zwei parameterlose Rueckrufe, die das Fenster uebergibt. Der Worker
        # ruft sie auf und weiss nicht, was sie tun — damit bleibt der Grundsatz
        # oben in Kraft: er entscheidet nichts und kennt den Store nicht.
        # ``store_reader`` wird hier ausdruecklich NICHT importiert.
        # EN: Two parameterless callbacks that the window passes in. The
        # worker calls them without knowing what they do — this keeps
        # the principle above intact: it decides nothing and knows
        # nothing about the store. ``store_reader`` is deliberately NOT
        # imported here.
        self._vorher = vorher
        self._nachher = nachher

    def run(self) -> None:
        # Abzug A **vor** dem Aufruf. Nebenlaeufig geholt koennte er bereits
        # geladene Daten enthalten und der Unterschied fiele zu klein aus; im
        # GUI-Thread wuerde das Fenster genau im Moment des Klicks einfrieren.
        # EN: Snapshot A **before** the call. If fetched concurrently it
        # could already contain loaded data and the diff would come out
        # too small; on the GUI thread the window would freeze exactly
        # at the moment of the click.
        self._rufe(self._vorher)

        if self._mode == "generate":
            result = mc.generate(self._payload, progress_id=self._progress_id)
        else:
            result = mc.preview(self._payload)

        # Was ``nachher`` zurueckgibt, reicht der Worker unbesehen weiter — was
        # dort verglichen wird, geht ihn nichts an.
        # EN: Whatever ``nachher`` returns, the worker passes on
        # unexamined — what is compared there is none of its business.
        self.finished.emit(result, self._mode, self._rufe(self._nachher))

    @staticmethod
    def _rufe(rueckruf):
        """Einen Rueckruf ausfuehren; scheitert er, ist das Ergebnis ``None``.

        Ein nicht erreichbarer Store darf einen Auftrag nie verhindern.

        English: Executes a callback; if it fails, the result is
        ``None``.

        An unreachable store must never block a request.
        """
        if rueckruf is None:
            return None
        try:
            return rueckruf()
        except Exception:      # noqa: BLE001 - jede Store-Stoerung ist hier gleich
            return None


def start_call(payload: dict[str, Any], mode: str, on_finished, *,
               vorher=None, nachher=None,
               progress_id: str = "") -> tuple[QThread, SelectionWorker]:
    """Worker in einem neuen Thread starten und beides zurueckgeben.

    Der Aufrufer muss die Rueckgabe festhalten, **bis der Thread sein
    ``finished``-Signal gesendet hat**: faellt die letzte Python-Referenz auf
    einen noch laufenden QThread, beendet Qt den Prozess hart. ``on_finished``
    laeuft noch VOR diesem Zeitpunkt — dort also nicht freigeben (siehe
    ``MainWindow._release_thread``). Thread und Worker raeumen sich danach
    selbst ab (``quit``/``deleteLater``).

    English: Starts the worker on a new thread and returns both.

    The caller must hold on to the return value **until the thread has
    sent its ``finished`` signal**: if the last Python reference to a
    still-running QThread is dropped, Qt hard-kills the process.
    ``on_finished`` still runs BEFORE that point — so do not release it
    there (see ``MainWindow._release_thread``). Thread and worker clean
    themselves up afterward (``quit``/``deleteLater``).
    """
    thread = QThread()
    worker = SelectionWorker(payload, mode, vorher=vorher, nachher=nachher,
                             progress_id=progress_id)
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

    English: Downloads **one** file from the mediator and reports the
    result.

    A separate worker instead of reusing :class:`SelectionWorker`: a
    download needs ``download_url``/``dest_path`` instead of a selection
    request, and returns no ``mode`` — neither fits its signature. The
    reason for a dedicated thread is the same as for generating: the
    file can be large, and writing it must not block the GUI thread.
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
    die Regeln zum Freigeben der Rueckgabe).

    English: Like :func:`start_call`, but for a file download (see there
    for the rules on releasing the return value).
    """
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

    English: Loads **one** ``.h5ad`` and builds the morph model from it.

    A separate worker for the same reason as :class:`DownloadWorker`:
    reading ``wissensnetz/data/pancancer.h5ad`` (44 MB) plus tSNE scaling
    takes several seconds; on the GUI thread the window would freeze
    right when the researcher has just chosen a file.

    The worker knows ``morph`` and nothing else about the UI; what
    happens with the model is decided by the window. For the rules on
    holding the thread reference, see :func:`start_call`.
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
    fuer die Regeln zum Freigeben der Rueckgabe).

    English: Like :func:`start_call`, but for loading a ``.h5ad`` (see
    there for the rules on releasing the return value).
    """
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

    English: Fetches the context of **one** sample from the knowledge
    graph.

    A separate thread so that a click on the map does not hang if Fuseki
    responds slowly or is not running at all. The worker is given a
    ready-made function and only calls it — it knows as little about the
    store as :class:`SelectionWorker`.
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
    die Regeln zum Freigeben der Rueckgabe).

    English: Like :func:`start_call`, but for a context lookup (see
    there for the rules on releasing the return value).
    """
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


class FortschrittWorker(QObject):
    """Fragt waehrend eines Auftrags wiederholt den gemeldeten Stand ab (P2).

    Eigener Thread, weil daneben der eigentliche Aufruf laeuft und der
    GUI-Thread fuer die Anzeige frei bleiben muss. Der Worker entscheidet
    nichts: er holt die Ereignisliste und reicht sie weiter — was daraus wird,
    rechnet ``ablauf.aus_ereignissen`` aus.

    Er endet von selbst, sobald der Mediator ``finished`` meldet; ausserdem
    laesst er sich ueber :meth:`stoppen` abbrechen, wenn der Aufruf vorbei ist.
    """

    stand = Signal(list, bool)      # (Ereignisse, fertig)

    def __init__(self, progress_id: str, takt_ms: int = 700) -> None:
        super().__init__()
        self._progress_id = progress_id
        self._takt = takt_ms / 1000.0
        self._laeuft = True

    def stoppen(self) -> None:
        self._laeuft = False

    def run(self) -> None:
        import time

        while self._laeuft:
            ergebnis = mc.progress(self._progress_id)
            if ergebnis.ok:
                daten = ergebnis.data or {}
                fertig = bool(daten.get("finished"))
                self.stand.emit(list(daten.get("events") or []), fertig)
                if fertig:
                    break
            # 404 heisst nur: noch nichts da. Weiterfragen, nicht aufgeben.
            time.sleep(self._takt)
        # Die Ereignisschleife des eigenen Threads beenden, sonst lebt er
        # weiter und Qt beendet den Prozess beim Schliessen hart (siehe die
        # Hinweise bei start_call).
        thread = self.thread()
        if thread is not None:
            thread.quit()


def start_fortschritt(progress_id: str, on_stand) -> tuple[QThread, FortschrittWorker]:
    """Wie :func:`start_call`, aber fuer die Fortschrittsabfrage (siehe dort fuer
    die Regeln zum Freigeben der Rueckgabe)."""
    thread = QThread()
    fortschritt = FortschrittWorker(progress_id)
    fortschritt.moveToThread(thread)

    thread.started.connect(fortschritt.run)
    fortschritt.stand.connect(on_stand)
    # **Kein** deleteLater hier: dieser Worker beendet seinen Thread selbst,
    # sobald der Mediator ``finished`` meldet. Wuerden Thread und Worker sich
    # dabei gleich mitloeschen, griffe der Aufrufer danach auf geloeschte
    # C++-Objekte ("Internal C++ object already deleted"). Er gibt seine
    # Referenzen am ``finished``-Signal frei, dann raeumt Python beide ab.
    thread.start()
    return thread, fortschritt
