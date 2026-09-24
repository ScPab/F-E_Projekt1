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

**Der Start ist leer.** Kohorte, `Obj` und `Datenquelle` stehen auf `Keine Auswahl`; die
Oberfläche wählt nichts vor, der Forscher stellt seine Auswahl selbst zusammen. Ohne
Kohorte oder ohne Datenquelle sagt die Statusleiste das und schickt nichts ab. Wer wieder
vorbelegen will, trägt Werte in `default_attributes` / `default_sources` in
`config/panel.json` ein — beide stehen dort als Schalter bereit und sind leer.

| | |
| --- | --- |
| **Vorschau** | `POST /selection/preview` — Abruf, Übersetzung, Laden in den Store. Keine Rohdaten, keine Matrix. Billig. |
| **Generieren** | `POST /selection/generate` — dasselbe, plus Rohdaten-Download und `.h5ad`. Dauert Minuten. |

Nicht angebundene Werte (DNA-Methylierung, Mutationen, ENA, GEO) stehen sichtbar
in der Liste, sind aber deaktiviert und tragen den Grund als Hinweistext und
Tooltip. Ehrliche Lücke statt unsichtbarer Grenze — dasselbe Prinzip wie bei den
MP-Lite-Slidern.

**Alle drei Auswahlen klappen auf, und alle drei sind Häkchenlisten.** Das Panel
hat fünf einzeilige Felder; ein Klick auf eines davon öffnet eine Karte darunter.
Ein Klick auf eine Zeile schaltet das Häkchen um und die Karte bleibt offen,
sonst müsste man sie für jede Kohorte neu aufklappen. Geschlossen wird über
Escape, Klick daneben oder erneuten Klick auf die Schaltfläche; die Leertaste
schaltet die Zeile unter dem Cursor um.

**Mehrere Kohorten sind der Normalfall, sobald man vergleicht.** Sie landen in
**derselben Ebene** des Auftrags — `SingleSelection.cohorts` ist eine Liste —,
nicht in mehreren: mehrere Ebenen entstehen nur durch mehrere **Datenquellen**.
Der Mediator holt je Kohorte `per_cohort_size or size` Proben, `Proben` im Panel
gilt also **pro Kohorte**. Im Netz stehen die gewählten Kohorten nebeneinander, und die
**Attributreihe hängt an allen** — so wie die Attribute im Auftrag neben den
Kohorten stehen, nicht unter einer davon. Dort zählt sie die Fälle über alle
gewählten Kohorten zusammen (`130 Faelle · 5 Kohorten`); die Zahl der Werte
fehlt dann bewusst, weil distinkte Werte je Kohorte sich nicht addieren lassen.
Ein Klick auf eine Kohorte schränkt die Reihe auf deren Zahlen ein und zeigt
auch die Werte, ein Klick auf `Auswahl` geht zurück auf alle.

Die Schaltfläche zeigt die Auswahl gekürzt — ab drei Werten die ersten beiden
plus `+N` —, den vollständigen Satz im Tooltip. Wo es ein Kürzel gibt, steht es
dort statt des Klarnamens (`BRCA · KIRC +1`): drei Klarnamen passen nicht in ein
360 Pixel breites Panel.

**Ein Suchfeld gibt es nur bei Kohorte und `Obj`.** Über drei Datenquellen wäre
es Ballast. In `Obj` wird über **Attributname und Knoten** gesucht: `stage`
findet `tumor_stage`, `diag` die ganze Diagnose-Gruppe. Die Gruppenüberschriften
(`Demographic`, `Diagnosis`, `Sample`) sind nicht anwählbar und verschwinden
beim Filtern, wenn keines ihrer Attribute mehr passt.

**Die Kohorten werden gesucht, nicht gescrollt.** Ein Klick auf das Feld klappt
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
`Auswahl`, darunter die gewählte Kohorte, darunter deren angehakte Attribute.

**Gezeigt wird genau die Auswahl aus dem Panel, sonst nichts** — nicht alles, was im Store
liegt. Das Netz zieht sofort mit, wenn man rechts die Kohorte wechselt oder ein Attribut an-
oder abhakt; ein Aufruf ist dafür nicht nötig. Die **Zahlen** kommen weiterhin aus dem
Store: was noch nie abgerufen wurde, steht mit `0 Faelle · 0 Werte` da, statt zu fehlen. So
sieht man vor dem Klick, was die Auswahl im Netz bewegen wird. Der Gesamtstand des Stores
steht weiterhin rechts in der Statusleiste.

Ein Klick auf die Kohorte klappt ihre Attribute zu und wieder auf, ein Klick auf die Wurzel
klappt zu; der aufgeklappte Knoten trägt einen **dickeren Rand**, keine andere Farbe:
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

- **Leer** (erreichbar, aber nichts zur Auswahl im Store): gedämpfter Hinweis, dass jede
  Vorschau das Netz erweitert. Das ist der normale Anfang nach `docker compose down -v`,
  **kein** Fehler.
- **Nicht erreichbar**: die Meldung in Fehlerfarbe, zusätzlich in der Statusleiste. Sie
  blockiert nichts — `Vorschau` und `Generieren` sprechen mit dem Mediator, nicht mit
  Fuseki.

**Eine fertige `.h5ad` bringt ihren Auftrag zurück.** Über `Auftrag aus .h5ad …` links
über dem Netz lässt sich eine früher erzeugte Datei öffnen; die Oberfläche stellt daraus
die Auswahl wieder her und zeichnet das Netz dazu. Das ist eine **Rekonstruktion, keine
Aufzeichnung**: die Datei führt den Auftrag nicht mit (`uns` ist leer), er wird aus den
Daten abgeleitet —

| woraus | wie verlässlich |
| --- | --- |
| Kohorten aus `obs["project_id"]` | verlässlich |
| Attribute aus den belegten `obs`-Spalten | ein angefragtes Attribut, das für **jede** Probe leer blieb, ist von einem nie angefragten nicht zu unterscheiden und fehlt |
| `Proben` aus der größten Fallzahl je Kohorte | verlässlich, solange nicht nachträglich gefiltert wurde |
| Datenquelle | steht nicht in der Datei und bleibt unangetastet |

Ältere Dateien tragen noch die Spalte `gender`; sie wird auf `sex_at_birth` gezogen. Die
Statuszeile nennt nach dem Lesen, was gesetzt wurde und was nicht.

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

Für die **Gegenrichtung** — welche Property gehört zu einem angehakten Attribut, damit der
Filter sie findet — reicht Raten erst recht nicht. Neun der elf ergeben sich aus dem
camelCase; genau diese beiden stehen deshalb als `store_property` in `config/panel.json`.
Das Feld dient **nur der Netzansicht** und hat auf den Auftrag keinen Einfluss: gesendet
wird immer `value`. Führend bleibt `KNOWN_ATTRIBUTES` im Mediator — ändert sich dort ein
Name, muss er in `panel.json` nachgezogen werden.

## Projektion

Über der Anzeigefläche stehen zwei Schaltflächen, **Wissensnetz** und **Projektion**.
Umschalten stößt keinen Abruf an, lädt keine Datei und verwirft keinen Zustand.

**Die Projektion bekommt das ganze Fenster.** Auswahlpanel, Antworttext und die drei
Schaltflächen treten dabei zurück: die Karte braucht Fläche, und bei 900 × 600 blieb
daneben nur ein Streifen, in dem der Kohortenkreis kaum zu erkennen war. Auswahl und
Antwort gehören ohnehin zum Auftrag, nicht zur Karte. Zurück im `Wissensnetz` steht
alles wieder da, wo es war — auch die Splitterstellungen.

Die Projektion ist die **Morphing-Karte**: ein Scatter, dessen Punktpositionen die
softmax-gewichtete Summe mehrerer Encodings sind — `pos = Σ aᵢ · E[i]` mit
`a = softmax(10 · Regler)`, genau wie im Oviedo-Original. Rechts stehen dessen 15 Regler
in fester Reihenfolge; `genes` startet auf 0,50, alle anderen auf 0. Zieht man `cancer`
hoch, wandert die tSNE-Wolke auf die Kreispositionen der Kohorten.

Die Karte hat **X- und Y-Achse mit Werten und ein Gitter** — wie die Oviedo-Vorlage. Die
Zahlen sind nach dem Morphen keine Messgrößen; sie machen Abstände und Lage vergleichbar,
wenn man die Karte verschiebt oder zoomt. Die Punktfarbe kodiert die Kohorte (dieselbe
`nipy_spectral`-Palette wie MP-Lite, über `OVIEDO_COHORTS`); die **Legende steht rechts
neben der Karte**, eine Zeile je Kohorte, und nennt nur die im Datensatz vorkommenden. Bei
32 Kohorten rollt sie.

**Die Mathematik kommt aus MP-Lite und wird nicht nachgebaut.** `encodings.py` und
`h5ad_source.py` aus `wissensnetz/prototype/mp_lite/` sind Qt-frei und werden hier
wiederverwendet — **per Dateipfad geladen, nicht per `import`**: `prototype/` ist kein
Paket, und `import encodings` träfe Pythons stdlib-Paket `encodings` (Codecs).
`mp_lite/app.py` macht es aus demselben Grund genauso. Einzige Kopie ist
`skaliere_layout` (dort `_scale_layout`), weil `app.py` Bokeh im Modulkopf importiert und
deshalb nicht importierbar ist. **MP-Lite selbst bleibt unberührt** und startet weiter
über `start_all.ps1 -WithMpLite`; es ist der Vergleichsmaßstab gegenüber Oviedo.

Drei Wege zur `.h5ad`, in dieser Rangfolge:

1. **Die gerade erzeugte Datei.** Nach `Als .h5ad speichern` merkt sich das Fenster den
   Pfad und lädt ihn, sobald man auf `Projektion` schaltet — nicht vorher: 44 MB sollen
   nicht ungefragt von der Platte kommen.
2. **`Datei oeffnen …`** über der Karte, Startordner `wissensnetz/data`.
3. **`DATABRIDGE_H5AD`**, über `h5ad_source.resolve_h5ad_path()` — dieselbe Variable, die
   MP-Lite und `start_all.ps1 -DemoGenerate` schon nutzen.

Geladen wird im Worker-Thread (`worker.H5adWorker`), das Fenster bleibt dabei bedienbar.

**Kein erfundenes Layout.** Fehlt in `obsm` sowohl `X_tsne_genes` als auch
`X_tsne_mirna`, gibt es keine Basis-View und damit keine Karte; die Fläche nennt dann im
Klartext, was fehlt und wie man es bekommt (`compute_tsne=true`). Das ist der eine Punkt,
an dem sich die Projektion von MP-Lite **unterscheiden muss**: der Prototyp darf auf
synthetische Punkte zurückfallen, um die Bedienung ohne Daten vorzuführen, der Explorer
nicht. Mit ihm wird geforscht, und eine erfundene Punktwolke wäre dort eine Lüge. Fehlt
nur eines der beiden Layouts, ist der zugehörige Regler deaktiviert.

Ein Regler ist ebenso deaktiviert, wenn seine Variable nicht encodierbar ist. Er bleibt
**sichtbar und an seinem Platz**, mit dem Grund im Tooltip: `Spalte fehlt in obs`,
`nur ein Wert vorhanden` oder `Marker nicht in var` — ehrliche Lücke statt unsichtbarer
Grenze, dieselbe Regel wie bei ENA und GEO im Auswahlpanel.

**Beim Schweben über einen Punkt** stehen dessen Werte im Tooltip — Sample, Kohorte,
Probentyp, race, sex_at_birth, ethnicity, tumor_stage, morphology,
site_of_resection_or_biopsy, primary_diagnosis, has_metastasis, vital_status, in genau
dieser Reihenfolge wie im Original. Fehlende Werte stehen als `--` da und werden **nicht**
weggelassen: eine Lücke ist eine Aussage über die Daten, eine fehlende Zeile sähe aus wie
ein Feld, das es nicht gibt. Der Punkt unter der Maus wird dabei größer und bekommt einen
Rand in der Akzentfarbe. Ein **Fadenkreuz** folgt der Maus innerhalb der Karte und
verschwindet, sobald man sie verlässt.

**Klick auf einen Punkt** holt den Kontext dieser Probe aus dem Wissensnetz
(`enrichment.case_context`, im eigenen Prozess, kein Endpunkt im Mediator) und zeigt ihn
unter der Karte. Der Schlüssel ist `obs["submitter_id"]` gegen `db:submitterId`. Zwei
Fälle sind normal und werden als solche benannt: die Probe liegt **nicht im Store** (die
`.h5ad` kann älter sein oder aus einer anderen Auswahl stammen), oder **Fuseki läuft
nicht** — die Karte bleibt in beiden Fällen voll bedienbar, das Morphing braucht den
Store nicht.

**Ein Rechteck aufziehen** wählt die Punkte darin aus; die Anzahl steht unter der Karte,
ausgewählte Punkte bekommen einen Rand in der Akzentfarbe, die Füllung bleibt die
Kohortenfarbe. Klick daneben hebt die Auswahl auf. Lasso und Rückkanal (`write_feedback`)
sind bewusst nicht Teil dieser Fassung.

## Architekturansicht

Unter der Anzeigefläche stehen zwei Schaltflächen, **Architektur** und **Textausgabe**.
Standard ist die Architektur: eine Kette aus sechs Stationen in **zwei Zeilen**, die zeigt,
was beim Abschicken der Reihe nach passiert — oben der Weg zur Datenquelle (Auswahl → JSON,
Mediator, Wrapper und Datenquelle), unten der Weg ins Wissensnetz (GDC-JSON → RDF, graph-db
(Fuseki), Wissensnetz). Eine Kurve verbindet das Ende der oberen mit dem Anfang der unteren
Zeile, damit sichtbar bleibt, dass es derselbe Weg ist. Die Pfeile sind in Textfarbe statt
im hellen Rahmenton — darin waren sie kaum zu sehen. Die Stationen folgen
`docs/DataBridge_Architektur.drawio`; gerendert wird das Bild nicht, sondern dieselbe Kette
neu gezeichnet — eine `.drawio` ist XML für einen Editor, kein Format, aus dem man Zustände
lebendig machen kann. (Das Diagramm ist vom 31.08. und an zwei Stellen überholt: `anndata`
und der Rückkanal stehen dort als „geplant", anndata läuft inzwischen.)

Jede Station trägt ein gezeichnetes Symbol — Dokument, Dienst, Wolke, RDF-Tripel,
Zylinder, Netz — und ihre Farbe: wartet, **läuft**, ok, fehlgeschlagen, übersprungen. An
einer laufenden Station wandert ein Lichtschweif am Rand entlang: ein heller Kopf, dahinter
ein weich auslaufender Schweif, darunter breitere und blassere Lagen als Schein. Das ist bewusst
**kein Fortschrittsbalken**: die Oberfläche weiß nicht, wie weit der Mediator ist, und ein
Balken würde genau das behaupten — die umlaufende Linie sagt „hier passiert etwas", ohne zu
lügen. Der Takt läuft nur, solange wirklich etwas läuft; im Ruhezustand kostet die Ansicht
nichts. Die
Symbole sind selbst gemalt, keine Icon-Dateien: sie skalieren mit der Szene, tragen die
Farbe des Zustands und kosten keine neue Abhängigkeit. Benannt werden **Komponenten, keine
Personen** — wer welchen Teil betreut, gehört in die Projektdoku, nicht in eine Oberfläche,
die später jemand anders bedient. Die
Textausgabe bleibt einen Klick entfernt und unverändert — sie ist das Rohmaterial, wenn man
einer Station nicht glaubt.

**Was die Ansicht ehrlich zeigen kann.** Die Oberfläche hört den Mediator **nicht** mit: es
gibt keinen Fortschrittskanal, nur einen HTTP-Aufruf, der läuft, und eine Antwort, die
kommt. Während des Aufrufs steht deshalb nur fest, *dass* Mediator und Wrapper arbeiten,
nicht wie weit sie sind. Alles Genauere ist **Beleg aus der Antwort**:

| Station | woraus belegt |
| --- | --- |
| Auswahl → JSON | der Auftrag selbst, im Fenster gebaut |
| Mediator | `status`, `recipe_key` je Ebene |
| Wrapper → Datenquelle | `selection.source`, `failed_cohorts` |
| GDC-JSON → RDF | `triple_count` |
| graph-db (Fuseki) | dass Tripel da sind, plus `load=true` (ADR-0003) |
| Wissensnetz | **eigener Abzug** vor und nach dem Aufruf, nicht die Antwort |

Die Messmatrix (`.h5ad`) steht bewusst **nicht** in der Kette: sie ist ein Nebenprodukt des
Generierens und bei jeder Vorschau grau, also meistens Rauschen. Was aus ihr wurde, sagen
die Statuszeile und die Textausgabe.

Ohne Beleg bleibt eine Station grau statt grün — eine erfundene Fortschrittsanzeige wäre
genau die Sorte Behauptung, die man später glaubt. Die Zeile unter der Kette sagt das
ebenfalls.

## Aufbau

| Datei | Zweck |
| --- | --- |
| `app.py` | Einstieg: `QApplication`, Stylesheet setzen, Fenster zeigen |
| `main_window.py` | Fenster, Panel, Signals/Slots, Formatierung der Antwort |
| `mediator_client.py` | HTTP gegen den Mediator — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `worker.py` | `QThread`-Worker für die langen Aufrufe |
| `theme.py` | Farben und Stylesheet an genau einer Stelle |
| `searchable_select.py` | aufklappende Auswahlmenüs: `MultiSelect` (Häkchen; Kohorte, `Obj`, `Datenquelle`) und `SearchableSelect` (einwertig, zurzeit ungenutzt) — gemeinsame Karte, gemeinsamer Zeilen-Delegate |
| `config/panel.json` | Modalitäten, Quellen, Attribute, Kohorten-Klarnamen |
| `netz_view.py` | das gezeichnete Netz (`QGraphicsView`, kein Browser) |
| `architektur_view.py` | die Stationenkette unter der Anzeige |
| `ablauf.py` | welche Station was belegt — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `projektion_view.py` | die Morphing-Karte (`pyqtgraph`, Regler, Auswahl) |
| `morph.py` | Encodings und Positionen — **ohne Qt-Import**, nutzt die mp_lite-Module per Dateipfad |
| `store_reader.py` | die drei SPARQL-Abfragen gegen Fuseki — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `tests/test_mediator_client.py` | Tests ohne Qt und ohne Netz (`requests` gemockt) |
| `tests/test_store_reader.py` | Tests der Auswertung, mit einem Doppel für `GraphStore` |
| `tests/test_morph.py` | Tests der Morphing-Rechnung, mit einem kuenstlichen AnnData |
| `tests/test_ablauf.py` | Tests der Stationenkette: keine Station ohne Beleg |

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
