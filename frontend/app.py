#!/usr/bin/env python3
"""DataBridge Explorer — Einstieg der Auswahl-Oberflaeche (PySide6).

    conda activate F+E
    python frontend\\app.py

Erste, bewusst einfache Fassung (Aufgabe 17): eine Auswahl zusammenstellen, sie
an den Mediator schicken und dessen Antwort anzeigen. **Kein** Zugriff auf den
RDF-Store, keine geschachtelten Ebenen, keine Karte — das sind Folgeaufgaben.

Technologieentscheidung und Aufbau: ``docs/adr/0004-frontend-pyside6.md``.
Der Store waechst trotzdem mit jedem Aufruf, weil der **Mediator** das Turtle
hineinschreibt (ADR-0003); Fuseki muss also laufen, auch wenn diese Oberflaeche
selbst nicht daraus liest.

English: DataBridge Explorer — entry point of the selection UI (PySide6).

    conda activate F+E
    python frontend\\app.py

First, deliberately simple version (Task 17): assemble a selection, send
it to the mediator and display its response. **No** access to the RDF
store, no nested levels, no map — those are follow-up tasks.

Technology decision and structure: ``docs/adr/0004-frontend-pyside6.md``.
The store still grows with every call because the **mediator** writes the
Turtle into it (ADR-0003); Fuseki must therefore be running, even though
this UI itself does not read from it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Direkter Start (``python frontend\app.py``) hat frontend/ ohnehin auf dem
# Pfad; der Eintrag hier macht auch ``python -m frontend.app`` und den Aufruf
# aus einem anderen Arbeitsverzeichnis heraus verlaesslich.
# EN: A direct start (``python frontend\app.py``) already has frontend/ on
# the path; this entry also makes ``python -m frontend.app`` and calls
# from a different working directory reliable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

import theme  # noqa: E402
from main_window import MainWindow  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("DataBridge Explorer")
    # Fusion statt des Windows-Stils: der native Stil zieht unter Windows 11 die
    # System-Hell/Dunkel-Einstellung mit, wodurch Aufklapplisten schwarz wurden
    # und mit unserer dunklen Schriftfarbe unlesbar waren.
    # EN: Fusion instead of the Windows style: under Windows 11 the native
    # style pulls in the system light/dark setting, which made dropdown
    # lists black and unreadable with our dark font color.
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    # Stylesheet einmal auf die QApplication: alle Farben kommen aus theme.py.
    # EN: Stylesheet applied once to the QApplication: all colors come
    # from theme.py.
    app.setStyleSheet(theme.stylesheet())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
