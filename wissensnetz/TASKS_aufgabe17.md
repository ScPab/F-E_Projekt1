# Aufgabe 17 (nur): Grundgerüst der Auswahl-Oberfläche (PySide6)

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.

Diese Aufgabe arbeitet bewusst **außerhalb** von `wissensnetz/`, weil die Oberfläche in den
bisher leeren Ordner `frontend/` gehört. Erlaubt sind: `frontend/**`, `requirements.txt` und
**eine** Stelle in `start_all.ps1`. **NICHT** `mediator/`, **NICHT** `wrappers/`,
**NICHT** `wissensnetz/` (auch nicht `prototype/mp_lite/`). Kleine Commits.

Grundlage: `docs/adr/0004-frontend-pyside6.md`, `docs/adr/0003-ui-gesteuerte-akquise.md`,
`recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md` Abschnitt 6.

## Ziel

Ein lauffähiges Fenster, das eine Auswahl zusammenstellt, sie an den Mediator schickt und
das Ergebnis anzeigt. Bewusst **eine** Auswahl-Ebene, ohne Schachtelung, ohne Karte. Das
Grundgerüst muss die Kette beweisen, nicht sie ausreizen.

## Deliverables

### 1) Abhängigkeit
`pyside6` in `requirements.txt` ergänzen, alphabetisch beim Rest der Oberflächen-Pakete.
`requests` dort explizit aufnehmen, falls es noch nur transitiv über `wissensnetz`/`wrappers`
kommt.

### 2) Struktur unter `frontend/`

```
frontend/
  app.py              # Einstiegspunkt: QApplication, Fenster zeigen
  main_window.py      # Fensterlogik, Signals/Slots
  mediator_client.py  # HTTP gegen den Mediator, keine Qt-Abhängigkeit
  worker.py           # QThread-Worker für lange Aufrufe
  ui/main_window.ui   # Qt-Designer-Entwurf, zur Laufzeit geladen
  config/panel.json   # vorgespeicherte Attribute und Modalitäten
  README.md           # Start, Voraussetzungen, Aufbau
```

`mediator_client.py` bleibt frei von Qt, damit es ohne Fenster testbar ist.

### 3) Fenster-Layout
Nach der Handskizze, per Splitter in zwei Spalten:

- **Links:** Anzeigefläche. Im Grundgerüst eine `QTableView` für die Fälle der Auswahl.
- **Rechts:** Auswahlpanel mit vier Zeilen:
  - Kohorte, `QListWidget` mit Mehrfachauswahl
  - Modalität, `QComboBox`
  - Attribute, `QListWidget` mit Mehrfachauswahl
  - Datenquelle, `QComboBox`
  - dazu ein `QSpinBox` für `size`
- **Unten:** `Vorschau` und `Generieren` als `QPushButton`, plus eine `QStatusBar`.

Nicht angebundene Werte (`dna_methylation`, `mutations`, andere Quellen als `gdc`) werden
angezeigt, aber deaktiviert, mit Hinweistext. Ehrliche Lücke statt unsichtbarer Grenze, wie
bei den MP-Lite-Slidern.

### 4) Panel befüllen
- **Kohorten aus `wissensnetz.cohorts`**, nicht aus einer eigenen Liste:
  `from wissensnetz.cohorts import COHORT_PROJECT_IDS`. Das ist die einzige Wahrheit für
  Ladeskript, MP-Lite und Oberfläche.
- **Attribute und Modalitäten aus `frontend/config/panel.json`**, den vorgespeicherten
  Attributen aus ADR-0003. Startwerte: `gender`, `race`, `ethnicity`, `vital_status`,
  `tumor_stage`, `morphology`, `site_of_resection_or_biopsy`, `primary_diagnosis`,
  `has_metastasis`, `sample_type`, `age_at_diagnosis`. Gegen `KNOWN_ATTRIBUTES` in
  `mediator/app/semantic/mapping.py` abgleichen (nur lesen, nicht ändern).

### 5) Auftrag bauen und senden
`mediator_client.py` baut aus dem Panel-Zustand einen `SelectionRequest` mit genau einer
Ebene und schickt ihn an `POST /selection/preview` beziehungsweise
`POST /selection/generate`. Basis-URL aus `MEDIATOR_URL`, Default `http://localhost:8000`.

Feldnamen und Grenzen **gegen `http://localhost:8000/docs` prüfen**, nicht raten. `size` ist
dort auf 1 bis 200 begrenzt.

Timeout: kurz für `preview`, mindestens 600 Sekunden für `generate`.

### 6) Threading, nicht optional
Beide Aufrufe laufen in einem `QThread`-Worker. Während eines Aufrufs sind die
Schaltflächen deaktiviert und die Statusleiste zeigt, was läuft. Das Fenster muss bedienbar
bleiben. Ein Aufruf im GUI-Thread lässt die Anwendung wie abgestürzt wirken, besonders beim
Generieren.

### 7) Ergebnis anzeigen
Nach erfolgreicher Antwort den `recipe_key` der ersten Ebene nehmen und die Tabelle über das
Paket füllen, **direkt im Prozess, nicht über HTTP**:

```python
from wissensnetz import GraphStore, cases_for_selection
rows = cases_for_selection(GraphStore(), recipe_key)
```

Spalten aus den Schlüsseln der Rückgabe, mindestens `submitter_id` und `project_id`. Nach
`generate` zusätzlich Dateiname und Größe des `.h5ad` aus der Antwort in der Statusleiste.

### 8) Fehlerfälle sichtbar machen
Jeweils Statusleiste plus, wo nötig, ein `QMessageBox`, aber **kein** Absturz und **keine**
stille Leere:

- Mediator nicht erreichbar (Verbindungsfehler, Timeout).
- Antwort mit `status="error"` je Ebene: die Meldung aus `error` zeigen.
- `failed_cohorts` nicht leer: Hinweis, welche Kohorten ausgefallen sind.
- Fuseki nicht erreichbar, also `GraphStore().is_reachable()` falsch: Tabelle bleibt leer,
  Statusleiste sagt warum.

### 9) `start_all.ps1`
An der in Aufgabe 16 markierten Stelle in Schritt 7 einen Schalter `-WithUi` ergänzen, der
`python frontend\app.py` startet. Verhalten wie `-WithMpLite`: `-NoUi` gewinnt,
Standardstart bleibt ohne Oberfläche. Alle bisherigen Parameter weiterhin akzeptieren.

### 10) Tests `frontend/tests/test_mediator_client.py`
Ohne Qt und ohne Netz, `requests` gemockt:

- Aus einem Panel-Zustand entsteht ein `SelectionRequest` mit genau einer Ebene, korrekten
  Feldnamen und den gewählten Attributen.
- `preview` und `generate` treffen die richtigen Pfade.
- Verbindungsfehler wird als Ergebnisobjekt zurückgegeben, nicht als rohe Exception.

## Verifikation

```powershell
conda activate F+E
pip install -r requirements.txt
.\start_all.ps1 -NoUi          # Dienste hoch, Demo-Scope gelaufen
python frontend\app.py
```

Erwartung:

1. Ein eigenes Fenster öffnet sich, kein Browser.
2. Kohortenliste ist gefüllt, 33 Einträge aus `COHORT_PROJECT_IDS`.
3. `Vorschau` mit einer Kohorte und zwei Attributen füllt die Tabelle, das Fenster bleibt
   während des Aufrufs bedienbar.
4. Mediator gestoppt (`docker compose stop mediator`), `Vorschau` erneut: klare Meldung in
   der Statusleiste, kein Absturz.
5. `Generieren` mit kleiner `size` erzeugt ein `.h5ad`, Name erscheint in der Statusleiste.
6. `pytest frontend/tests -q` ist grün.
7. `.\start_all.ps1 -WithUi` startet Dienste und Fenster.

## Grenze

Keine Änderung an `mediator/`, `wrappers/` oder `wissensnetz/`. Keine zweite Tabelle
Attribut zu `db:`-Property anlegen, die Oberfläche schickt nur Attributnamen. Keine
Schachtelung weiterer Ebenen, keine Karte, kein PyInstaller-Paket. Das sind Folgeaufgaben.
