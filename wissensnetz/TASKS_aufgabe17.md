# Aufgabe 17 (nur): Auswahl-Oberfläche, erste einfache Fassung (PySide6)

> Diese Datei ersetzt die frühere Fassung von Aufgabe 17. Der Zuschnitt ist bewusst kleiner:
> das Wissensnetz bleibt in dieser Fassung außen vor.

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.

Diese Aufgabe arbeitet bewusst außerhalb von `wissensnetz/`, weil die Oberfläche in den
bisher leeren Ordner `frontend/` gehört. Erlaubt sind: `frontend/**`, `requirements.txt` und
**eine** Stelle in `start_all.ps1`. **NICHT** `mediator/`, **NICHT** `wrappers/`,
**NICHT** `wissensnetz/`. Kleine Commits.

Grundlage: `docs/adr/0004-frontend-pyside6.md`, `docs/adr/0003-ui-gesteuerte-akquise.md`,
`recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md` Abschnitt 6, und die Handskizze
(links Anzeigefläche, rechts Auswahlpanel, darunter zwei Schaltflächen).

## Ziel

Ein eigenes Fenster, das eine Auswahl zusammenstellt, sie an den Mediator schickt und dessen
Antwort anzeigt. Erste Fassung, bewusst einfach.

**Ausdrücklich NICHT in dieser Fassung:**

- kein Zugriff auf das Wissensnetz, also **kein** `GraphStore`, **kein**
  `cases_for_selection`, **keine** Tabelle aus dem Store, **keine** Graphansicht
- keine Schachtelung weiterer Auswahl-Ebenen
- keine Zählungen oder Facetten im Panel
- keine Karte, kein Plot
- kein PyInstaller-Paket

Die Anzeigefläche zeigt genau das, was der Mediator selbst zurückgibt. Mehr nicht.

**Abweichung von ADR-0004 Punkt 4:** Das Layout wird in dieser Fassung **im Code** gebaut,
nicht als Qt-Designer-`.ui`. Begründung: weniger bewegliche Teile für ein Fenster mit vier
Auswahlzeilen und zwei Schaltflächen. Sobald das Panel wächst, auf `.ui` umstellen und
ADR-0004 entsprechend ergänzen. Diesen Satz in `frontend/README.md` aufnehmen.

## Deliverables

### 1) Abhängigkeiten
`pyside6` in `requirements.txt` ergänzen. `requests` dort explizit aufnehmen, falls es
bisher nur transitiv über `wissensnetz`/`wrappers` kommt.

### 2) Struktur

```
frontend/
  app.py                  # Einstieg: QApplication, Theme anwenden, Fenster zeigen
  main_window.py          # Fenster, Panel, Signals/Slots
  mediator_client.py      # HTTP gegen den Mediator, OHNE Qt-Import
  worker.py               # QThread-Worker fuer die langen Aufrufe
  theme.py                # Farben und Stylesheet an genau einer Stelle
  config/panel.json       # Modalitaeten, Quellen, Attribute nach Knoten gruppiert
  README.md
  tests/test_mediator_client.py
```

`mediator_client.py` bleibt frei von Qt, damit es ohne Fenster testbar ist.

### 3) Fensteraufbau

`QMainWindow`, Titel „DataBridge Explorer", Startgröße etwa 1200 × 760, Mindestgröße
900 × 600.

- **Kopfzeile:** ein schmaler dunkler Balken über die volle Breite, links „DataBridge" fett
  und daneben „Explorer" in gedämpfter Farbe. Feste Höhe, kein Widget darin außer den
  beiden Labels.
- **Mitte:** `QSplitter` waagerecht.
  - **Links, breit:** Anzeigefläche. Ein `QPlainTextEdit`, schreibgeschützt, Festbreitenschrift.
  - **Rechts, schmal:** Auswahlpanel, Breite etwa 360 Pixel, oben ausgerichtet.
- **Unter der linken Fläche:** die beiden Schaltflächen `Vorschau` und `Generieren`
  nebeneinander, linksbündig, wie in der Skizze. Nicht im Panel.
- **Unten:** `QStatusBar` über die volle Breite.

### 4) Auswahlpanel, bewusst leicht

Fünf Zeilen, je eine Beschriftung über dem Widget, großzügiger Abstand:

1. **Krebs** — `QComboBox`, **eine** Kohorte. Mehrfachauswahl kommt später.
2. **Var** — `QComboBox` für die Modalität.
3. **Obj** — `QListWidget` mit Häkchen je Eintrag (`ItemIsUserCheckable`), gruppiert nach
   Knoten. Die Gruppenüberschriften sind nicht anwählbare Einträge in gedämpfter Farbe.
   Vorausgewählt: `gender` und `primary_diagnosis`.
4. **Datenquelle** — `QComboBox`.
5. **Proben** — `QSpinBox`, 1 bis 200, Voreinstellung 20.

Nicht angebundene Werte (`dna_methylation`, `mutations`, alle Quellen außer `gdc`) erscheinen
in der Liste, sind aber deaktiviert und tragen den Hinweistext aus `panel.json`. Ehrliche
Lücke statt unsichtbarer Grenze, dasselbe Prinzip wie bei den MP-Lite-Slidern.

### 5) `theme.py`

Alle Farben als benannte Konstanten plus ein einziges Qt-Stylesheet, das in `app.py` auf die
`QApplication` gesetzt wird. **Außerhalb von `theme.py` steht kein Farbwert im Code.**

| Rolle | Wert |
|---|---|
| Kopfzeile Hintergrund | `#101827` |
| Kopfzeile Text | `#ffffff`, gedämpft `#8b95a6` |
| Fenstergrund | `#ffffff` |
| Panel- und Kartenfläche | `#f6f7f9` |
| Rand | `#dfe3e9` |
| Text | `#1b2230` |
| Text gedämpft | `#6b7280` |
| Akzent, Auswahl, aktiver Rand | `#2563eb` |
| Akzent Hinterlegung | `#e6eefc` |
| Erfolg | `#0d8a5f`, Hinterlegung `#dff5ec` |
| Hinweis | `#b45309`, Hinterlegung `#fdf0dc` |
| Fehler | `#b42318`, Hinterlegung `#fde8e6` |

Dazu: Eckenradius 8 Pixel, Ränder 1 Pixel, Schrift „Segoe UI" 10 pt mit Rückfall auf die
Systemschrift, Festbreitenschrift „Consolas" für die Anzeigefläche. `Vorschau` ist die
neutrale Schaltfläche, `Generieren` bekommt den Akzent als Hintergrund.

### 6) `mediator_client.py`, ohne Qt

```python
def build_selection_request(*, cohort, modality, attributes, source, size) -> dict
def preview(payload: dict, *, base_url: str, timeout: float) -> Result
def generate(payload: dict, *, base_url: str, timeout: float) -> Result
```

`Result` ist eine kleine Dataclass mit `ok`, `status_code`, `data`, `error`. Ein
Verbindungsfehler oder Timeout wird als `Result(ok=False, error=...)` zurückgegeben, **nicht**
als Exception nach oben gereicht.

Basis-URL aus `MEDIATOR_URL`, Voreinstellung `http://localhost:8000`. Zeitlimits: 60 Sekunden
für `preview`, 900 Sekunden für `generate`.

Der Auftrag hat genau **eine** Ebene. Feldnamen, Pflichtfelder und Grenzen **gegen
`http://localhost:8000/docs` prüfen**, nicht raten. Dort ist `size` auf 1 bis 200 begrenzt.

### 7) Threading, nicht optional

Beide Aufrufe laufen über einen `QThread`-Worker. Während eines Aufrufs sind beide
Schaltflächen deaktiviert und die Statusleiste sagt, was läuft. Das Ergebnis kommt per Signal
zurück in den GUI-Thread. **Kein `requests`-Aufruf im GUI-Thread**, sonst friert das Fenster
beim Generieren ein und wirkt abgestürzt.

### 8) Antwort anzeigen

Die linke Fläche wird nach jedem Aufruf neu gefüllt, aus der Antwort der ersten Ebene:

- `recipe_key`
- `status`, bei `error` die Meldung aus `error`
- `requested_fields`
- `triple_count`
- `failed_cohorts`, falls nicht leer
- bei `generate` zusätzlich aus `anndata`: `filename`, `n_obs`, `n_vars`, `obs_columns`,
  `download_url`

Darunter optional die ersten 40 Zeilen des `turtle`, klar als Ausschnitt gekennzeichnet.

Kein Import aus `wissensnetz` außer der Kohortenliste (siehe 10). Das ist Teil der Abnahme.

### 9) Fehlerfälle sichtbar machen

Jeweils Statusleiste plus Text in der Anzeigefläche, kein Absturz und keine stille Leere:

- Mediator nicht erreichbar, Verbindungsfehler oder Zeitüberschreitung
- HTTP-Status ungleich 200
- Antwort mit `status="error"`: die Meldung zeigen
- `failed_cohorts` nicht leer: benennen, welche Kohorte ausgefallen ist

### 10) `config/panel.json`, nach Knoten gruppiert

```json
{
  "sources": [
    {"value": "gdc", "label": "GDC / TCGA", "enabled": true}
  ],
  "modalities": [
    {"value": "gene_expression", "label": "Genexpression", "enabled": true},
    {"value": "dna_methylation", "label": "DNA-Methylierung", "enabled": false,
     "note": "noch nicht angebunden"},
    {"value": "mutations", "label": "Mutationen", "enabled": false,
     "note": "noch nicht angebunden"}
  ],
  "attribute_groups": [
    {"node": "Demographic", "attributes": ["gender", "race", "ethnicity", "vital_status"]},
    {"node": "Diagnosis", "attributes": ["primary_diagnosis", "age_at_diagnosis",
      "morphology", "site_of_resection_or_biopsy", "tumor_stage", "has_metastasis"]},
    {"node": "Sample", "attributes": ["sample_type"]}
  ]
}
```

Genau diese elf Attribute, weil nur sie in `KNOWN_ATTRIBUTES`
(`mediator/app/semantic/mapping.py`, nur lesen) hinterlegt sind.

**Wichtig, nicht erweitern:** Die vollständige Feldliste steht in
`wissensnetz/GDC_TCGA_Klinische_Datenfelder.md`. Felder aus den Knoten Exposure, Treatment,
Family History, Follow Up und Pathology Detail dürfen hier **nicht** aufgenommen werden:
`resolve_attribute()` im Mediator nimmt bei einem Namen ohne Punkt `diagnoses.<name>` an und
löst sie damit falsch auf. Diesen Grund als Kommentarfeld `"_hinweis"` in die JSON schreiben.

### 11) Kohortenliste

```python
from wissensnetz.cohorts import COHORT_PROJECT_IDS
```

Das ist nur eine Konstante aus einem installierten Paket, **kein** Zugriff auf den Store.
Gründe: dieselbe Wahrheit für Ladeskript, MP-Lite und Oberfläche. Schlägt der Import fehl,
auf eine Liste `"cohorts"` aus `panel.json` zurückfallen und das in der Statusleiste sagen.

### 12) `start_all.ps1`

An der in Aufgabe 16 markierten Stelle in Schritt 7 den Schalter `-WithUi` ergänzen, der
`python frontend\app.py` startet. Verhalten wie `-WithMpLite`: `-NoUi` gewinnt, der
Standardstart bleibt ohne Oberfläche. Alle bisherigen Parameter weiter akzeptieren.

### 13) Tests `frontend/tests/test_mediator_client.py`

Ohne Qt, ohne Netz, `requests` gemockt:

- `build_selection_request` erzeugt genau eine Ebene mit den richtigen Feldnamen und den
  angehakten Attributen
- `preview` und `generate` treffen die richtigen Pfade
- ein Verbindungsfehler wird als `Result(ok=False, ...)` zurückgegeben, nicht geworfen

### 14) `frontend/README.md`

Kurz: Voraussetzungen (`conda activate F+E`, `pip install -r requirements.txt`), Start
(`python frontend\app.py`), Aufbau der Dateien, die Abweichung von ADR-0004 Punkt 4, und der
Hinweis, dass Fuseki laufen muss, weil der **Mediator** beim Auswahl-Aufruf in den Store
schreibt, auch wenn die Oberfläche selbst nicht daraus liest.

## Verifikation

```powershell
conda activate F+E
pip install -r requirements.txt
.\start_all.ps1 -NoUi
python frontend\app.py
```

Erwartung:

1. Ein eigenes Fenster öffnet sich, kein Browser. Kopfzeile dunkel, Panel hell, Akzentfarbe
   auf der Schaltfläche `Generieren`.
2. Die Kohortenliste ist gefüllt, 33 Einträge.
3. `Vorschau` mit einer Kohorte und zwei Attributen füllt die Anzeigefläche mit
   `recipe_key`, `triple_count` und `requested_fields`. Das Fenster bleibt währenddessen
   bedienbar, die Schaltflächen sind ausgegraut.
4. `docker compose stop mediator`, dann `Vorschau`: klare Meldung in Statusleiste und
   Anzeigefläche, kein Absturz.
5. `Generieren` mit `size` = 5 liefert Dateiname, `n_obs` und `n_vars` in der Anzeige.
6. `grep -r "GraphStore\|cases_for_selection\|enrichment" frontend/` findet nichts.
7. `pytest frontend/tests -q` ist grün.
8. `.\start_all.ps1 -WithUi` startet Dienste und Fenster.

## Grenze

Keine Änderung an `mediator/`, `wrappers/` oder `wissensnetz/`. Keine zweite Tabelle
Attribut zu `db:`-Property anlegen, die Oberfläche schickt nur Attributnamen. Kein Zugriff
auf den RDF-Store. Keine Schachtelung, keine Karte, kein Paketbau. Das sind Folgeaufgaben.
