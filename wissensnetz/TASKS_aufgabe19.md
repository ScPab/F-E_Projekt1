# Aufgabe 19 (nur): Das Wissensnetz in der Oberfläche zeigen, wie es wächst

> Diese Datei ersetzt die erste Fassung von Aufgabe 19. Der Unterschied: die
> vorhandene Oberfläche wird **nicht umgebaut**, das Netz wird eingesetzt. Abschnitt
> "Was unverändert bleibt" ist deshalb Teil der Aufgabe, nicht Beiwerk.

## Rahmen

Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.

Erlaubt sind `frontend/**` und **eine** Ergänzung in `docs/adr/0004-frontend-pyside6.md`
(Deliverable 10). **NICHT** `mediator/`, **NICHT** `wrappers/`, **NICHT**
`wissensnetz/src/`. Kleine Commits.

Grundlage: `docs/adr/0003-ui-gesteuerte-akquise.md`, `docs/adr/0004-frontend-pyside6.md`
Punkt 3 und 5, die Layoutskizze `recherche/Konzept_Navigation_Ebene1.png`, und die in
Aufgabe 17 und 18 erarbeiteten Bausteine `frontend/theme.py` und
`frontend/searchable_select.py`.

## Was unverändert bleibt

Die Oberfläche steht und ist eingespielt. Diese Aufgabe **fügt ein Feature ein**, sie baut
nichts um. Alles Folgende wird nicht angefasst, auch nicht "bei der Gelegenheit":

- `_build_panel()` und das gesamte Auswahlpanel: fünf einzeilige Felder, `MultiSelect`,
  `SearchableSelect`, `config/panel.json`. Kein neues Feld, keine neue Zeile, keine
  geänderte Breite (`theme.PANEL_WIDTH` bleibt 360).
- `_build_header()` und die Kopfzeile.
- Die drei Schaltflächen, ihre Reihenfolge, ihre Beschriftung und `_set_busy()`.
- `current_payload()`, `mediator_client.py` und der Auftrag an den Mediator. Er bleibt
  Zeichen für Zeichen derselbe, das ist Teil der Abnahme.
- `_render()` und der Text, den die Anzeigefläche nach einem Aufruf zeigt.
- `self._output` selbst: dasselbe `QPlainTextEdit`, derselbe `objectName`, derselbe
  Anfangstext, weiterhin schreibgeschützt und ohne Zeilenumbruch.
- Mindestgröße des Fensters (900 × 600), `theme.HEADER_HEIGHT`, der waagerechte
  Splitter zwischen Anzeige und Panel.
- In `theme.py` werden Tokens **ergänzt**, keine bestehenden Werte geändert.

In `main_window.py` sind genau sechs Berührungspunkte erlaubt, sonst keiner:

| Stelle | Änderung |
|---|---|
| `_build_display_side()` | die eine Zeile `layout.addWidget(self._output, stretch=1)` wird ein senkrechter Splitter mit Netz und `self._output` |
| `_build_menu()` | ein Menüeintrag `Ansicht > Netz aktualisieren` (F5) |
| `_build_ui()` | ein `addPermanentWidget` an der vorhandenen `self._status` |
| `_start()` | die beiden Abzug-Funktionen an `worker.start_call` durchreichen |
| `_on_finished()` | dritter Signalparameter, an die Netzansicht weiterreichen |
| Fensterende von `__init__` | ein erstes Zeichnen des Netzes |

## Ausgangslage

Aufgabe 17 hat das Wissensnetz bewusst ausgespart: die Oberfläche spricht bis heute nur
per HTTP mit dem Mediator und liest nichts aus dem Store. Das ändert sich jetzt, und zwar
genau so, wie ADR-0004 Punkt 3 es vorgesehen hat: **die Anzeige liest über das Paket
`wissensnetz` im eigenen Prozess**, nicht über einen zusätzlichen Endpunkt im Mediator.

Vier Befunde aus dem Code, die den Zuschnitt bestimmen. Sie sind geprüft, nicht vermutet:

1. **Die Form des Netzes ist bereits die Geschichte der Aufrufe.** Im Store stehen genau
   die Kohorten, die je angefragt wurden, und unter jeder genau die Attribute, die je als
   Trigger mitgegeben wurden. Eine nie angefragte Kohorte ist nicht ausgegraut, sie
   existiert nicht. Das Netz zeichnen heißt also zeigen, was gefragt wurde.

2. **`Vorschau` füllt den Store schon heute.** `SelectionRequest.load` steht in
   `mediator/app/schemas.py` auf `True`, und `_load_selection_knowledge` läuft in
   `mediator/app/main.py` bei `preview` genauso wie bei `generate`. Der billige Knopf lässt
   das Netz wachsen, der teure fügt nur die Matrix dazu.

3. **Der Store weiß nicht, welcher Fall aus welchem Aufruf kam.** Der Mediator lädt alles
   in den Default-Graph und ruft `wissensnetz.selection.write_selection` nie auf. Es gibt
   kein Manifest und keinen Named Graph, `cases_for_selection` liefert deshalb nichts.
   **Daraus folgt der ganze Zuschnitt von Deliverable 4:** "was ist neu" kann nur die
   Oberfläche selbst wissen, über zwei Abzüge und einen Vergleich. Jeder Versuch, das aus
   dem Store zu lesen, läuft ins Leere.

4. **Der Store ist über `localhost:3030` erreichbar.** `wissensnetz/src/wissensnetz/config.py`
   liest `GRAPH_DB_HOST` mit Vorgabe `localhost`; der Container-Name `graph-db` gilt nur
   innerhalb von Compose. Die Oberfläche läuft als Host-Prozess und braucht deshalb keine
   Sonderbehandlung.

## Ziel

Die Anzeigefläche links zeigt zusätzlich zum bisherigen Antworttext das Wissensnetz als
**gezeichnetes Netz** und markiert nach jedem Aufruf, was dazugekommen ist. Alles, was dort
steht, stammt aus SPARQL-Abfragen gegen Fuseki, nichts aus der Mediator-Antwort. Ist der
Store leer, sagt die Fläche das, statt leer zu wirken.

## Deliverables

### 1) `frontend/store_reader.py`, Qt-frei

Neues Modul, **ohne jeden Qt-Import**, damit es wie `mediator_client.py` ohne Bildschirm
testbar bleibt. Es hält die einzige Verbindung zum Store und gibt einfache Python-Daten
zurück (`dict`/`list`), keine Widgets und keine rdflib-Objekte.

```python
from wissensnetz.graphstore import GraphStore
```

Funktionen:

- `snapshot(store) -> dict` liefert den vollständigen Abzug: Gesamtzahlen, Kohorten,
  Attribute je Kohorte. Genau **drei** Abfragen, siehe unten.
- `is_reachable(store) -> bool` reicht `GraphStore.is_reachable()` durch.
- `diff(vorher, nachher) -> dict` vergleicht zwei Abzüge (Deliverable 4).

Die drei Abfragen, wörtlich so zu verwenden und nicht umzuformulieren:

```sparql
# a) Wurzel
PREFIX db: <http://databridge.hka/onto#>
SELECT (COUNT(DISTINCT ?case) AS ?cases) (COUNT(DISTINCT ?project) AS ?projects)
WHERE {
  ?case a db:Case .
  OPTIONAL { ?case db:belongsToProject ?project }
}
```

```sparql
# b) Kohorten
PREFIX db: <http://databridge.hka/onto#>
SELECT ?projectId (COUNT(DISTINCT ?case) AS ?cases)
WHERE {
  ?project a db:Project ; db:projectId ?projectId .
  ?case db:belongsToProject ?project .
}
GROUP BY ?projectId
```

```sparql
# c) Attribute je Kohorte, in EINEM Aufruf fuer alle Kohorten
PREFIX db:  <http://databridge.hka/onto#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?projectId ?p (COUNT(DISTINCT ?case) AS ?cases) (COUNT(DISTINCT ?v) AS ?values)
WHERE {
  ?case a db:Case ; db:belongsToProject ?project .
  ?project db:projectId ?projectId .
  ?case db:hasDemographic|db:hasDiagnosis|db:hasSample ?entity .
  ?entity ?p ?v .
  FILTER(isLiteral(?v))
  FILTER(?p != rdf:type)
}
GROUP BY ?projectId ?p
```

Abfrage c) ist der Kern und hat eine Eigenschaft, die erhalten bleiben muss: **sie kennt
die Attributliste nicht.** Legt `resolve_attribute()` im Mediator dynamisch eine neue
Property an, erscheint sie im Netz von allein. Deshalb hier keine Liste von Properties
einbauen, auch nicht "zur Sicherheit".

`isLiteral(?v)` erledigt zwei Dinge nebenbei: es wirft die Rückverweise
(`db:isDemographicOf`, `db:describesCase`) heraus und lässt die NCIt-IRI aus
`db:primaryDiagnosis` weg, während der Text aus `db:primaryDiagnosisLabel` bleibt. Das in
einem Kommentar festhalten, sonst wird es beim nächsten Anfassen "aufgeräumt".

### 2) `frontend/netz_view.py`, das gezeichnete Netz

Ein `QGraphicsView` mit eigener `QGraphicsScene`. **Nicht** `graph_view` nennen: unter
`scripts/graph_view.py` liegt bereits die pyvis-Ansicht, und zwei Dinge mit demselben Namen
in einem Projekt sind eine Falle. Keine neue Abhängigkeit, `QtWidgets` reicht; insbesondere
**kein** QtWebEngine und **kein** pyvis, die Oberfläche soll gerade kein Browser sein.

Drei Reihen von oben nach unten, wie in `recherche/Konzept_Navigation_Ebene1.png`:

| Reihe | Knoten | Beschriftung |
|---|---|---|
| 1 | Wurzel | `Store`, darunter gedämpft `N Kohorten · M Fälle` |
| 2 | je Kohorte einer | `TCGA-BRCA`, darunter gedämpft `20 Fälle` |
| 3 | Attribute **der aufgeklappten Kohorte** | `sexAtBirth`, darunter gedämpft `20 Fälle · 2 Werte` |

Aussehen der Knoten nach der Skizze: abgerundetes Rechteck (`theme.RADIUS`), Fläche
`theme.WINDOW_BG`, Rand `theme.BORDER`, fette Titelzeile in `theme.TEXT`, gedämpfte
Zweitzeile in `theme.TEXT_MUTED`. Kanten als weiche Kurven von der Unterkante des
Elternknotens zur Oberkante des Kindes, in `theme.BORDER`. Links an der Kantenschar ein
gedämpftes Etikett `db:belongsToProject` beziehungsweise
`db:hasDemographic | db:hasDiagnosis | db:hasSample`, wie in der Skizze. **Kein Farbwert
außerhalb `theme.py`**, dieselbe Regel wie in Aufgabe 17 und 18; fehlende Tokens dort
ergänzen, vorhandene nicht ändern.

Reihe 2 zeigt höchstens **sieben** Kohorten, Reihe 3 höchstens **sieben** Attribute. Der
Rest wird zu einem gedämpften `… N weitere Kohorten` unter der Reihe, genau wie in der
Skizze. Reihenfolge: **neu zuerst, dann gewachsen, dann nach Fallzahl absteigend.** Das ist
nicht Kosmetik, sondern die Bedingung dafür, dass Wachstum überhaupt sichtbar ist: eine
neue Kohorte darf nie hinter `… N weitere` verschwinden.

Die Szene passt sich der Breite an (`fitInView` mit `KeepAspectRatio` beim Anpassen der
Fenstergröße). Bei 900 × 600, der Mindestgröße des Fensters, darf **nichts überlappen** und
nichts abgeschnitten sein. Genau daran sind die ersten Fassungen der Auswahllisten in
Aufgabe 17 und 18 gescheitert.

Über dem Netz eine schmale Titelzeile wie in der Skizze: links fett `Wissensnetz`, rechts
gedämpft `Struktur und Zählungen, keine Messdaten`. Eine Zeile, keine eigene Kartenfläche.

### 3) Bedienung im Netz

Klick auf einen Kohortenknoten klappt ihn auf, Reihe 3 zeigt dann seine Attribute. Erneuter
Klick klappt ihn zu. Es ist immer **höchstens eine** Kohorte aufgeklappt, sonst wird Reihe 3
beliebig breit. Klick auf die Wurzel klappt alles zu. Der aufgeklappte Knoten trägt einen
**dickeren Rand**, keine andere Farbe.

Das ist eine bewusste Trennung: **Auswahl zeigt der Rand, Wachstum zeigt die Farbe.** Zwei
Signale, die sich nicht ins Gehege kommen.

**Der Klick ändert das Auswahlpanel rechts nicht.** Das Netz ist in dieser Fassung eine
Anzeige, keine Navigation. Der Weg "im Netz klicken und damit den nächsten Auftrag
zusammenstellen" ist der zurückgestellte Drill-down aus ADR-0003 und eine eigene
Entscheidung, keine Nebenwirkung dieser Aufgabe.

### 4) Wachstum über zwei Abzüge

Ablauf bei jedem Aufruf, alles im Worker-Thread, nichts davon im GUI-Thread:

1. Abzug A über `store_reader.snapshot()`, **bevor** die Anfrage abgeschickt wird.
2. Der Aufruf an den Mediator wie bisher.
3. Abzug B, nachdem die Antwort da ist.
4. `diff(A, B)` und das Netz neu zeichnen.

Die Reihenfolge ist Teil der Aufgabe. Wird A nebenläufig zum Aufruf geholt, kann er bereits
geladene Daten enthalten und der Unterschied fällt zu klein aus. Ein synchroner Abzug in
`_start()` scheidet ebenfalls aus: Abfrage c) läuft auf einem vollen Store spürbar lange,
und das Fenster würde genau im Moment des Klicks einfrieren.

**Der einzige erlaubte Eingriff in `worker.py`:** `SelectionWorker` bekommt zwei optionale
Rückrufe und einen dritten Signalparameter.

```python
def __init__(self, payload, mode, *, vorher=None, nachher=None) -> None
finished = Signal(object, str, object)   # (Result, mode, diff | None)
```

`vorher` und `nachher` sind parameterlose Funktionen, die das Fenster übergibt; der Worker
ruft sie auf und weiß nicht, was sie tun. Damit bleibt der Grundsatz aus dem Modul-Docstring
in Kraft: der Worker entscheidet nichts und kennt den Store nicht. `store_reader` wird in
`worker.py` **nicht** importiert. `DownloadWorker` und `start_download` bleiben unberührt.

Schlägt ein Abzug fehl, etwa weil Fuseki nicht läuft, ist der dritte Parameter `None` und
der Mediator-Aufruf läuft trotzdem zu Ende. Ein nicht erreichbarer Store darf einen Auftrag
nie verhindern.

Drei Zustände je Knoten:

| Zustand | Bedeutung | Farbe |
|---|---|---|
| unverändert | war vorher da, gleiche Zahl | `theme.WINDOW_BG` auf `theme.BORDER` |
| gewachsen | war vorher da, Zahl ist gestiegen | `theme.ACCENT_BG` / `theme.ACCENT`, Zweitzeile ergänzt um `+N` |
| neu | war vorher nicht da | `theme.SUCCESS_BG` / `theme.SUCCESS` |

Die Markierung gilt für den letzten Aufruf und wird **nicht gespeichert**. Nach einem
Neustart zeigt das Netz den aktuellen Stand ohne Markierungen. Eine Historie über die
Sitzung hinaus wäre erfunden, weil der Store sie nicht hergibt (siehe Befund 3).

### 5) Leerer Store und nicht erreichbarer Store sind zwei Zustände

Sie sehen sonst gleich aus und bedeuten Verschiedenes:

- **Leer** (erreichbar, null Fälle): in der Netzfläche mittig, gedämpft: "Der Store enthält
  noch keine Fälle. Jede Vorschau erweitert das Netz." Das ist der normale Anfang nach
  `docker compose down -v` und kein Fehler, also **keine** Fehlerfarbe.
- **Nicht erreichbar**: "Fuseki unter `<url>` nicht erreichbar. Läuft `docker compose up`?"
  in `theme.ERROR`, plus dieselbe Meldung über `set_status(..., "error")`.

Ein nicht erreichbarer Store darf die Oberfläche **nicht** blockieren: Vorschau und
Generieren bleiben bedienbar, denn sie sprechen mit dem Mediator, nicht mit Fuseki.

### 6) Platz im Fenster: ein Splitter, kein Umbau

In `_build_display_side()` wird die **eine** Zeile

```python
layout.addWidget(self._output, stretch=1)
```

ersetzt durch einen senkrechten `QSplitter`, der zwei Dinge enthält: oben die Netzfläche
(Deliverable 2, Mindesthöhe 260 px), unten `self._output` (Mindesthöhe 120 px). Das Widget
`self._output` wird dabei unverändert übernommen, nicht neu gebaut.

Anfangsverhältnis etwa 60 zu 40 zugunsten des Netzes, danach frei verschiebbar. Die
Splitterstellung wird **nicht** gespeichert. Die drei Schaltflächen bleiben darunter, das
Panel rechts, der Kopf und die Statusleiste bleiben, wie sie sind.

Der waagerechte Splitter zwischen Anzeige und Panel bleibt unangetastet. Es entsteht also
ein Splitter im Splitter, das ist gewollt und der kleinstmögliche Eingriff.

### 7) Statusleiste ergänzen, ohne sie zu kapern

`set_status()` schreibt weiterhin die wechselnden Meldungen, unverändert. **Zusätzlich**
rechts ein dauerhaftes Feld über `QStatusBar.addPermanentWidget`, das den Stand des Stores
zeigt: `Store: 20 Fälle · 1 Kohorte` beziehungsweise `Store: nicht erreichbar`. Das
entspricht der rechten Seite der Fußzeile in der Skizze und kollidiert nicht mit den
Meldungen links.

### 8) Aktualisieren

Das Netz wird gelesen

- beim Start des Fensters,
- nach jedem Aufruf (Deliverable 4),
- auf Anforderung über einen Menüeintrag `Ansicht > Netz aktualisieren` mit `F5`.

Der letzte Punkt ist nötig, weil der Store sich auch ohne die Oberfläche ändert, etwa durch
`scripts/run_selection.py` oder `start_all.ps1 -FullLoad`. Ohne Aktualisierung altert das
Bild still. Gibt es das Menü `Ansicht` noch nicht, kommt es neu dazu; das vorhandene Menü
`Datei` bleibt unverändert.

### 9) Namen: Store-Property oder Panel-Attribut

Das Panel schreibt `sex_at_birth`, der Store trägt `db:sexAtBirth`. Zwei Schreibweisen für
dasselbe, und die Übersetzung gehört dem Mediator (`KNOWN_ATTRIBUTES`), den die Oberfläche
nicht importieren darf.

Regel, mechanisch und überprüfbar: Titelzeile des Attributknotens ist der **lokale Name der
Property aus dem Store**. Gedämpfte Zweitzeile mit dem Panel-Namen **nur dann**, wenn
`panel_name` in camelCase genau dem lokalen Namen entspricht. Kein Raten, keine Tabelle.

Damit bleiben zwei der elf ohne Zweitzeile, und das ist richtig so: `has_metastasis` liegt
als `db:metastasisAtDiagnosis` im Store, `primary_diagnosis` als `db:primaryDiagnosisLabel`.
Eine halb stimmende Rückübersetzung wäre genau die Sorte stiller Fehlzuordnung, die uns
schon das tote GDC-Feld `gender` eingebrockt hat.

### 10) `frontend/README.md` und ADR-0004

README: ein Abschnitt "Netzansicht", eingefügt nach "Bedienung", ohne die vorhandenen
Abschnitte umzuschreiben. Was gezeigt wird, dass es aus SPARQL kommt und nicht aus der
Mediator-Antwort, dass `Vorschau` das Netz wachsen lässt, die drei Wachstumsfarben, die
beiden leeren Zustände, und die Namensregel aus Deliverable 9 mit ihren zwei Ausnahmen.

ADR-0004: **ein** Absatz unter "Konsequenzen", dass Punkt 3 mit dieser Aufgabe in Kraft
tritt. Konkret: die Oberfläche hängt jetzt an zwei Diensten, und `pip install -e ./wissensnetz`
ist keine Rückfalloption mehr, sondern Voraussetzung. Die Kohortenliste hat bis heute einen
Rückfall auf `config/panel.json`, die Netzansicht hat keinen.

### 11) Tests

`frontend/tests/test_store_reader.py`, Qt-frei, mit einem Doppel für `GraphStore` (die
Abfragen werden nicht wirklich gestellt):

- `snapshot()` auf leeren Ergebnismengen ergibt einen leeren, aber wohlgeformten Abzug,
  keinen `KeyError`.
- `diff()` erkennt eine neue Kohorte, eine gewachsene Kohorte und eine unveränderte.
- `diff()` erkennt ein neu dazugekommenes Attribut unter einer schon vorhandenen Kohorte.
  Das ist der Fall, der das Trigger-Modell abbildet: gleiche Kohorte, neue Frage.
- Die Sortierung liefert neu vor gewachsen vor Fallzahl.
- Die Namensregel aus Deliverable 9: `sex_at_birth` bekommt die Zweitzeile,
  `has_metastasis` bekommt keine.

Die vorhandenen Tests in `frontend/tests/test_mediator_client.py` bleiben unverändert und
grün. Ändert sich dort etwas, ist das ein Zeichen, dass der Auftrag angefasst wurde.

## Verifikation

Mit wirklich leerem Store, sonst ist der Test wertlos:

```powershell
docker compose down -v
.\start_all.ps1 -SkipLoad
```

1. Das Fenster sieht aus wie vorher, nur dass die Anzeigefläche jetzt oben das Netz und
   unten den Antworttext zeigt. Panel, Kopfzeile, Schaltflächen und Statusleiste sind
   unverändert.
2. Die Netzfläche sagt, dass der Store noch keine Fälle enthält. Keine Fehlerfarbe, kein
   leerer weißer Kasten. Die Statusleiste rechts zeigt `Store: 0 Fälle`.
3. Auswahl TCGA-BRCA, Attribute `sex_at_birth` und `primary_diagnosis`, Proben 20,
   dann **Vorschau**. Danach: Wurzel, ein Kohortenknoten TCGA-BRCA, beide grün markiert.
   Kohorte anklicken, Reihe 3 zeigt genau die Attribute, die im Auftrag standen, ebenfalls
   grün. Keine Rohdaten heruntergeladen, das Netz ist trotzdem gewachsen.
4. Dieselbe Auswahl mit Proben 50, nochmal **Vorschau**. TCGA-BRCA ist jetzt blau mit
   `+N` in der Zweitzeile, nicht grün. Die Attribute ebenso.
5. Auswahl auf TCGA-LUAD umstellen, **Vorschau**. Neuer grüner Zweig neben TCGA-BRCA,
   TCGA-BRCA jetzt neutral, ohne Markierung.
6. Ein Attribut dazunehmen, das vorher nicht im Auftrag stand, etwa `vital_status`,
   **Vorschau**. Unter der Kohorte erscheint ein neuer grüner Attributknoten, die Kohorte
   selbst bleibt neutral oder wächst nur leicht.
7. **Der Auftrag ist unverändert.** Dieselbe Auswahl wie vor dem Umbau ergibt denselben
   `current_payload()`. Am besten vorher einmal abschreiben und nachher vergleichen.
8. Fenster auf 900 × 600 ziehen: nichts überlappt, nichts ist abgeschnitten, und das Panel
   rechts sitzt genauso wie vorher.
9. `docker compose stop graph-db`, dann `F5`: die Fläche meldet, dass Fuseki nicht
   erreichbar ist, die Statusleiste ebenso, und **Vorschau bleibt bedienbar**.
10. `pytest frontend/tests -q` ist grün.
11. **Mit einer Bildschirmaufnahme prüfen, nicht mit `widget.grab()`.** Letzteres malt den
    Fensterhintergrund nicht mit; daran ist in Aufgabe 17 ein schwarzes Popup
    durchgerutscht (siehe `frontend/README.md`, Abschnitt zu den Top-Level-Fenstern).

## Grenze

Nur `frontend/**` plus der eine Absatz in `docs/adr/0004-frontend-pyside6.md`. Keine
Änderung an `mediator/`, `wrappers/` oder `wissensnetz/src/`. Insbesondere:

- **Keine SPARQL-UPDATE-Anweisung.** Die Oberfläche liest, sie schreibt nicht in den Store.
  Geschrieben wird ausschließlich vom Mediator.
- **Kein zusätzlicher Endpunkt im Mediator** für die Anzeige. Das ist der Punkt, an dem
  ADR-0004 sich gegen C# entschieden hat.
- **Keine Umbenennung, keine Umsortierung, kein Aufräumen** in den vorhandenen Dateien.
  Wer beim Einfügen etwas findet, das verbessert gehört, notiert es und lässt es stehen.
- `searchable_select.py` und `config/panel.json` werden **nicht** angefasst.

## Hinweise, keine Aufgabe

**Die Ersetzungslogik bleibt offen.** `_load_selection_knowledge` hängt nur an, siehe die
dokumentierte Schuld P4. Bei der gewählten Tiefe, also nur bis zum Attribut, fällt das nicht
auf, weil über `COUNT(DISTINCT ?case)` gezählt wird. Sichtbar würde es erst auf einer
Werteebene. Ein schwacher, aber belastbarer Hinweis steckt schon in Abfrage c): sind mehr
distinkte Werte als Fälle vorhanden, trägt mindestens ein Fall zwei Werte an derselben
Property. Das kann P4 sein oder schlicht ein Fall mit zwei Diagnosen, und deshalb wird es in
dieser Fassung **nicht** als Fehler markiert.

**Die zweite Achse fehlt noch.** `db:primaryDiagnosis` zeigt auf NCIt, und dort hängt die
`rdfs:subClassOf`-Hierarchie, die `enrichment.subclasses()` bereits lesen kann. Das ist das
Netz, das schon Verbindungen hat, und der natürliche nächste Schritt nach dieser Aufgabe.
Er bleibt draußen, weil er die Alignment-Tabelle voraussetzt, und die hat heute drei
Einträge, von denen einer falsch ist.
