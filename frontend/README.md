# frontend — DataBridge Explorer (PySide6)

Die Auswahl-Oberfläche: eine Auswahl zusammenstellen, sie an den Mediator
schicken, dessen Antwort anzeigen. Eigenes Fenster, kein Browser-Tab
(siehe [ADR-0004](../docs/adr/0004-frontend-pyside6.md)).

Erste Fassung (Aufgabe 17), bewusst einfach.

## Voraussetzungen

```powershell
conda activate F+E
cd C:\Dev\F+E\F-E_Projekt1
conda install -c conda-forge pyside6     # NICHT per pip, siehe unten
pip install -r requirements.txt
```

> **PySide6 muss aus conda kommen, nicht aus pip.** Das PyPI-Wheel bringt kein
> ICU mit und ist gegen ein neueres ICU gebaut als das conda-Paket `icu 73` in
> der Env `F+E`. `Qt6Core.dll` findet dann die versionsbehafteten ICU-Exporte
> nicht, und der Import scheitert mit
> `DLL load failed while importing QtCore: Die angegebene Prozedur wurde nicht
> gefunden`. Das conda-Paket (6.11.0) ist gegen das vorhandene `qtbase`/`icu`
> gebaut und funktioniert. Derselbe Hinweis steht in `requirements.txt`.

**Fuseki muss laufen**, obwohl diese Oberfläche selbst nicht aus dem Store
liest: der **Mediator** schreibt das übersetzte Turtle bei jedem
`/selection/*`-Aufruf in den Default-Graph (ADR-0003, „der Store wächst mit den
Aufrufen"). Ohne Fuseki schlägt der Aufruf mediator-seitig fehl.

## Start

```powershell
.\start_all.ps1
```

Das genügt: Docker, Fuseki und Mediator kommen hoch, ein Demo-Scope wird
geladen, **danach** öffnet sich das Fenster. Es startet abgekoppelt, das
Terminal bleibt frei, und `.\stop_all.ps1` schließt es wieder mit.

Einzeln starten, wenn die Dienste schon laufen:

```powershell
python frontend\app.py
```

Ohne jede Oberfläche: `.\start_all.ps1 -NoUi`.

Die Basis-URL des Mediators kommt aus `MEDIATOR_URL`, Voreinstellung
`http://localhost:8000`.

## Bedienung

Rechts das Auswahlpanel — Kohorte, Modalität, klinische Attribute, Datenquellen,
Probenzahl. Unten links die beiden Schaltflächen:

| | |
| --- | --- |
| **Vorschau** | `POST /selection/preview` — Abruf, Übersetzung, Laden in den Store. Keine Rohdaten, keine Matrix. Billig. |
| **Generieren** | `POST /selection/generate` — dasselbe, plus Rohdaten-Download und `.h5ad`. Dauert Minuten. |

Nicht angebundene Werte (DNA-Methylierung, Mutationen, ENA, GEO) stehen sichtbar
in der Liste, sind aber deaktiviert und tragen den Grund als Hinweistext und
Tooltip. Ehrliche Lücke statt unsichtbarer Grenze — dasselbe Prinzip wie bei den
MP-Lite-Slidern.

**Die Kohorte wird gesucht, nicht gescrollt.** Ein Klick auf das Feld klappt
eine Karte mit Suchfeld auf. Gesucht wird **über die offizielle
TCGA-Studienabkürzung** — `BRCA`, `LUAD`, `KIRC` — oder über die volle
Projekt-ID (`TCGA-OV`); ein Präfix genügt, `ki` findet KICH, KIRC und KIRP.
Pfeiltasten und Enter funktionieren aus dem Suchfeld heraus, Escape schließt.

Der **Klarname in der Zeile ist Beschriftung, kein Suchbegriff**: `lung` findet
nichts, `LUAD` schon. Damit das nicht wie ein Fehler wirkt, nennt der
Platzhalter das Muster (`Kuerzel suchen, z. B. BRCA …`) und die Leermeldung
lautet „Kein Kuerzel passt". Die Klarnamen stammen einmalig von `GET /projects`
der GDC-API und stehen als `cohort_labels` in `config/panel.json` — gesendet
wird immer die `project_id`.

**Datenquellen sind mehrfach wählbar.** `SingleSelection.source` ist im Mediator
ein einzelner Wert, keine Liste — je angehakter Quelle entsteht deshalb eine
**eigene Ebene** im Auftrag. Genau dafür gibt es `levels`: parallele,
gleichrangige Auswahlen, die unabhängig voneinander gelingen oder scheitern
([ADR-0003](../docs/adr/0003-ui-gesteuerte-akquise.md), Entscheidung 7.2). Die
Anzeigefläche zeigt jede Ebene einzeln, die Statuszeile fasst zusammen.

Heute ist nur **GDC/TCGA** angehakt-bar: `POST /selection/*` kennt in
`_selection_fetch` ausschließlich `source="gdc"`. ENA und GEO haben zwar eigene
Endpunkte (`/ena/query`, `/geo/query`), sind aber nicht an die Auswahl
angebunden. Der Mechanismus steht trotzdem vollständig — sobald Pablo sie
anbindet, genügt in `config/panel.json` ein `"enabled": true`.

## Aufbau

| Datei | Zweck |
| --- | --- |
| `app.py` | Einstieg: `QApplication`, Stylesheet setzen, Fenster zeigen |
| `main_window.py` | Fenster, Panel, Signals/Slots, Formatierung der Antwort |
| `mediator_client.py` | HTTP gegen den Mediator — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `worker.py` | `QThread`-Worker für die langen Aufrufe |
| `theme.py` | Farben und Stylesheet an genau einer Stelle |
| `searchable_select.py` | aufklappende Auswahl mit Suchfeld (Kohorte) |
| `config/panel.json` | Modalitäten, Quellen, Attribute, Kohorten-Klarnamen |
| `tests/test_mediator_client.py` | Tests ohne Qt und ohne Netz (`requests` gemockt) |

```powershell
pytest frontend/tests -q
```

## Drei Festlegungen, die man kennen sollte

**Alle Netzaufrufe laufen über einen Worker-Thread.** `/selection/generate`
dauert Minuten; im GUI-Thread würde das Fenster einfrieren und abgestürzt
wirken. Während eines Aufrufs sind beide Schaltflächen ausgegraut und die
Statusleiste sagt, was läuft.

**Außerhalb von `theme.py` steht kein Farbwert im Code.** Wer das Aussehen
ändert, ändert es dort. Dazu gehören auch der Qt-Stil und die Palette: `app.py`
setzt `Fusion` und `theme.palette()`. Ohne beides zieht der native Windows-Stil
die System-Hell/Dunkel-Einstellung mit, und Aufklapplisten werden schwarz
hinterlegt — mit unserer dunklen Schriftfarbe unlesbar. Aus demselben Grund
zeichnet das Stylesheet die Häkchen (`QListWidget::indicator`) ausdrücklich.

**Das Panel führt genau die elf Attribute aus `KNOWN_ATTRIBUTES`**
(`mediator/app/semantic/mapping.py`). Die vollständige GDC-Feldliste steht in
[`../wissensnetz/GDC_TCGA_Klinische_Datenfelder.md`](../wissensnetz/GDC_TCGA_Klinische_Datenfelder.md),
aber Felder aus den Knoten Exposure, Treatment, Family History, Follow Up und
Pathology Detail dürfen hier **nicht** aufgenommen werden: `resolve_attribute()`
nimmt bei einem Namen ohne Punkt `diagnoses.<name>` an und löst sie damit falsch
auf. Der Grund steht auch als `_hinweis` in `config/panel.json`.

## Abweichung von ADR-0004, Punkt 4

ADR-0004 sieht den Oberflächen-Entwurf als Qt-Designer-`.ui`-Dateien vor. Diese
Fassung baut das Layout **im Code**: weniger bewegliche Teile für ein Fenster mit
vier Auswahlzeilen und zwei Schaltflächen. **Sobald das Panel wächst, auf `.ui`
umstellen und ADR-0004 entsprechend ergänzen.**

## Was diese Fassung ausdrücklich nicht tut

Kein Zugriff auf das Wissensnetz — kein `GraphStore`, kein
`cases_for_selection`, keine Tabelle aus dem Store, keine Graphansicht. Die
Anzeigefläche zeigt genau das, was der Mediator selbst zurückgibt. Einzige
Ausnahme beim Import ist die Kohorten-Konstante `wissensnetz.cohorts.COHORT_PROJECT_IDS`,
damit Ladeskript, MP-Lite und Oberfläche dieselbe Wahrheit nutzen; schlägt der
Import fehl, greift die Liste aus `panel.json`.

Ebenfalls nicht: geschachtelte Auswahl-Ebenen, Zählungen oder Facetten im Panel,
Karte oder Plot, PyInstaller-Paket. Das sind Folgeaufgaben.
