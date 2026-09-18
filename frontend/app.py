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
"""

from __future__ import annotations

import sys
from pathlib import Path

# Direkter Start (``python frontend\app.py``) hat frontend/ ohnehin auf dem
# Pfad; der Eintrag hier macht auch ``python -m frontend.app`` und den Aufruf
# aus einem anderen Arbeitsverzeichnis heraus verlaesslich.
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
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    # Stylesheet einmal auf die QApplication: alle Farben kommen aus theme.py.
    app.setStyleSheet(theme.stylesheet())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
