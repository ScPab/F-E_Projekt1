# Wissensnetz — RDF-Store, SPARQL & Rückkanal

Teilbereich **Wissensnetz** des DataBridge-Projekts: besitzt den RDF-Store
(Apache Jena Fuseki, Service `graph-db`) und seine Lese-/Schreib-Oberfläche.

**Komponentengrenze:** Der Mediator produziert RDF/Turtle, das Wissensnetz
konsumiert es. Die Naht ist RDF/Turtle; kommuniziert wird ausschließlich per
HTTP/SPARQL gegen `graph-db`. Dieses Paket importiert **keinen** Code aus
`mediator/` oder `wrappers/` und baut das GDC→RDF-Mapping **nicht** nach.
Kontext/Regeln: [`CLAUDE.md`](CLAUDE.md), Aufgaben:
[`TASKS_wissensnetz.md`](TASKS_wissensnetz.md).

## Installation

Eigenständiges, installierbares Python-Paket (Muster wie `wrappers/`):

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e ./wissensnetz
```

Konfiguration über Umgebungsvariablen (siehe `.env.example`, Abschnitt
`graph-db`): `GRAPH_DB_URL` (Default `http://localhost:3030`),
`GRAPH_DB_DATASET` (`databridge`), `GRAPH_DB_ADMIN_USER`/`GRAPH_DB_ADMIN_PASSWORD`
(`admin`/`admin`, für Schreibzugriffe).

## End-to-End-Ablauf

```bash
# 1) Store starten (legt das persistente TDB2-Dataset 'databridge' an)
docker compose up -d graph-db

# 2) Dataset sicherstellen + TBox (databridge-core.ttl) laden
wissensnetz init

# 3) Beispiel-ABox laden (eingefrorene Mediator-Ausgabe, s. u.)
wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl

# 4) Abfragen
wissensnetz query "SELECT ?sid ?label WHERE {
  ?c a db:Case ; db:submitterId ?sid ; db:hasDiagnosis ?d .
  ?d db:primaryDiagnosisLabel ?label } ORDER BY ?sid"

# 5) Rückkanal: Erkenntnis schreiben und zurücklesen (Aufgabe 4)
wissensnetz feedback wissensnetz/data/sample/selection_event.json
wissensnetz findings --user nvaldes

# Status jederzeit prüfen:
wissensnetz status
```

Schritt 2 ist **idempotent** (bereits geladene TBox wird übersprungen,
`--force` erzwingt Neuladen). Die Standard-PREFIXE (`db:`, `ncit:`, `prov:`,
`owl:`, `rdfs:`, …) stellt `wissensnetz query` automatisch voran (`--raw`
schaltet das ab).

Die Beispieldaten unter [`data/sample/cases_brca_sample.ttl`](data/sample/cases_brca_sample.ttl)
sind die **eingefrorene Turtle-Ausgabe des Mediators**
(`mediator/scripts/example_gdc_to_rdf.py` bzw. `POST /transform`), nicht selbst
erzeugt — sie dienen als Fixture zum Laden/Abfragen. Alternativ direkt aus dem
Mediator laden:

```bash
# Turtle vom Mediator erzeugen und in den Store laden
python mediator/scripts/example_gdc_to_rdf.py           # schreibt scripts/output/tcga_brca_sample.ttl
wissensnetz load mediator/scripts/output/tcga_brca_sample.ttl
```

## CLI

| Befehl | Zweck |
| --- | --- |
| `wissensnetz status` | Erreichbarkeit, Dataset und TBox prüfen |
| `wissensnetz init [--force]` | Dataset sicherstellen + TBox laden (Aufgabe 1) |
| `wissensnetz load <datei.ttl \| ->` | Turtle laden, `--graph <IRI>` für Named Graph (Aufgabe 2) |
| `wissensnetz query "<SPARQL>"` | SELECT/ASK ausführen, `--raw` ohne PREFIXE (Aufgabe 2) |
| `wissensnetz hierarchy <klasse> [--up] [--no-self]` | Unter- bzw. (`--up`) Oberklassen via `rdfs:subClassOf*` (Aufgabe 3) |
| `wissensnetz context <ref>` | Fall-/Diagnose-Kontext: verknüpfte Konzepte + Alignment-Ziele (Aufgabe 3) |
| `wissensnetz feedback <event.json> [--user <id>]` | MP-Selektions-Event in den Nutzer-Named-Graph schreiben (Aufgabe 4) |
| `wissensnetz findings [--user <id>]` | Gespeicherte Experten-Erkenntnisse auflisten (Aufgabe 4) |
| `wissensnetz selections` | Alle Auswahlen (Named Graphs) auflisten (Aufgabe 13) |
| `wissensnetz selection <id>` | Eine Auswahl samt ihrer Fälle zeigen (Aufgabe 13) |
| `wissensnetz drop-selection <id> [--yes]` | Manifest einer Auswahl verwerfen, Wissensbestand bleibt (Aufgabe 13) |

## Anreicherung (Aufgabe 3)

```bash
# Klassenhierarchie (transitiv, rdfs:subClassOf*)
wissensnetz hierarchy db:Case              # Unterklassen (inkl. Klasse selbst)
wissensnetz hierarchy db:Diagnosis --up    # Oberklassen

# Fall- bzw. Diagnose-Kontext (Case per submitterId oder IRI, Diagnose per Kennung/IRI)
wissensnetz context TCGA-A1-A0SB           # -> Projekt, Geschlecht, Diagnosen
wissensnetz context d-11111111             # -> Label, Alter, zugehöriger Case
```

> **Datenhinweis:** `aligned_concept` (NCIt-Link via `db:primaryDiagnosis`)
> bleibt leer, solange die Alignment-Tabelle
> (`ontology/alignment/ncit_primary_diagnosis.json`) leer ist; die
> Krankheitshierarchie liefert erst dann mehrstufige Ergebnisse, wenn eine
> Hierarchie (z. B. NCIt) in den Store geladen wird. Die Funktionen sind
> generisch und arbeiten dann unverändert.

## Rückkanal (Aufgabe 4)

Expertenwissen aus Morphing Projections zurück ins Netz: ein Selektions-Event
wird als `oa:Annotation`/`db:ExpertFinding` mit PROV-O-Provenienz und
**RDF-star** für die Kern-Aussage modelliert (nach
`recherche/_archiv/Rueckkanal-Konzept_MP-zu-RDF`, zusammengefasst in
`recherche/DataBridge_Stand_und_Ausrichtung.md`, Teil A.3) und per
SPARQL-Update in einen
**Named Graph pro Nutzer** (`http://databridge.hka/graph/user/<id>`) geschrieben.
So bleibt die Kern-TBox/ABox im Default-Graph unberührt und Erkenntnisse sind pro
Nutzer isoliert und widerrufbar (`DROP GRAPH`).

```bash
wissensnetz feedback wissensnetz/data/sample/selection_event.json   # schreibt (Nutzer aus Event)
wissensnetz findings --user nvaldes                                 # liest zurück
```

Kern-Aussage je Probe als RDF-star (Provenienz/Konfidenz direkt an der Aussage):

```turtle
<< db:sample-… db:reclassifiedAs ncit:PanNET >>
    prov:wasDerivedFrom <…/annotation/anno-…> ;
    db:confidence 0.7 .
```

Das Rückkanal-Vokabular (`db:ExpertFinding`, `db:Reclassification`,
`db:hypothesis`, `db:from`/`db:to`, `db:reclassifiedAs`, `db:inView`,
`db:morphParam`, `db:confidence`, `db:tag`) liegt in
[`ontology/feedback.ttl`](ontology/feedback.ttl) und wird von `wissensnetz init`
mitgeladen; `oa:`/`prov:`-Terme werden wiederverwendet.

## Auswahl-Graphen (Aufgabe 13)

Der Store ist **nicht** global vorbefüllt, sondern **wächst mit den Aufrufen**:
jeder `/selection/*`-Aufruf des Mediators schreibt seinen Wissensbestand hinein
(siehe [ADR-0003](../docs/adr/0003-ui-gesteuerte-akquise.md) und
[`HANDOFF_pablo_store_waechst.md`](HANDOFF_pablo_store_waechst.md)). Zwei Ebenen
bleiben dabei getrennt:

| Ebene | Inhalt | Ort | Lebensdauer |
| --- | --- | --- | --- |
| Wissensbestand | Case, Demographic, Diagnosis, Sample, dynamische Properties | **Default-Graph** | wächst, bleibt |
| Auswahl-Manifest | welche Proben und Fälle zur Auswahl gehören, plus die Auswahlparameter | **Named Graph** `http://databridge.hka/graph/selection/<id>` | je Aufruf, verwerfbar |

Läge der Wissensbestand je Auswahl in einem eigenen Named Graph, stünden
dieselben Case-Tripel als Quads mehrfach im Store, und ein `DROP GRAPH` würde
Wissen löschen, das eine andere Auswahl noch braucht.

```bash
wissensnetz selections                 # alle Auswahlen im Store
wissensnetz selection <recipe_key>     # nur die Fälle DIESER Auswahl
wissensnetz query "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a db:Case }"  # weiterhin der ganze Store
wissensnetz drop-selection <recipe_key>   # nur das Manifest, mit Sicherheitsabfrage
```

Genau dieser Unterschied ist der Zweck: `wissensnetz selection <id>` zeigt nur
die Fälle der Auswahl, während `wissensnetz query` den gesamten Store sieht.

Das Auswahl-Vokabular (`db:Selection`, `db:selectionId`, `db:hasMember`,
`db:selectionCase`, `db:selectedCohort`/`-Modality`/`-Attribute`, `db:source`)
liegt in [`ontology/selection.ttl`](ontology/selection.ttl) und wird von
`wissensnetz init` mitgeladen; `prov:`/`rdfs:`-Terme werden wiederverwendet.
`db:hasCase` ist in der Kern-TBox für `db:Project` → `db:Case` belegt, daher
heißt der Fallbezug hier `db:selectionCase`.

**Naht zum Mediator:** `write_selection(...)` ist die Funktion, die der Mediator
aufruft — ihre Signatur ändert sich nicht ohne Absprache. Die Sample-IRIs folgen
derselben Bildungsregel wie das Mediator-Mapping
(`INSTANCE_BASE + "sample/" + _slug(sample_id)`), festgenagelt in
`tests/test_selection.py::test_sample_iri_matches_mediator_rule`.

Die Kette ohne Oberfläche durchspielen (Projektskript, nicht Teil des Pakets):

```bash
python scripts/run_selection.py selection.json            # POST /selection/preview
python scripts/run_selection.py selection.json --generate # POST /selection/generate
```

## Upsert je Property (Aufgabe 14)

Weil der Store mit den Aufrufen wächst, kann derselbe Fall mehrfach geladen
werden. Ändert GDC dazwischen einen Wert, hingen ohne Gegenmaßnahme **zwei**
Werte an derselben Property — `build_obs` und MP-Lite erwarten einen.

`load_knowledge()` löst das als **Upsert je Property**, nicht als „Fall
ersetzen":

> Gelöscht wird nur, was die aktuelle Nutzlast auch schreibt.

Das ist der Unterschied, auf den es ankommt: verschiedene Auswahlen fragen
verschiedene Attributmengen ab. Holt Auswahl A `sex_at_birth` und `tumor_stage`
und Auswahl B danach nur `sex_at_birth`, dann **löscht B das `tumor_stage` von A
nicht**.
Der Store wächst monoton, außer in den Werten, die tatsächlich neu geliefert
werden. „Fall ersetzen" würde ihn dagegen je nach letzter Anfrage schrumpfen
lassen (siehe [`HANDOFF_pablo_P4_ersetzen.md`](HANDOFF_pablo_P4_ersetzen.md)).

```python
from wissensnetz import load_knowledge

load_knowledge(
    store, turtle,
    submitter_ids=[...],   # aus dem geteilten Abruf
    properties=[...],      # db:-Property-IRIs der gewählten Attribute
)
```

Ohne `properties` verhält sich die Funktion wie `store.load_turtle(turtle)`,
also reines Anhängen. Die Zuordnung *Attributname → `db:`-Property* bleibt beim
Mediator (`resolve_attribute`) und kommt als Parameter herein — hier entsteht
bewusst keine zweite Tabelle davon.

Gelöscht wird am Fall **und an seinen Unterknoten** (`db:hasDemographic`,
`db:hasDiagnosis`, `db:hasSample`), denn die Klinikfelder hängen laut TBox nicht
am Case selbst. Enthält die Liste `db:primaryDiagnosisLabel`, gehen der
NCIt-Link `db:primaryDiagnosis` und dessen RDF-star-Provenienz als Anhang mit.

Unberührt bleiben die TBox, die kohortenweit geteilten Projekt-Knoten und alle
Named Graphs (Auswahl-Manifeste, Rückkanal-Graphen). Das ist nicht angenommen,
sondern in `tests/test_knowledge.py` festgenagelt.

## Python-API

```python
from wissensnetz import GraphStore, initialize
from wissensnetz import subclasses, superclasses, case_context, diagnosis_context
from wissensnetz import SelectionEvent, write_feedback, list_findings
from wissensnetz import write_selection, cases_for_selection, list_selections
from wissensnetz import load_knowledge

store = GraphStore()          # liest Verbindung aus ENV
initialize(store)             # Dataset + TBox (Aufgabe 1)
store.load_turtle("data/sample/cases_brca_sample.ttl")   # Aufgabe 2
rows = store.query("PREFIX db: <http://databridge.hka/onto#> "
                   "SELECT ?c WHERE { ?c a db:Case }")

# Aufgabe 3 — Anreicherung (reine Lese-Funktionen, strukturierte Rückgabe)
subclasses(store, "db:Case")               # -> ["http://databridge.hka/onto#Case", ...]
ctx = case_context(store, "TCGA-A1-A0SB")  # -> {project_id, sex_at_birth, diagnoses: [...]}
diagnosis_context(store, "d-11111111")     # -> {label, age_at_diagnosis, case_iri, ...}

# Aufgabe 4 — Rückkanal (Schreiben)
event = SelectionEvent.from_json_file("data/sample/selection_event.json")
graph_iri = write_feedback(store, event)   # schreibt in Named Graph pro Nutzer
list_findings(store, user="nvaldes")       # -> [{annotation, hypothesis, targets, ...}]

# Auswahl (Aufgabe 13) — Manifest schreiben, danach begrenzt lesen
graph_iri = write_selection(
    store, selection_id=recipe_key, source="gdc", cohorts=["TCGA-BRCA"],
    modality="gene_expression", attributes=["sex_at_birth", "tumor_stage"],
    submitter_ids=[...], sample_ids=[...],
)
cases_for_selection(store, recipe_key)     # wie all_cases(), aber nur diese Auswahl
list_selections(store)                     # -> [{selection_id, cohorts, members, ...}]

# Wissensbestand (Aufgabe 14) — Upsert je Property statt reinem Anhängen
load_knowledge(store, turtle, submitter_ids=[...], properties=[...])
```

`load_turtle` überträgt den Turtle-Text **roh** an Fuseki (kein rdflib-
Roundtrip), damit RDF-star-Ausgaben (`<< s p o >>`, Provenienz/Konfidenz aus
dem Mediator) erhalten bleiben — Fuseki hat nativen RDF-star-Support
(siehe [ADR-0002](../docs/adr/0002-graph-db-wahl-offen.md) und CLAUDE.md,
„RDF-star-Falle").

## Achtung: Änderungen hier brauchen einen Mediator-Neubau

`mediator/Dockerfile` kopiert dieses Paket **beim Bauen** ins Image
(`COPY wissensnetz /wissensnetz`, kein Bind-Mount). Der Mediator nutzt es für
`all_cases`/`build_obs`. Eine Änderung an `src/wissensnetz/` wirkt deshalb erst
nach

```powershell
.\start_all.ps1 -RebuildMediator
```

Ohne den Neubau läuft im Container weiter die alte Fassung, während `wissensnetz`
auf dem Host bereits die neue ist — die beiden laufen dann still auseinander.
Genau daran ist die `sex_at_birth`-Umstellung zunächst hängen geblieben: im Store
stand die neue Property, der Container fragte noch die alte ab.

(Die Ontologie unter `ontology/` ist davon ausgenommen, die ist als Bind-Mount
eingebunden und wirkt sofort.)

## Tests

```bash
pip install -e "./wissensnetz[test]"
cd wissensnetz && pytest
```

Die Tests laufen gegen ein **laufendes Fuseki** und decken Laden + Abfragen ab
(Aufgabe 1: TBox-Klassen abfragbar; Aufgabe 2: Beispiel-Cases/Diagnosen). Ist
kein Fuseki erreichbar, werden sie **übersprungen** (kein Fehler) — praktisch
für CI ohne Store.

## Verzeichnisstruktur

```
wissensnetz/
  pyproject.toml            # installierbares Paket "wissensnetz"
  requirements.txt
  README.md                 # dieses Dokument
  src/wissensnetz/
    config.py               # Fuseki-URL, Dataset, Namespaces aus ENV
    graphstore.py           # (2) Fuseki-Client: load_turtle / query / update
    init.py                 # (1) Dataset sicherstellen + TBox + Nebenvokabulare laden
    enrichment.py           # (3) Lese-Funktionen: Hierarchie, Fall-/Diagnose-Kontext,
                            #     all_cases / cases_for_selection
    feedback.py             # (4) Rückkanal: Event -> oa:Annotation/PROV-O/RDF-star
    selection.py            # (13) Auswahl-Manifeste im Named Graph je /selection/*-Aufruf
    knowledge.py            # (14) Upsert je Property beim Laden in den Default-Graph
    cli.py                  # CLI-Einstieg
  ontology/                 # TBox databridge-core.ttl, feedback.ttl, selection.ttl + Alignment
  data/sample/              # Mediator-Turtle-Fixture + selection_event.json
  tests/                    # pytest (Skip ohne laufendes Fuseki)
```

## Stand / Nächste Schritte

- **Aufgabe 1 (Dataset + TBox-Init):** umgesetzt.
- **Aufgabe 2 (Graphstore-Client):** umgesetzt.
- **Aufgabe 3 (SPARQL-Anreicherung, Lesen):** umgesetzt — `enrichment.py`
  (`subclasses`/`superclasses` via `rdfs:subClassOf*`, `case_context`,
  `diagnosis_context`) + CLI `hierarchy`/`context`.
- **Aufgabe 4 (Rückkanal, Schreiben):** umgesetzt — `feedback.py` (MP-Selektions-
  Event → `oa:Annotation`/PROV-O/RDF-star, SPARQL-star-INSERT in Named Graph
  pro Nutzer) + Vokabular `ontology/feedback.ttl` + CLI `feedback`/`findings`.

- **Aufgabe 13 (Auswahl-Graphen, wachsender Store):** umgesetzt —
  `selection.py` (Manifest je Auswahl im Named Graph, `write_selection` als Naht
  zum Mediator, `drop_selection`, `list_selections`),
  `enrichment.cases_for_selection` als begrenztes Gegenstück zu `all_cases`,
  Vokabular `ontology/selection.ttl` + CLI `selections`/`selection`/
  `drop-selection` + Projektskript `scripts/run_selection.py`.

- **Aufgabe 14 (Upsert je Property):** umgesetzt — `knowledge.py`
  (`load_knowledge` als Naht zum Mediator, `replace_case_properties`), inkl.
  Sonderfall NCIt-Alignment (`db:primaryDiagnosis` + RDF-star) und Nachweis,
  dass TBox, Projekt-Knoten und Named Graphs unberührt bleiben.

Damit sind alle drei Richtungen des Wissensnetzes umgesetzt: **① Laden** (ABox
aus dem Mediator), **② Anreichern/Lesen** (SPARQL) und **③ Rückkanal/Schreiben**
(Expertenwissen).
