# Umsetzungsplan: UI-gesteuerte Akquise

Stand 2026-09-17, Fassung 3 (nach zwei Korrekturen von Marcel). Grundlage ist die
Handskizze vom 2026-09-17: oben Fensterlayout und Auswahlpanel, unten die Ablaufkette.
Dieses Dokument übersetzt die Skizze in eine Änderungsliste gegen die heutige Codebase,
aufgeteilt nach Zuständigkeit. Alle Zeilenangaben beziehen sich auf den Stand vom
2026-09-17.

---

## 1 Wie ich das Konzept lese

1. **Die Oberfläche ist zweigeteilt.** Links die Darstellungsfläche, rechts das
   Auswahlpanel, unten zwei Schaltflächen: `Vorschau` und `Generieren`.
2. **Das Auswahlpanel hat vier Zeilen.** `Krebs` (Kohorte, Dropdown, mit `+` also
   mehrfach), `Var` (Modalität: gene expression, DNA-Methylierung, Mutationen), `Obj`
   (klinische Attribute, mehrere addierbar, in der Skizze mit `Trigger` beschriftet),
   `Datenquelle` (TCGA und später weitere).
3. **`Obj` sind Trigger, keine Filter.** Ein hinzugefügtes Attribut erweitert den Auftrag,
   es verengt ihn nicht. Jedes Attribut wird zu einem angefragten Feld und später zu einer
   `obs`-Spalte.
4. **"Weitere Ebene"** sind die gestapelten gestrichelten Kopien: eine Auswahl kann
   geschachtelt werden, jede Ebene ein weiterer Panelsatz.
5. **Beim Start bietet die Software vorgespeicherte Attribute an** (gender, krebs, …).
   Optional darüber hinaus eine Abstraktion, die über die API nach Labels sucht und daraus
   neue Attribute anlegt.
6. **Aus der Auswahl wird ein JSON.** Das ist der Suchauftrag und damit der Vertrag.
7. **Der Suchauftrag geht an den Wrapper.** Der Wrapper führt die API-Abfrage gegen die
   gewählte Datenbank aus. Der Mediator entscheidet dabei **nicht**, was das Wissensnetz
   braucht, und er fragt es auch nicht für die Oberfläche ab.
8. **Der Mediator nimmt das Ergebnis, übersetzt es und verzweigt.** Aus dem übersetzten
   Ergebnis entsteht beides: die Anknüpfung an das Wissensnetz und das anndata.
9. **Ein Datensatz, zwei Darstellungen.** Die beiden Pfeile unten rechts sind **keine
   Rückkopplung**. Derselbe abgerufene Datensatz wird an das Wissensnetz geknüpft und
   für das anndata verwendet. Ein Abruf, eine Übersetzung, zwei Serialisierungen.

Die Kette ist damit linear und einfach:

```
Auswahl → JSON → Wrapper (API) → Mediator (Übersetzung) → ┬→ Wissensnetz  (Vorschau)
                                                          └→ anndata      (Generieren)
```

## 1a Eine Präzisierung zu "geht an den Wrapper"

Fachlich geht der Auftrag an den Wrapper. Technisch gibt es dafür keine eigene Adresse: die
Wrapper sind laut ADR-0001 **Python-Pakete im Mediator-Container**, kein eigener Service.
Die Oberfläche spricht also weiterhin mit dem Mediator, aber der Mediator verhält sich an
dieser Stelle wie ein Durchreicher, nicht wie ein Entscheider. Er nimmt das JSON, ruft die
Wrapper-Funktion, und die Intelligenz liegt im JSON, nicht in ihm.

Das ist wichtig für die Bewertung der Arbeit: der Endpunkt, der den Auftrag annimmt, ist
klein. Was groß ist, steht in Abschnitt 1b.

## 1b Der eigentliche Umbau: ein Abruf, zwei Serialisierungen

Heute ist Punkt 9 **nicht** erfüllt. Die beiden Senken werden aus zwei unabhängigen
Abrufen befüllt:

- `POST /transform` holt für GDC `wrapper.search("cases", …, fields=TRANSFORM_CASE_FIELDS)`
  und baut daraus die Tripel (`mediator/app/main.py` ab Zeile 412).
- `POST /export/anndata` holt `wrapper.query("files", …)` mit einer ganz anderen Feldliste
  und baut daraus die Matrix (`mediator/app/main.py` ab Zeile 555).

Zwei Abrufe, zwei unabhängig gezogene Stichproben. Deshalb können Graph und Matrix
auseinanderlaufen, und genau daher stammen zwei bekannte Notlösungen: der GDC-Fallback in
`build_obs(..., gdc_project_by_sample=…)` und der Stratifizierungs-Fix über
`per_project_size`. Beide behandeln Symptome dieser Trennung.

Die neue Variante schreibt vor: **ein Auftrag, ein Abruf, ein Proben-Set, zwei
Serialisierungen.** Die Probenmenge wird einmal bestimmt, danach schreibt der Mediator
dieselbe Menge zweimal weg, einmal als RDF, einmal als `.h5ad`. Der Fallback in `build_obs`
wird damit prinzipiell überflüssig, weil `obs` verlässlich aus dem Graphen kommen kann.

Voraussetzung ist **eine** Identität über beide Senken. Die gibt es schon: der TCGA-Barcode
beziehungsweise `db:submitterId` ist der Join-Schlüssel, in MP-lite die Spalte `tumor`. Der
Wrapper hat dafür bereits `extract_sample_case_rows()` (`wrappers/gdc/client.py` Zeile 158),
die Proben- und Fall-Zuordnung aus den Datei-Treffern zieht. Dieser Baustein wird zum
Angelpunkt.

## 2 Was heute fehlt

Nach der Korrektur ist die Lücke deutlich kleiner als in Fassung 1 angenommen, weil die
Oberfläche ihre Auswahlwerte zunächst aus vorgespeicherten Attributen bezieht und nicht aus
dem Wissensnetz. Es fehlen:

1. **Ein Endpunkt, der ein Auswahl-JSON annimmt.** Heute verlangt `POST /query`, dass der
   Aufrufer Endpunkt, `project_id` und `experimental_strategy` einzeln übergibt
   (`schemas.py` Zeile 17), und liefert rohe GDC-Treffer zurück.
2. **Die Trennung billig gegen teuer.** `POST /export/anndata` lädt sofort herunter, eine
   Vorschau existiert nicht.
3. **Dynamische Felder.** `TRANSFORM_CASE_FIELDS` (`main.py` Zeile 59) ist eine Konstante
   mit 15 Einträgen. Ein Attribut, das die Oberfläche hinzufügt, käme nicht an.
4. **Die Verzweigung aus 1b.** Sie existiert in keiner Form.
5. **Die Oberfläche selbst.** `frontend/` enthält `.gitkeep` und ein README, kein
   Compose-Service, keine Technologieentscheidung.

## 3 Änderungen im Mediator (Pablo)

**Erster Durchgang**

| # | Was | Wo |
|---|---|---|
| M1 | Neues Request-Modell `SelectionRequest` als Abbild des UI-JSON: `source`, `cohorts[]`, `modality`, `attributes[]`, `levels[]`. Dazu `PreviewResponse`. | `mediator/app/schemas.py`, neben `TransformRequest` (Zeile 76) |
| M2 | Zwei Endpunkte: `POST /selection/preview` (billig) und `POST /selection/generate` (teuer, schreibt `.h5ad`). Beide reichen das JSON an den Wrapper durch und entscheiden selbst nichts über Inhalte. | `mediator/app/main.py`, neben `/transform` (Zeile 389) |
| M3 | **Gemeinsamer Abrufschritt, der Kern.** Eine interne Funktion bestimmt das Proben-Set einmal (Datei-Abfrage plus `extract_sample_case_rows()`), danach laufen zwei Serialisierungen auf genau dieser Menge. `cases_to_graph()` bekommt seine Fälle aus dem geteilten Set statt aus einem eigenen `search("cases")`. | `main.py`, Zusammenführung von Zeile 412 und Zeile 555 |
| M4 | `TRANSFORM_CASE_FIELDS` von Konstante zu abgeleitet: die angefragten Felder entstehen aus `attributes[]`. Das ist der Kern der Trigger-Idee. | `main.py` Zeile 59 |
| M5 | `cases_to_graph()` muss zusätzliche Attribute generisch auf `db:`-Properties abbilden. Heute ist jedes Feld einzeln ausprogrammiert (Zeilen 90 bis 180), ein neues Attribut aus der UI fiele still auf den Boden. Vorschlag: Mapping-Tabelle Feldname zu Property statt if-Kaskade. | `mediator/app/semantic/mapping.py` Zeile 66 |
| M6 | `export_anndata` wird von `/selection/generate` aufgerufen und arbeitet auf dem geteilten Proben-Set. `per_project_size` (Zeile 570) bleibt Mengenbegrenzung, die Stratifizierung wird durch die explizite Kohortenliste trivial. | `main.py` Zeile 521 |
| M7 | Eine Identität für beides. Der vorhandene Recipe-Schlüssel (`wrapper.cache.recipes.key_for`, genutzt in Zeile 550) wird zur ID der Auswahl, damit Vorschau, Named Graph und `.h5ad` dieselbe Auswahl bezeichnen. Fachlicher Join-Schlüssel bleibt `db:submitterId`. | `main.py` |

**Später**

| # | Was | Wo |
|---|---|---|
| M8 | `build_obs` kann den GDC-Fallback verlieren, sobald M3 steht: `obs` kommt dann verlässlich aus dem Graphen. Der Punkt, an dem eine Notlösung sauber wegfällt. | `semantic/expression.py`, `build_obs` Zeile 170 |
| M9 | Quellen-Routing vereinheitlichen. Heute wählt `source` nur in `/transform` das Mapping-Modul, GEO, ENA und cBioPortal haben eigene Rohendpunkte, `POST /query` kann nur GDC. Für eine echte Panel-Zeile "Datenquelle" brauchen alle vier denselben Weg, und M3 braucht je Quelle ein Äquivalent zu `extract_sample_case_rows()`. | `main.py` Zeilen 150 bis 388 |
| M10 | `GET /selection/options`, falls die Auswahlwerte später nicht mehr vorgespeichert sein sollen, sondern aus Facetten und Wissensnetz kommen. **Im ersten Durchgang ausdrücklich nicht nötig.** | `main.py` |

## 4 Änderungen in den Wrappern (Julian)

**Erster Durchgang**

| # | Was | Wo |
|---|---|---|
| W1 | Nichts umbauen für M4: `query()`/`search()` reichen die Feldliste generisch durch, live gegen die GDC-API verifiziert. Die Aufgabe ist nur, das zu bestätigen und gegebenenfalls die Feldnamen für die neuen Attribute zu benennen. | `wrappers/gdc/client.py` Zeile 211 |
| W2 | `extract_sample_case_rows()` (Zeile 158) wird von M3 zum zentralen Baustein. Prüfen, ob es alle Felder liefert, die beide Senken brauchen, und gegebenenfalls erweitern. | `wrappers/gdc/client.py` Zeile 158 |

**Später**

| # | Was | Wo |
|---|---|---|
| W3 | **Facetten und Zählungen**: `facets(endpoint, field, filters)` liefert Werte plus Anzahl ohne Nutzdaten (GDC: `facets=<feld>` und `size=0`). Nötig erst für M10 und für die Abstraktion aus Punkt 5. | `wrappers/gdc/client.py`, neben `query` (Zeile 211) |
| W4 | Fallstrick zu W3, bereits verifiziert: ein Filter auf `cases.project.project_id` wirkt zuverlässig, ein Filter auf `cases.diagnoses.primary_diagnosis` lieferte mehrfach stillschweigend **ungefilterte** Facets. Erkennbar daran, dass die Buckets exakt den Projektgrößen entsprechen. Immer gegen `pagination.total` plausibilisieren. | dito |
| W5 | Für die Abstraktion, die nach Labels sucht: `get_schema(endpoint)` (Zeile 321) liefert die Feldliste eines Endpunkts über `_mapping`. Das ist der vorhandene Baustein, um neue Attribute zu entdecken, statt sie vorzuspeichern. | `wrappers/gdc/client.py` Zeile 321 |
| W6 | Modalität 2 und 3. Für Expression existieren `build_expression_filters` (Zeile 133) und `download_expression_files` (Zeile 400). DNA-Methylierung und Mutationen fehlen vollständig, `to_anndata` (Zeile 454) ist bewusst `NotImplementedError`. Ohne das hat die Panel-Zeile `Var` genau einen wählbaren Wert. | `wrappers/gdc/client.py` |
| W7 | Facetten auch für `geo`, `ena`, `cbioportal`, sonst kann die UI die Datenquelle nicht wirklich wechseln. | `wrappers/<quelle>/client.py` |

## 5 Änderungen im Wissensnetz (Marcel)

Nach der Korrektur ist das Wissensnetz im ersten Durchgang **Senke und
Vorschau-Darstellung**, nicht Lieferant für die Oberfläche. Das ist deutlich weniger Arbeit
als in Fassung 1 angenommen.

**Erster Durchgang**

| # | Was | Wo |
|---|---|---|
| K1 | **Named Graph je Auswahl.** `load_turtle(..., graph=…)` kann das schon (`graphstore.py` Zeile 98). Es fehlen die Konvention `http://databridge.hka/graph/selection/<id>` und das Aufräumen per `DROP GRAPH`. Muster existiert beim Rückkanal (`graph_iri_for`, `feedback.py` Zeile 124). | `graphstore.py`, `init.py` |
| K2 | **Vorschau-Lesefunktion.** `all_cases()` liefert heute alles, was im Graphen steht (Zeile 197). Es braucht eine Variante, die auf einen Auswahl-Graphen begrenzt ist, etwa `cases_for_selection(store, selection_id)`. Sie ist gleichzeitig die `obs`-Quelle für M8. | `enrichment.py` Zeile 197 |
| K3 | **CLI erweitern**, damit die Kette ohne Oberfläche testbar bleibt: `wissensnetz preview <selection.json>`. Heute gibt es status, init, load, query, hierarchy, context, feedback, findings. | `cli.py` Zeile 26 ff |
| K4 | Generische Attribute müssen in der TBox deklariert sein, sonst schreibt M5 Tripel gegen undeklarierte Properties. Entweder die TBox vorab um die Attribute erweitern, die im Panel stehen, oder eine bewusste Entscheidung, undeklarierte Properties zuzulassen. | `ontology/databridge-core.ttl` |

**Später**

| # | Was | Wo |
|---|---|---|
| K5 | **Attributkatalog aus der TBox** (`db:`-Properties mit Label und Domain) und **Wertelisten mit Zählung** per SPARQL. Das ist die Wissensnetz-Hälfte von M10, also der Schritt, an dem die vorgespeicherten Attribute durch die Ontologie ersetzt werden. | `enrichment.py` |
| K6 | **NCIt-Alignment und Slim**, sobald "weitere Ebene" semantisch tiefer gehen soll. Ohne Hierarchie im Store ist eine zweite Ebene nur ein zweiter Textfilter. Arbeitsliste liegt bereit. | `ontology/alignment/KANDIDATEN.md` |
| K7 | **MP-lite**, falls der Prototyp die Oberfläche wird: `app.py` liest beim Start alles und baut den Plot sofort. Panel davor, Plot erst nach `Vorschau`. Die datengetriebene Slider-Aktivierung (Zeile 401 ff) passt begrifflich auf das Panel. | `prototype/mp_lite/app.py` |

## 6 Frontend (Zuständigkeit offen)

- Zweispaltiges Fenster, Auswahlpanel rechts, Darstellung links, zwei Schaltflächen unten.
- Vier Panelzeilen, Mehrfachauswahl bei `Krebs` und `Obj`, Schachtelung weiterer Ebenen.
- Zwei Aufrufe gegen den Mediator: `POST /selection/preview` und `POST /selection/generate`.
- Die vorgespeicherten Attribute liegen im ersten Durchgang als Konfiguration vor, zum
  Beispiel als JSON neben dem Frontend. Kein Aufruf ans Wissensnetz nötig.
- Die Oberfläche spricht nur mit dem Mediator, nie direkt mit einem Wrapper. Sonst ist
  ADR-0001 hinfällig.

## 7 Offene Entscheidungen

1. **Frontend-Technologie.** MP-lite erweitern (Bokeh, Python, schnell zu einem Demo) oder
   ein eigenes Frontend gegen die REST-Schnittstelle. Blockiert die Panel-Arbeit.
2. **Bedeutung von "weitere Ebene".** Verfeinerung derselben Auswahl, also ein logisches
   UND, oder mehrere gleichrangige Auswahlen zum Vergleich? Ändert die JSON-Struktur und
   damit M1.
3. **Was macht `Vorschau` genau?** Zwei Möglichkeiten: derselbe geteilte Abruf ohne die
   Matrizen, oder ein reiner Zählschritt ohne Datenabruf. Beim ersten Weg setzt
   `Generieren` auf dem Vorschau-Ergebnis auf, beim zweiten wiederholt es den Abruf.
4. **Wo liegen die vorgespeicherten Attribute?** Konfigurationsdatei beim Frontend
   (einfach, dupliziert Wissen) oder schon jetzt die TBox (K5 vorziehen). Für "erstmal"
   spricht die Konfigurationsdatei.
5. **Werden undeklarierte Properties zugelassen?** Siehe K4.
6. **Modalitätsquelle.** Solange DNA-Methylierung und Mutationen nicht angebunden sind
   (GDC oder UCSC Xena), ist `Var` eine Attrappe mit einem Wert.

## 8 Vorgeschlagene Reihenfolge

1. Entscheidungen 7.1, 7.2 und 7.3. Alle drei sind billig zu treffen und teuer, wenn man
   sie erst nach dem Bau merkt.
2. M1 und M2, die beiden Endpunkte, zunächst mit einer Attrappe als Antwort. Danach kann
   das Frontend parallel starten.
3. M4 und M5, dynamische Felder und generisches Mapping, dazu K4.
4. **M3, der gemeinsame Abrufschritt.** Fachlich der Kern, technisch der größte Eingriff,
   weil er zwei heute getrennte Pfade zusammenlegt.
5. K1 und K2, Auswahl-Graph und Vorschau-Lesefunktion, dazu K3 zum Testen.
6. M6 und M7, Generieren und die gemeinsame ID. Danach M8.
7. Erst dann W3 bis W7 und K5 bis K7, also Facetten, Katalog und weitere Modalitäten.

**Abnahmetest der ganzen Variante, ohne Oberfläche:** ein Auftrag als JSON durchschicken,
danach prüfen, ob `wissensnetz query` und das erzeugte `.h5ad` dieselbe Probenliste nennen.
Stimmen die beiden Listen überein, trägt Punkt 9 aus Abschnitt 1.
