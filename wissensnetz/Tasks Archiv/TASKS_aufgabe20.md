# Aufgabe 20 (nur): Morphing-Projektion als zweite Ansicht im Fenster

## Rahmen

Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.

Erlaubt sind `frontend/**` und **eine** Zeile in `requirements.txt` (Deliverable 1).
**NICHT** `mediator/`, **NICHT** `wrappers/`, **NICHT** `wissensnetz/` (auch nicht
`wissensnetz/prototype/mp_lite/`). Kleine Commits.

Grundlage: `docs/adr/0004-frontend-pyside6.md` ("Die Darstellung der Karte muss später
eingebettet werden, über matplotlib oder pyqtgraph"), `wissensnetz/prototype/mp_lite/app.py`
als inhaltliche Vorlage, und die Oviedo-Referenz
`morphing-projections-demo-and-dataset-preparation-master/`.

Die Aufgabe hat eine natürliche Schnittstelle: **Teil A** (Deliverable 1 bis 8) ergibt eine
benutzbare Karte, **Teil B** (Deliverable 9 bis 11) hängt Kontext und Auswahl daran. Wird
der Lauf lang, ist nach Teil A ein sinnvoller Halt. Teil A ohne Teil B ist vollständig
und nicht kaputt.

## Was unverändert bleibt

Die Oberfläche ist eingespielt und soll es bleiben. Diese Aufgabe **fügt eine zweite
Ansicht ein**, sie baut nichts um. Nicht angefasst wird:

- `_build_panel()` und das gesamte Auswahlpanel rechts: fünf Felder, `MultiSelect`,
  `SearchableSelect`, `config/panel.json`, `theme.PANEL_WIDTH`. Die Slider der Projektion
  kommen **nicht** in dieses Panel.
- `_build_header()`, die drei Schaltflächen, `_set_busy()`.
- `current_payload()`, `mediator_client.py`, der Auftrag an den Mediator.
- `store_reader.py`, `_render()`, `self._output` und die Statusleiste `set_status()`.
- `searchable_select.py`.
- `NetzView` und die Netzzeichnung selbst.
- `wissensnetz/prototype/mp_lite/` bleibt voll funktionsfähig und startet weiter über
  `start_all.ps1 -WithMpLite`. Es ist der Vergleichsmaßstab gegenüber Oviedo
  (ADR-0004 Punkt 6), nicht die Vorlage zum Ausschlachten.
- In `theme.py` und `worker.py` wird **ergänzt**, nichts Bestehendes geändert.
  `SelectionWorker` und `DownloadWorker` bleiben, wie sie sind.

Erlaubte Berührungspunkte in vorhandenen Dateien, sonst keine:

| Datei | Änderung |
|---|---|
| `main_window.py` | Titelzeile mit Umschalter, `QStackedWidget` statt des direkten `NetzPanel` im senkrechten Splitter, Weitergabe der geladenen `.h5ad` |
| `netz_view.py` | `NetzPanel` baut seine Titelzeile nicht mehr selbst (sie wandert ins Fenster, Deliverable 2) |
| `worker.py` | zwei neue Worker-Klassen nach dem Muster von `DownloadWorker` |
| `theme.py` | neue Tokens: Umschalter, Kohortenpalette, Slider |
| `requirements.txt` | eine Zeile `pyqtgraph` |

## Ziel

Über der Anzeigefläche stehen zwei zusammenhängende Schaltflächen, `Wissensnetz` und
`Projektion`. Die Projektion zeigt die Morphing-Karte aus einer `.h5ad`, die der Forscher
lädt: ein Scatter, dessen Punktpositionen die softmax-gewichtete Summe mehrerer Encodings
sind, gesteuert über Oviedos Slider. Alles läuft **im Fenster**, ohne Browser und ohne
Serverprozess.

## Befunde, auf denen der Zuschnitt aufsetzt

Geprüft, nicht vermutet:

1. **Die Mathematik ist schon geschrieben und Qt-frei.**
   `wissensnetz/prototype/mp_lite/encodings.py` (`circular_encoding`, `linear_encoding`,
   `is_encodable`) und `h5ad_source.py` (`resolve_h5ad_path`, `load_h5ad`,
   `points_from_obs`, `marker_column`, `layout`) importieren nur numpy und anndata, kein
   Bokeh und kein Qt. Sie werden **wiederverwendet**, nicht nachgebaut.

2. **Diese beiden Module dürfen nicht über `import` geholt werden.**
   `wissensnetz/prototype/` ist kein Paket, und `import encodings` würde Pythons
   stdlib-Paket `encodings` (Codecs) treffen. `app.py` lädt beide deshalb über
   `importlib.util.spec_from_file_location` per Dateipfad (Zeilen 63 bis 80, mit
   Begründung im Kommentar). Genau dasselbe Verfahren hier verwenden, relativ zu
   `Path(__file__).resolve().parent.parent`, wie es `main_window.py` für den
   Download-Ordner schon tut.

3. **Das Morphing ist eine Zeile numpy.**
   `pos = Σ aᵢ · E[i]` mit `a = softmax(SENS · slider)`, `SENS = 10.0`,
   `CIRCLE_SCALE = 5.0`, `BASE_WEIGHT = 0.5` für die Basis-View. In MP-Lite läuft die
   Gewichtung clientseitig als CustomJS; hier läuft sie in numpy im GUI-Thread, und das ist
   bei 5000 Punkten und 15 Encodings ein Bruchteil einer Millisekunde.

4. **Die 2D-Layouts heißen `X_tsne_genes` und `X_tsne_mirna`.**
   So schreibt der Mediator sie (`mediator/app/main.py` Zeilen 871, 1008, 1266), so prüft
   `scripts/check_h5ad.py` sie (`_TSNE_KEY`), so liest MP-Lite sie (`app.py` Zeilen 337,
   339). Keine anderen Schlüssel erfinden.

5. **Zum Testen liegen Dateien bereit.**
   `wissensnetz/data/selection_demo.h5ad` (7,4 MB, mit tSNE),
   `wissensnetz/data/pancancer.h5ad` (44 MB, 32 Kohorten),
   `mediator/sample_data/tcga_brca_sample.h5ad` (54 KB, voraussichtlich **ohne** `obsm`,
   also der Negativtest für Deliverable 7).

## Deliverables, Teil A

### 1) `pyqtgraph` in `requirements.txt`

Eine Zeile im Abschnitt zur Oberfläche, mit einem Satz Begründung: das Scatter soll beim
Ziehen mehrerer Slider flüssig bleiben, matplotlib wird dabei auf tausenden Punkten zäh.

Anders als bei `pyside6` ist **pip hier unbedannt**: `pyqtgraph` ist reines Python ohne
kompilierte Teile und ohne ICU-Bindung. Der Warnblock über `pyside6` gilt dafür also
nicht und wird nicht angefasst.

### 2) Titelzeile mit Umschalter, `QStackedWidget` darunter

Heute baut `NetzPanel` selbst eine Titelzeile (links fett `Wissensnetz`, rechts gedämpft
`Struktur und Zaehlungen, keine Messdaten`). Diese Zeile **wandert ins Fenster**, weil sie
künftig beide Ansichten überschreibt. `NetzPanel` gibt sie ab und wird zur reinen Ansicht;
das ist die einzige erlaubte Änderung an `netz_view.py`.

Die neue Zeile in `_build_display_side()`:

- **links** zwei zusammenhängende Schaltflächen, `Wissensnetz` und `Projektion`. Optisch
  ein Stück: linke Ecke links gerundet, rechte Ecke rechts gerundet, in der Mitte keine
  doppelte Linie. Die aktive Fläche in `theme.ACCENT` mit `theme.ON_ACCENT`, die andere in
  `theme.SURFACE` mit `theme.TEXT`. Umsetzung über zwei `QPushButton` mit `setCheckable(True)`
  in einer `QButtonGroup` mit `setExclusive(True)`.
- **rechts** der gedämpfte Hinweis, jetzt **abhängig von der Ansicht**:
  - Wissensnetz: `Struktur und Zaehlungen, keine Messdaten` (Text bleibt wörtlich)
  - Projektion: `Messdaten aus <dateiname>` beziehungsweise `Keine Datei geladen`

Darunter im senkrechten Splitter statt `self._netz` direkt ein `QStackedWidget` mit zwei
Seiten: `NetzPanel` und `ProjektionPanel`. `self._output` bleibt die zweite Hälfte des
Splitters, unverändert, und bleibt in **beiden** Ansichten sichtbar. Die drei
Schaltflächen darunter bleiben ebenfalls in beiden Ansichten.

Umschalten ist rein optisch und hat **keine Nebenwirkung**: es stößt keinen Abruf an, lädt
keine Datei, verwirft keinen Zustand. Wer zurückschaltet, findet beide Ansichten so vor,
wie er sie verlassen hat.

### 3) `frontend/morph.py`, Qt-frei

Die Mathematik und das Datenlesen kommen in ein eigenes Modul **ohne jeden Qt-Import**,
damit sie ohne Bildschirm testbar sind. Dasselbe Muster wie `store_reader.py` neben
`netz_view.py`, das hat sich in Aufgabe 19 bewährt.

Inhalt:

- Laden von `encodings.py` und `h5ad_source.py` per Dateipfad (siehe Befund 2), gebündelt
  an **einer** Stelle, nicht verstreut.
- `baue_encodings(adata) -> Morphmodell`: erzeugt die Liste der Encodings in Oviedos
  fester Reihenfolge (Deliverable 5), jedes als `(N, 2)`-Array, dazu je Eintrag Name,
  Startgewicht und ob er nutzbar ist samt Grund, wenn nicht.
- `positionen(modell, gewichte) -> (N, 2)`: `softmax(SENS · gewichte)` und die gewichtete
  Summe. Über ein gestapeltes `(N, k, 2)`-Array und `np.einsum`, nicht über eine
  Python-Schleife je Punkt.
- `skaliere_layout(arr, ziel=CIRCLE_SCALE)`: zentriert und skaliert ein tSNE-Layout auf
  eine mit den Kreis-Encodings vergleichbare Spanne. **Diese eine Funktion muss kopiert
  werden**, sie steht als `_scale_layout` in `app.py`, und `app.py` ist nicht importierbar
  (Bokeh im Modulkopf). Konstanten und Verhalten identisch übernehmen und im Docstring
  die Herkunft nennen: `mp_lite/app.py::_scale_layout`. Ohne diese Skalierung springt das
  Bild beim Morphen zwischen tSNE und Kreis-Encoding, weil die Wertebereiche
  auseinanderliegen.

### 4) `frontend/projektion_view.py`, die Ansicht

`ProjektionPanel`, ein `QWidget` mit zwei Spalten:

- **links die Karte**: ein `pyqtgraph.PlotWidget` mit einem `ScatterPlotItem`. Titel
  `Cancer map` wie im Original. Achsen ohne Beschriftung, denn die Koordinaten bedeuten
  nach dem Morphen nichts Absolutes. Seitenverhältnis fest (`setAspectLocked(True)`),
  sonst verzerren die Kreis-Encodings zu Ellipsen.
- **rechts die Slider**, etwa 240 px breit, in einem `QScrollArea`, weil 15 Slider bei
  600 px Fensterhöhe nicht alle hineinpassen.

Die Karte trägt die Kohorten-Legende, und die Punktfarbe kodiert die Kohorte
(Deliverable 8). Kein Farbwert außerhalb `theme.py`, dieselbe Regel wie in Aufgabe 17
bis 19; fehlende Tokens dort ergänzen, vorhandene nicht ändern.

Hintergrund des Plots auf `theme.WINDOW_BG` setzen und die Achsen auf `theme.BORDER`:
pyqtgraph ist von Haus aus dunkel und würde sonst als schwarzer Block in einer hellen
Oberfläche sitzen.

### 5) Oviedos 15 Slider, feste Reihenfolge und Benennung

Genau diese Reihenfolge, wörtlich diese Beschriftungen, aus `app.py::_SLIDER_SPECS`
übernommen:

```
genes            mirna              cancer             type
race             sex_at_birth       ethnicity          primary_diagnosis
has_metastasis   vital_status       cancer (ver)       tumor_stage (ver)
miRNA-210-3p (hor)                  CA9 (ver)          SAA1 (hor)
```

Wertebereich 0 bis 1, `genes` startet auf `BASE_WEIGHT = 0.5`, alle anderen auf 0. Ein
Slider ist **deaktiviert**, wenn seine Variable nicht encodierbar ist, also
`is_encodable()` falsch liefert oder die Spalte fehlt. Der Grund gehört als Tooltip an den
Slider, wörtlich benannt: `Spalte fehlt in obs`, `nur ein Wert vorhanden`,
`Marker nicht in var`. Deaktivierte Slider bleiben **sichtbar** und an ihrem Platz, das ist
dieselbe Regel wie bei ENA und GEO im Auswahlpanel: ehrliche Lücke statt unsichtbarer
Grenze.

Neben jedem Slider der aktuelle Wert mit zwei Nachkommastellen, sonst weiß man nach dem
Ziehen nicht, wo man steht.

Die Positionen werden bei jeder Sliderbewegung neu gerechnet und gesetzt. Kein Neuaufbau
des `ScatterPlotItem`, nur `setData` mit den neuen Koordinaten, sonst flackert es und wird
langsam.

### 6) Woher die `.h5ad` kommt

Drei Wege, in dieser Rangfolge, alle sichtbar in der Statuszeile:

1. **Die Datei, die gerade erzeugt wurde.** Speichert der Forscher über
   `Als .h5ad speichern` eine Datei, meldet das Fenster der Projektion den Pfad, und die
   Ansicht lädt sie, sobald man auf `Projektion` schaltet. Nicht vorher: das Laden von
   44 MB soll nicht ungefragt passieren.
2. **Eine Schaltfläche `Datei oeffnen …`** über der Karte, mit `QFileDialog`, Filter
   `*.h5ad`, Startordner `wissensnetz/data` (dieselbe Vorgabe, die
   `main_window.py` beim Speichern verwendet).
3. **`DATABRIDGE_H5AD`**, über `h5ad_source.resolve_h5ad_path()`. Damit verhält sich die
   Projektion wie MP-Lite und die Variable, die `start_all.ps1 -DemoGenerate` schon setzt,
   wirkt auch hier.

**Das Laden läuft im Worker-Thread.** `wissensnetz/data/pancancer.h5ad` ist 44 MB; im
GUI-Thread friert das Fenster mehrere Sekunden ein. Neue Klasse `H5adWorker` in
`worker.py`, nach dem Muster von `DownloadWorker`, mit derselben Regel zum Festhalten der
Thread-Referenz (siehe die Kommentare bei `_release_thread`). Während des Ladens steht in
der Karte `Lade <dateiname> …`.

### 7) Kein erfundenes Layout

Fehlt in `obsm` sowohl `X_tsne_genes` als auch `X_tsne_mirna`, gibt es **keine** Basis-View
und damit keine Karte. Dann zeigt die Fläche im Klartext, was fehlt und wie man es bekommt:

> Die Datei enthaelt kein 2D-Layout (obsm 'X_tsne_genes'). Erzeuge sie mit
> compute_tsne=true, etwa über `start_all.ps1 -DemoGenerate` oder
> `scripts/fetch_pancancer_h5ad.py`.

Das ist der eine Punkt, an dem die Projektion sich von MP-Lite **unterscheiden muss**:
MP-Lite darf als Prototyp auf synthetische Basis-Views zurückfallen, damit man die
Bedienung auch ohne Daten vorführen kann. Der Explorer darf das nicht. Er ist das Werkzeug,
mit dem geforscht wird, und eine erfundene Punktwolke wäre dort eine Lüge. Fehlt nur eines
der beiden Layouts, ist der zugehörige Slider deaktiviert, das andere trägt die Karte.

### 8) Kohortenfarben und Legende

Farbe je Punkt nach Kohorte, in der Reihenfolge von
`wissensnetz.cohorts.OVIEDO_COHORTS`, wie MP-Lite es tut. Die Kohorte je Probe aus
`obs`, über `cancer_code` aus demselben Modul. `wissensnetz.cohorts` darf die Oberfläche
importieren, das tut sie für die Kohortenliste bereits.

Die Palette selbst kommt in `theme.py`, als Funktion über `OVIEDO_COHORTS`, und nutzt
matplotlibs `nipy_spectral` wie das Original (matplotlib steht schon in
`requirements.txt`). Nur die im Datensatz **vorkommenden** Kohorten stehen in der Legende,
in `OVIEDO_COHORTS`-Reihenfolge.

Die farbigen Punkte in den Auswahllisten rechts (`theme.dot_color`) bleiben davon
**unberührt**. Dass die dort rein optisch sind und nichts kodieren, ist der offene Punkt
aus Aufgabe 18 und eine eigene Entscheidung, keine Nebenwirkung dieser Aufgabe.

## Deliverables, Teil B

### 9) Klick auf eine Probe holt den Kontext aus dem Wissensnetz

Das ist Punkt 2 der MP-Lite-Kopplung. Klick auf einen Punkt zeigt unter der Karte einen
kompakten Kontextblock: Projekt, Diagnose, die im Store vorhandenen Attribute. Quelle ist
`wissensnetz.enrichment.case_context(store, submitter_id)`, im eigenen Prozess, kein
Endpunkt im Mediator (ADR-0004 Punkt 3).

Der Verbindungsschlüssel ist `obs["submitter_id"]` gegen `db:submitterId`;
`case_context` nimmt beides, Case-IRI oder `submitterId`. Die `GraphStore`-Instanz kommt
aus `store_reader`, es wird **keine zweite** angelegt.

**Die Abfrage läuft im Worker**, neue Klasse `KontextWorker` in `worker.py`, gleiches
Muster. Ein Klick darf nicht hängen, auch wenn Fuseki langsam antwortet.

Zwei Fälle, die ehrlich benannt werden müssen und beide normal sind:

- **Der Fall steht nicht im Store.** Die `.h5ad` kann älter sein als der Storeinhalt oder
  aus einer anderen Auswahl stammen. Dann: `Dieser Fall liegt nicht im Store. Eine
  Vorschau mit dieser Kohorte laedt ihn nachträglich.` Kein Fehler, keine Fehlerfarbe.
- **Fuseki ist nicht erreichbar.** Dann dieselbe Meldung wie in der Netzansicht, und die
  Karte bleibt voll bedienbar. Das Morphing braucht den Store nicht.

### 10) Rechteckauswahl

Ein Rechteck aufziehen wählt die Punkte darin aus; die Anzahl steht als
`n Proben ausgewaehlt` unter der Karte, ausgewählte Punkte werden hervorgehoben
(`theme.ACCENT` als Rand, Füllung bleibt die Kohortenfarbe). Ein Klick daneben hebt die
Auswahl auf.

**Lasso bleibt draußen.** pyqtgraph bringt das Rechteck über den `ViewBox` mit, ein
Freihand-Lasso wäre Handarbeit an Polygon-Tests. Rechteck zuerst, Lasso ist eine eigene
Aufgabe, wenn sich zeigt, dass es fehlt.

**Der Rückkanal bleibt ebenfalls draußen.** `write_feedback` und `list_findings`, also
Punkt 3 der MP-Lite-Kopplung, sind nicht Teil dieser Aufgabe.

### 11) Tests und README

`frontend/tests/test_morph.py`, Qt-frei, mit einem kleinen künstlichen AnnData-Doppel
(oder `mediator/sample_data/tcga_brca_sample.h5ad`, wenn anndata im Testlauf verfügbar ist):

- `softmax` summiert auf 1, und ein einzelner Slider auf 1 bei sonst 0 ergibt annähernd
  genau dieses Encoding.
- `skaliere_layout` zentriert (Mittelwert nahe 0) und hält `max |Koordinate|` bei
  `CIRCLE_SCALE`.
- Fehlt `obsm`, liefert `baue_encodings` keine Basis-View und einen benannten Grund,
  statt zu werfen.
- Eine Spalte mit nur einem Wert ergibt einen deaktivierten Eintrag mit dem Grund
  `nur ein Wert vorhanden`.
- Die Reihenfolge der 15 Einträge entspricht Deliverable 5, auch wenn einzelne
  deaktiviert sind.

`frontend/README.md`: ein Abschnitt "Projektion", eingefügt nach "Netzansicht", ohne die
vorhandenen Abschnitte umzuschreiben. Was die Karte zeigt, dass die Encodings und das
`.h5ad`-Lesen aus `mp_lite` kommen und warum sie per Dateipfad geladen werden, die drei
Wege zur Datei, die Regel aus Deliverable 7, und dass MP-Lite unberührt weiterläuft.

Die vorhandenen Tests in `test_mediator_client.py` und `test_store_reader.py` bleiben
unverändert und grün.

## Verifikation

```powershell
.\start_all.ps1 -SkipLoad
```

1. Über der Anzeigefläche stehen zwei Schaltflächen. `Wissensnetz` ist aktiv und die
   Netzansicht sieht aus wie vorher. Panel, Kopfzeile, Schaltflächen, Statusleiste und
   der Antworttext unten sind unverändert.
2. Klick auf `Projektion`: die Fläche wechselt, rechts steht `Keine Datei geladen`. Das
   Auswahlpanel und der Antworttext bleiben sichtbar.
3. `Datei oeffnen …`, dann `wissensnetz\data\selection_demo.h5ad`. Während des Ladens ist
   das Fenster bedienbar. Danach: Punktwolke, Kohortenfarben, Legende, 15 Slider, `genes`
   auf 0,50, die übrigen auf 0.
4. `cancer` langsam hochziehen: die Punkte wandern von der tSNE-Wolke auf die
   Kreispositionen der Kohorten. Beim Ziehen ruckelt nichts.
5. `sex_at_birth` dazunehmen: die Wolke ordnet sich zwischen beiden Encodings ein. Zwei
   Slider gleichzeitig bleiben flüssig.
6. Ein Slider zu einer Variablen, die in dieser Datei fehlt, ist deaktiviert und nennt im
   Tooltip den Grund.
7. `mediator\sample_data\tcga_brca_sample.h5ad` öffnen: die Fläche nennt das fehlende
   `obsm 'X_tsne_genes'` und den Weg dahin. Keine Punktwolke, kein Absturz, keine
   erfundenen Koordinaten.
8. `wissensnetz\data\pancancer.h5ad` öffnen (44 MB, 32 Kohorten): lädt ohne Einfrieren,
   die Legende zeigt die vorkommenden Kohorten in Oviedo-Reihenfolge.
9. Zurück auf `Wissensnetz` und wieder auf `Projektion`: beide Ansichten sind unverändert,
   die Datei ist noch geladen, die Sliderstellungen stehen noch.
10. Fenster auf 900 × 600: nichts überlappt, die Sliderspalte scrollt, die Karte bleibt
    quadratisch.
11. **Der Auftrag ist unverändert.** Dieselbe Auswahl ergibt denselben `current_payload()`,
    und `Vorschau` verhält sich wie vorher.
12. Teil B: Klick auf einen Punkt zeigt den Kontext aus dem Store. Ein Fall, der nicht im
    Store liegt, wird als solcher benannt. `docker compose stop graph-db`, dann nochmal
    klicken: Meldung, und die Karte bleibt bedienbar.
13. Teil B: Rechteck aufziehen zeigt die Anzahl und hebt die Punkte hervor, Klick daneben
    hebt die Auswahl auf.
14. `pytest frontend/tests -q` ist grün.
15. **Mit einer Bildschirmaufnahme prüfen, nicht mit `widget.grab()`.** Letzteres malt den
    Fensterhintergrund nicht mit; daran ist in Aufgabe 17 ein schwarzes Popup
    durchgerutscht (siehe `frontend/README.md`).

## Grenze

Nur `frontend/**` plus die eine Zeile in `requirements.txt`. Insbesondere:

- **`wissensnetz/prototype/mp_lite/` wird nicht angefasst.** Die zwei Hilfsmodule werden
  gelesen, nicht verändert, nicht verschoben, nicht kopiert (Ausnahme: die eine Funktion
  aus Deliverable 3, die in `app.py` steckt).
- **Kein QtWebEngine, kein pyvis, kein Bokeh** im `frontend/`. Die Ansicht ist ein
  Qt-Widget, kein eingebetteter Browser.
- **Kein Schreiben in den Store.** Auch Teil B liest nur.
- **Kein zusätzlicher Endpunkt im Mediator.**
- Keine Umbenennung, keine Umsortierung, kein Aufräumen in den vorhandenen Dateien.

## Hinweise, keine Aufgabe

**`encodings.py` und `h5ad_source.py` stehen am falschen Ort.** Sie sind mit dieser Aufgabe
gemeinsamer Code von MP-Lite und Explorer, liegen aber in einem Prototyp-Ordner, der kein
Paket ist, und müssen deshalb über Dateipfade geladen werden. Der saubere Platz wäre
`wissensnetz/src/wissensnetz/`. Das Verschieben berührt `mp_lite/app.py` und ist deshalb
eine eigene Entscheidung.

**`skaliere_layout` existiert danach zweimal**, hier und als `_scale_layout` in
`app.py`. Das ist die Folge daraus, dass `app.py` Bokeh im Modulkopf importiert. Beim
Verschieben nach oben löst sich auch das auf.

**Der Rückkanal fehlt noch.** `write_feedback` und `list_findings` sind in MP-Lite fertig
und im Explorer nicht angebunden. Erst damit wäre der Kreis aus dem Konzept geschlossen:
Auswahl in der Karte, Hypothese, Named Graph.
