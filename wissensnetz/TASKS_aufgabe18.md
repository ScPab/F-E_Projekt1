# Aufgabe 18 (nur): Obj und Datenquelle als aufklappende Menüs

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.

Erlaubt ist nur `frontend/**`. **NICHT** `mediator/`, **NICHT** `wrappers/`, **NICHT**
`wissensnetz/`. Kleine Commits.

Grundlage: `docs/adr/0004-frontend-pyside6.md`, die Kohortenauswahl aus Aufgabe 17
(`frontend/searchable_select.py`) und die Vorlage, an der sie gebaut wurde: eine Karte, die
unter einer Schaltfläche aufklappt, oben ein Suchfeld, darunter abgerundete Zeilen.

## Befund

Die Kohorte klappt seit Aufgabe 17 auf und braucht im Panel nur noch eine Zeile. `Obj` und
`Datenquelle` sind dagegen weiterhin dauerhaft sichtbare Listen im Panel
(`frontend/main_window.py`, `_attribute_list` mit `setMinimumHeight(240)` und `_source_list`
mit `setMaximumHeight(110)`). Folgen, am laufenden Fenster beobachtet:

- Die Attributliste ist immer abgeschnitten. Von elf Attributen sind acht zu sehen, die
  letzte Zeile wird mitten durchgeschnitten, und man muss in einem 240 Pixel hohen Kasten
  scrollen, um `sample_type` zu finden.
- Das Panel ist dadurch voll, obwohl vier der fünf Zeilen selten angefasst werden. Die
  Anzeigefläche links bekommt weniger Platz als der Auswahlkasten rechts.
- Die drei Datenquellen brauchen dauerhaft 110 Pixel, obwohl zwei davon deaktiviert sind.

## Ziel

`Obj` und `Datenquelle` verhalten sich wie die Kohorte: eine Schaltfläche zeigt die aktuelle
Auswahl, ein Klick klappt die Karte auf. Das Panel schrumpft auf fünf einzeilige Felder.

**Der Unterschied zur Kohorte ist die Mehrfachauswahl.** Beide Listen sind Häkchenlisten:
`Obj` wählt mehrere Attribute, `Datenquelle` mehrere Quellen. Daraus folgt alles Weitere in
dieser Aufgabe — die Karte darf beim Anhaken **nicht** zugehen, und die Schaltfläche muss
mehrere Werte zusammenfassen.

**Ausdrücklich NICHT in dieser Fassung:**

- keine Änderung an dem, was an den Mediator geht. `current_payload()` muss vorher und
  nachher **denselben** Auftrag erzeugen; das ist Teil der Abnahme.
- keine neuen Attribute und keine neuen Quellen (die elf aus `KNOWN_ATTRIBUTES` und
  gdc/ena/geo bleiben, siehe `config/panel.json`)
- keine Mehrfachauswahl bei der **Kohorte** — die bleibt einwertig
- keine Facetten, keine Zählungen, kein Umbau der Anzeigefläche

## Deliverables

### 1) Mehrfachauswahl-Widget in `frontend/searchable_select.py`

Kein zweites Popup-Gerüst danebenstellen. `PopupCard` und `RowDelegate` sind die Teile, die
in Aufgabe 17 teuer erarbeitet wurden (siehe deren Docstrings) — die werden geteilt.

Vorschlag: eine Klasse `MultiSelect` neben `SearchableSelect`, die sich Karte, Suchfeld,
Höhenanpassung und Delegate teilt. Wenn dabei mehr als die Hälfte von `SearchableSelect`
kopiert würde, stattdessen die gemeinsame Mechanik in eine Basisklasse ziehen und beide
davon ableiten. Welcher Weg — entscheide beim Schreiben, aber **nicht zwei Popups pflegen**.

Verhalten:

- Klick auf eine Zeile schaltet deren Häkchen um. **Die Karte bleibt offen**, sonst müsste
  man sie für jedes Attribut neu aufklappen.
- Geschlossen wird über Escape, Klick daneben oder erneuten Klick auf die Schaltfläche.
- Leertaste schaltet die Zeile unter dem Cursor um, Pfeiltasten bewegen ihn — wie bei der
  Kohorte, damit man die Maus nicht braucht.
- Signal `selection_changed(list[str])`, damit die Schaltflächenbeschriftung ohne Umweg
  nachgezogen wird.
- `checked_values() -> list[str]` in **Panel-Reihenfolge**, nicht in Klick-Reihenfolge. Die
  bisherigen `checked_attributes()`/`checked_sources()` liefern das so, und der Client reicht
  die Reihenfolge unveraendert durch (`test_build_request_takes_the_checked_attributes_in_order`
  in `frontend/tests/test_mediator_client.py`). Eine Klick-Reihenfolge wuerde also unbemerkt
  im Auftrag landen.

### 2) Häkchen zeichnet der Delegate mit

`RowDelegate` malt heute Punkt, Name und Kürzel. Für die Mehrfachauswahl kommt links ein
Kästchen dazu. **Nicht** über `QListWidget::indicator` im Stylesheet lösen: in der
aufklappenden Karte greifen Stylesheet-Hintergründe nicht (siehe `PopupCard`), das Kästchen
bliebe unsichtbar oder schwarz. Es wird gezeichnet wie alles andere in der Zeile auch.

Zustände: leer, angehakt (Akzentfarbe), deaktiviert (gedämpft). Alle Farben aus `theme.py`,
dort gehören auch Kästchengröße und Abstand hin — im Delegate steht kein Farbwert.

### 3) Gruppenüberschriften in `Obj`

Die Attribute sind nach Knoten gruppiert (`Demographic`, `Diagnosis`, `Sample`, siehe
`attribute_groups` in `config/panel.json`). Die Überschriften bleiben:

- nicht anwählbar, kein Häkchen, gedämpfte Farbe, fett
- **beim Filtern verschwindet eine Überschrift, wenn keines ihrer Attribute mehr passt.**
  Sonst steht „Sample“ allein über einer leeren Fläche und sieht nach einem Fehler aus.
- die Höhenanpassung der Karte (`_passe_hoehe_an`) zählt Überschriften mit, sonst ist die
  Karte zu klein und scrollt, obwohl alles hineinpassen würde.

### 4) Suchfeld nur, wo es sich lohnt

`Obj` bekommt eines: elf Attribute mit langen Namen wie
`site_of_resection_or_biopsy`. Gesucht wird über den **Attributnamen und den Knoten** —
`diag` findet die Diagnose-Gruppe, `stage` findet `tumor_stage`.

`Datenquelle` bekommt **keines**: drei Einträge, davon zwei deaktiviert. Ein Suchfeld über
drei Zeilen ist Ballast. Das Widget muss das Suchfeld also abschaltbar haben.

### 5) Beschriftung der Schaltflächen

Sie muss die Auswahl zeigen, ohne umzubrechen — das Panel ist rund 360 Pixel breit:

- nichts gewählt: `Keine Auswahl` in gedämpfter Farbe
- ein bis zwei Werte: die Namen, mit `·` getrennt
- ab drei: die ersten beiden plus `+N`, zum Beispiel `sex_at_birth · primary_diagnosis +2`
- der vollständige Satz gehört in den Tooltip der Schaltfläche

### 6) Deaktivierte Einträge bleiben sichtbar

ENA und GEO stehen weiterhin in der Liste, sind nicht anhakbar und tragen ihren Grund als
Hinweistext in der Zeile und als Tooltip (`note`/`detail` in `config/panel.json`). Ehrliche
Lücke statt unsichtbarer Grenze — dasselbe Prinzip wie bisher. Dass sie nicht anhakbar sind,
muss man **sehen**: gedämpftes Kästchen, gedämpfter Text, kein Schwebe-Zustand.

### 7) Panel aufräumen

Nach dem Umbau sind alle fünf Zeilen einzeilig. Was das an Platz freimacht, bekommt die
**Anzeigefläche links** über den Splitter — nicht ein wachsendes Panel. Prüfen, dass das
Panel bei 900 × 600 (der Mindestgröße des Fensters) ohne Überlappung sitzt; genau daran ist
die erste Fassung der Kohortenliste gescheitert.

### 8) `frontend/README.md`

Abschnitt „Bedienung“ nachziehen: alle drei Auswahlen klappen auf, Mehrfachauswahl bei `Obj`
und `Datenquelle`, Suchfeld nur bei Kohorte und `Obj`. Kurz halten.

## Verifikation

```powershell
.\start_all.ps1 -NoUi
python frontend\app.py
```

1. Das Panel hat fünf einzeilige Felder. Nichts ist abgeschnitten, nichts überlappt — auch
   nicht, wenn man das Fenster auf 900 × 600 zieht.
2. `Obj` klappt auf, zeigt die drei Gruppenüberschriften, und **mehrere Attribute lassen
   sich nacheinander anhaken, ohne dass die Karte zugeht**.
3. Suche `stage` → nur `tumor_stage`, und nur die Überschrift `Diagnosis` steht darüber.
   Suche `zzz` → Leermeldung, keine verwaiste Überschrift.
4. `Datenquelle` klappt auf, hat **kein** Suchfeld. ENA und GEO sind sichtbar, nicht
   anhakbar, mit Tooltip.
5. Die Schaltflächen zeigen die Auswahl gekürzt, der Tooltip vollständig.
6. **Der Auftrag ist unverändert.** Dieselbe Auswahl wie vorher ergibt denselben
   `current_payload()` — Attributnamen, Reihenfolge, Quellen. Am besten vorher einmal
   abschreiben und nachher vergleichen.
7. `pytest frontend/tests -q` ist grün.
8. **Mit einer Bildschirmaufnahme prüfen, nicht mit `widget.grab()`.** Letzteres malt den
   Fensterhintergrund nicht mit und zeigt aufklappende Karten fälschlich weiß — genau daran
   ist in Aufgabe 17 ein schwarzes Popup durchgerutscht (siehe `frontend/README.md`,
   Abschnitt zu den Top-Level-Fenstern).

## Grenze

Nur `frontend/`. Keine Änderung an `mediator/`, `wrappers/` oder `wissensnetz/`. Der Auftrag
an den Mediator bleibt Zeichen für Zeichen derselbe. Die Kohortenauswahl bleibt einwertig
und ihre Suche bleibt auf das offizielle Studienkürzel beschränkt.

## Offener Punkt, nicht Teil dieser Aufgabe

Der farbige Punkt links in den Kohortenzeilen ist **rein optisch** und kodiert nichts; er ist
nicht die MP-Lite-Palette (siehe `theme.dot_color`). Ob er dieselbe Bedeutung tragen soll wie
die Farben dort — und die Palette dann aus `wissensnetz/prototype/mp_lite/` kommen muss statt
neu erfunden zu werden —, ist eine eigene Entscheidung. In `Obj` und `Datenquelle` hat ein
solcher Punkt ohnehin keine Bedeutung und sollte dort weggelassen werden.
