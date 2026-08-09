# memory

Dieser Ordner ist das **projekteigene Gedächtnis** von DataBridge — unabhängig
von Werkzeugen wie Claude Code. Er hält laufenden Kontext fest, der nicht
bereits aus Code, Git-Historie oder den ADRs (`/docs/adr`) ablesbar ist:
Projektziele, aktuellen Stand, offene Fragen und kurze Historie wichtiger
Entscheidungen.

## Abgrenzung zu /docs/adr

- **`/docs/adr`** – einzelne, formal dokumentierte Architekturentscheidungen
  (eine Entscheidung pro Datei, dauerhaft, kaum noch geändert nach Annahme).
- **`/memory`** – lebendiger, fortlaufend aktualisierter Überblick über den
  Projektkontext als Ganzes; verweist bei Bedarf auf einzelne ADRs.

## Dateien

- `context.md` – aktueller Projektkontext: Ziel, Architekturüberblick,
  offene Punkte, Verweise auf relevante ADRs und Recherche-Unterlagen.

Bei wesentlichen Änderungen am Projekt (neue Entscheidung, neuer offener
Punkt, geänderter Fokus) sollte `context.md` aktualisiert werden.
