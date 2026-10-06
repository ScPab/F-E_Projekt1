# memory

Dieser Ordner ist das **projekteigene Gedächtnis** von DataBridge — unabhängig
von Werkzeugen wie Claude Code. Er hält laufenden Kontext fest, der nicht
bereits aus Code oder Git-Historie ablesbar ist:
Projektziele, aktuellen Stand, offene Fragen und kurze Historie wichtiger
Entscheidungen.

## Architekturentscheidungen

Die Architekturentscheidungen lagen früher als einzelne ADR-Dateien unter
`/docs/adr`. Dieser Ordner wurde entfernt; die Kurzfassung von ADR-0001 bis
ADR-0004 steht jetzt in `context.md` im Abschnitt "Architekturentscheidungen",
der volle Wortlaut bleibt über die Git-Historie erreichbar.

## Dateien

- `context.md` – aktueller Projektkontext: Ziel, Architekturüberblick,
  Architekturentscheidungen, offene Punkte und Verweise auf die
  Recherche-Unterlagen.

Bei wesentlichen Änderungen am Projekt (neue Entscheidung, neuer offener
Punkt, geänderter Fokus) sollte `context.md` aktualisiert werden.
