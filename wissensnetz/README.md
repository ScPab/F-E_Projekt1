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
`recherche/Rueckkanal-Konzept_MP-zu-RDF`) und per SPARQL-Update in einen
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

## Python-API

```python
from wissensnetz import GraphStore, initialize
from wissensnetz import subclasses, superclasses, case_context, diagnosis_context
from wissensnetz import SelectionEvent, write_feedback, list_findings

store = GraphStore()          # liest Verbindung aus ENV
initialize(store)             # Dataset + TBox (Aufgabe 1)
store.load_turtle("data/sample/cases_brca_sample.ttl")   # Aufgabe 2
rows = store.query("PREFIX db: <http://databridge.hka/onto#> "
                   "SELECT ?c WHERE { ?c a db:Case }")

# Aufgabe 3 — Anreicherung (reine Lese-Funktionen, strukturierte Rückgabe)
subclasses(store, "db:Case")               # -> ["http://databridge.hka/onto#Case", ...]
ctx = case_context(store, "TCGA-A1-A0SB")  # -> {project_id, gender, diagnoses: [...]}
diagnosis_context(store, "d-11111111")     # -> {label, age_at_diagnosis, case_iri, ...}

# Aufgabe 4 — Rückkanal (Schreiben)
event = SelectionEvent.from_json_file("data/sample/selection_event.json")
graph_iri = write_feedback(store, event)   # schreibt in Named Graph pro Nutzer
list_findings(store, user="nvaldes")       # -> [{annotation, hypothesis, targets, ...}]
```

`load_turtle` überträgt den Turtle-Text **roh** an Fuseki (kein rdflib-
Roundtrip), damit RDF-star-Ausgaben (`<< s p o >>`, Provenienz/Konfidenz aus
dem Mediator) erhalten bleiben — Fuseki hat nativen RDF-star-Support
(siehe [ADR-0002](../docs/adr/0002-graph-db-wahl-offen.md) und CLAUDE.md,
„RDF-star-Falle").

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
    init.py                 # (1) Dataset sicherstellen + TBox + Feedback-Vokabular laden
    enrichment.py           # (3) Lese-Funktionen: Hierarchie + Fall-/Diagnose-Kontext
    feedback.py             # (4) Rückkanal: Event -> oa:Annotation/PROV-O/RDF-star
    cli.py                  # CLI-Einstieg
  ontology/                 # TBox databridge-core.ttl, feedback.ttl + Alignment
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

Damit sind alle drei Richtungen des Wissensnetzes umgesetzt: **① Laden** (ABox
aus dem Mediator), **② Anreichern/Lesen** (SPARQL) und **③ Rückkanal/Schreiben**
(Expertenwissen).
