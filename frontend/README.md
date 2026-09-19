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

**Fuseki muss laufen.** Seit Aufgabe 19 liest die Netzansicht selbst aus dem Store, und
der **Mediator** schreibt das übersetzte Turtle bei jedem
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

**Alle drei Auswahlen klappen auf.** Das Panel hat fünf einzeilige Felder; ein
Klick auf eines davon öffnet eine Karte darunter. Kohorte ist **einwertig**,
`Obj` und `Datenquelle` sind **Häkchenlisten**: dort schaltet ein Klick das
Häkchen um und die Karte bleibt offen, sonst müsste man sie für jedes Attribut
neu aufklappen. Geschlossen wird über Escape, Klick daneben oder erneuten Klick
auf die Schaltfläche; die Leertaste schaltet die Zeile unter dem Cursor um.

Die Schaltfläche zeigt die Auswahl gekürzt — ab drei Werten die ersten beiden
plus `+N` (`sex_at_birth · primary_diagnosis +2`) —, den vollständigen Satz im
Tooltip.

**Ein Suchfeld gibt es nur bei Kohorte und `Obj`.** Über drei Datenquellen wäre
es Ballast. In `Obj` wird über **Attributname und Knoten** gesucht: `stage`
findet `tumor_stage`, `diag` die ganze Diagnose-Gruppe. Die Gruppenüberschriften
(`Demographic`, `Diagnosis`, `Sample`) sind nicht anwählbar und verschwinden
beim Filtern, wenn keines ihrer Attribute mehr passt.

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

## Netzansicht

Über der Anzeigefläche steht das **Wissensnetz** als gezeichnetes Netz: oben die Wurzel
`Store`, darunter je Kohorte ein Knoten, darunter — wenn man eine Kohorte anklickt — deren
Attribute. Ein Klick auf die Wurzel klappt alles zu; es ist immer höchstens eine Kohorte
aufgeklappt. Der aufgeklappte Knoten trägt einen **dickeren Rand**, keine andere Farbe:
**Auswahl zeigt der Rand, Wachstum zeigt die Farbe.** Der Klick ändert das Auswahlpanel
rechts nicht — das Netz ist eine Anzeige, keine Navigation.

**Alles darin kommt aus SPARQL-Abfragen gegen Fuseki, nichts aus der Mediator-Antwort**
(`store_reader.py`, drei Abfragen). Gelesen wird über das Paket `wissensnetz` im eigenen
Prozess, nicht über einen zusätzlichen Endpunkt im Mediator (ADR-0004, Punkt 3).
Geschrieben wird nie; der Store gehört dem Mediator.

**Auch `Vorschau` lässt das Netz wachsen.** `SelectionRequest.load` steht im Mediator auf
`True`, die Übersetzung wird bei `preview` genauso in den Store geladen wie bei `generate` —
der billige Knopf erweitert das Netz, der teure fügt nur die Matrix dazu. Die Form des
Netzes ist damit die Geschichte der Aufrufe: eine nie angefragte Kohorte ist nicht
ausgegraut, sie existiert nicht.

Nach jedem Aufruf ist markiert, was dazugekommen ist — ein Abzug vor der Anfrage, einer
danach, beide im Worker-Thread:

| Farbe | Bedeutung |
| --- | --- |
| neutral | war vorher da, gleiche Zahl |
| blau (`ACCENT`) | war vorher da, Zahl ist gestiegen — Zweitzeile mit `+N` |
| grün (`SUCCESS`) | war vorher nicht da |

Die Markierung gilt nur für den letzten Aufruf und wird **nicht gespeichert**; nach einem
Neustart zeigt das Netz den aktuellen Stand ohne Markierungen. Eine Historie darüber hinaus
wäre erfunden, weil der Store nicht weiß, welcher Fall aus welchem Aufruf kam.

Zwei leere Zustände, die Verschiedenes bedeuten und deshalb verschieden aussehen:

- **Leer** (erreichbar, null Fälle): gedämpfter Hinweis, dass jede Vorschau das Netz
  erweitert. Das ist der normale Anfang nach `docker compose down -v`, **kein** Fehler.
- **Nicht erreichbar**: die Meldung in Fehlerfarbe, zusätzlich in der Statusleiste. Sie
  blockiert nichts — `Vorschau` und `Generieren` sprechen mit dem Mediator, nicht mit
  Fuseki.

Aktualisiert wird beim Start, nach jedem Aufruf und über **`Ansicht > Netz aktualisieren`
(F5)** — nötig, weil der Store sich auch ohne diese Oberfläche ändert, etwa durch
`scripts/run_selection.py` oder `start_all.ps1 -FullLoad`. Rechts in der Statusleiste steht
dauerhaft der Stand (`Store: 20 Fälle · 1 Kohorte`).

**Namen: Store-Property oder Panel-Attribut.** Das Panel schreibt `sex_at_birth`, der Store
trägt `db:sexAtBirth`. Die Übersetzung gehört dem Mediator (`KNOWN_ATTRIBUTES`), den die
Oberfläche nicht importieren darf. Deshalb eine mechanische Regel: Titel des
Attributknotens ist der **lokale Name aus dem Store**, der Panel-Name steht nur darunter,
wenn er in camelCase genau passt. Zwei der elf bleiben dadurch ohne Panel-Namen —
`has_metastasis` liegt als `db:metastasisAtDiagnosis` im Store, `primary_diagnosis` als
`db:primaryDiagnosisLabel`. Eine halb stimmende Rückübersetzung wäre genau die Sorte stiller
Fehlzuordnung, die uns schon das tote GDC-Feld `gender` eingebrockt hat.

## Aufbau

| Datei | Zweck |
| --- | --- |
| `app.py` | Einstieg: `QApplication`, Stylesheet setzen, Fenster zeigen |
| `main_window.py` | Fenster, Panel, Signals/Slots, Formatierung der Antwort |
| `mediator_client.py` | HTTP gegen den Mediator — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `worker.py` | `QThread`-Worker für die langen Aufrufe |
| `theme.py` | Farben und Stylesheet an genau einer Stelle |
| `searchable_select.py` | aufklappende Auswahlmenüs: `SearchableSelect` (einwertig, Kohorte) und `MultiSelect` (Häkchen, `Obj`/`Datenquelle`) — gemeinsame Karte, gemeinsamer Zeilen-Delegate |
| `config/panel.json` | Modalitäten, Quellen, Attribute, Kohorten-Klarnamen |
| `netz_view.py` | das gezeichnete Netz (`QGraphicsView`, kein Browser) |
| `store_reader.py` | die drei SPARQL-Abfragen gegen Fuseki — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `tests/test_mediator_client.py` | Tests ohne Qt und ohne Netz (`requests` gemockt) |
| `tests/test_store_reader.py` | Tests der Auswertung, mit einem Doppel für `GraphStore` |

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
zeichnet das Stylesheet die Häkchen (`QListWidget::indicator`) ausdrücklich. In
der aufklappenden Karte greift selbst das nicht: dort **malt der Zeilen-Delegate
das Kästchen**, Größe und Farben stehen als `CHECK_*` in `theme.py`.

**Top-Level-Fenster füllen unter Windows 11 gar keinen Hintergrund.** Die
aufklappende Karte der Kohortenauswahl ist so ein Fenster: weder Stylesheet
noch Palette kamen dort an, sie blieb schwarz mit dunklem Text. Ränder und Text
wurden dagegen gezeichnet. `PopupCard.paintEvent` malt die Fläche deshalb
selbst — erst die ganze Fensterfläche füllen, dann den runden Rahmen darauf,
sonst bleiben an den Ecken schwarze Zwickel. Wer dort etwas ändert, prüft das
mit einer **Bildschirmaufnahme**, nicht mit `widget.grab()`: letzteres malt den
Fensterhintergrund nicht mit und zeigt die Karte fälschlich weiß.

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

Seit Aufgabe 19 liest die **Netzansicht** aus dem Store (siehe oben); der
Antworttext darunter zeigt weiterhin genau das, was der Mediator selbst
zurückgibt. Was es weiterhin nicht gibt: `cases_for_selection`, eine Tabelle aus
dem Store, die Werteebene unter den Attributen und jede Form von Schreibzugriff.
Beim Import kommt zur Netzansicht nur die Kohorten-Konstante
`wissensnetz.cohorts.COHORT_PROJECT_IDS` hinzu, damit Ladeskript, MP-Lite und
Oberfläche dieselbe Wahrheit nutzen; schlägt dieser Import fehl, greift die Liste
aus `panel.json` — die Netzansicht hat keinen solchen Rückfall.

Ebenfalls nicht: geschachtelte Auswahl-Ebenen, Zählungen oder Facetten im Panel,
Drill-down aus dem Netz in die Auswahl, die NCIt-Hierarchie als zweite Achse,
Karte oder Plot, PyInstaller-Paket. Das sind Folgeaufgaben.
