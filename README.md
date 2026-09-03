# DataBridge (F-E_Projekt1)

DataBridge ist eine Systemarchitektur zur automatisierten Datenintegration
für Visualisierungswerkzeuge im Bereich Onkologie/Genetik. Testfall: Zugriff
auf TCGA-Daten über die GDC Developer API. Die Architektur folgt dem
Mediator-Wrapper-Muster; Zielformat der Datenausgabe ist anndata (`.h5ad`).

Dies ist das **Grundgerüst** (Boilerplate) der Architektur – ohne fertige
Datenintegrationslogik. Diese folgt in späteren Schritten.

## Struktur

- `mediator/` – Zentraler Mediator-Service (Python/FastAPI), nimmt Anfragen
  entgegen und delegiert an Wrapper-Module. Dependency-Management via
  Conda/Mamba (`environment.yml`), u. a. für anndata/scanpy.
- `wrappers/` – Wrapper-Module je Datenquelle (Mediator-Wrapper-Muster):
  `gdc` (GDC Developer API / TCGA), `geo` (Gene Expression Omnibus), `ena`
  (European Nucleotide Archive), `cbioportal`. Liegen als Python-Packages im
  Mediator-Container, siehe
  [ADR-0001](docs/adr/0001-wrapper-als-python-package.md).
- `graph-db/` – Graph-Speicherung: Apache Jena Fuseki/TDB2 (RDF-Triple-Store
  mit OWL, RDF-star für Kanten-Metadaten), Entscheidung getroffen, siehe
  [ADR-0002](docs/adr/0002-graph-db-wahl-offen.md).
- `wissensnetz/` – Semantische Schicht (Ontologie, Mapping-Konzept GDC→RDF/OWL).
  Basis-Ontologie unter `wissensnetz/ontology/`, Mapping-Code im Mediator
  unter `mediator/app/semantic/`, siehe
  [`wissensnetz/ontology/README.md`](wissensnetz/ontology/README.md) und
  [`docs/adding_new_sources.md`](docs/adding_new_sources.md).
- `frontend/` – Leerer Platzhalter-Ordner; Visualisierungsschicht noch
  nicht entschieden, aktuell kein Compose-Service.
- `docs/adr/` – Architecture Decision Records (inkl. Template unter
  `docs/adr/template.md`).
- `memory/` – Projekteigenes, fortlaufend aktualisiertes Gedächtnis
  (aktueller Kontext, offene Punkte), siehe `memory/README.md`.
- `Orga/` – Ablage für organisatorische Themen und Absprachen.
- `recherche/` – Literaturrecherche (Ontologien, Wissensrepräsentation,
  RDF vs. Property Graph) als fachliche Grundlage.

## Starten

1. `.env.example` nach `.env` kopieren und bei Bedarf anpassen.
2. Container bauen und starten:

   ```bash
   docker compose up --build
   ```

3. Health-Check des Mediators prüfen:

   ```bash
   curl http://localhost:8000/health
   # -> {"status": "ok"}
   ```

Der Graph-DB-Platzhalter (Jena Fuseki) ist danach unter
`http://localhost:3030` erreichbar.

### Beispielaufrufe: GDC-Wrapper über den Mediator

Testfall: `TCGA-BRCA`, `RNA-Seq`, `files.access = open`.

```bash
# Metadaten-Suche (Metadaten-Tier, paginiert über size/from)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
        "endpoint": "files",
        "project_id": "TCGA-BRCA",
        "experimental_strategy": "RNA-Seq",
        "fields": ["file_name", "file_id", "access"],
        "size": 5
      }'

# Verfügbare Felder eines Endpunkts (Schema-Introspektion via _mapping)
curl http://localhost:8000/schema/files

# Manifest für gdc-client erzeugen (Bulk-Tier)
curl -X POST http://localhost:8000/manifest \
  -H "Content-Type: application/json" \
  -d '{
        "project_id": "TCGA-BRCA",
        "experimental_strategy": "RNA-Seq",
        "size": 10
      }'
```

Details zur Wrapper-Implementierung (Filter-Aufbau, Cache-Tiers,
`gdc-client`-Anbindung): [`wrappers/gdc/README.md`](wrappers/gdc/README.md).

### Beispielaufrufe: semantische Schicht (GDC → RDF/OWL)

Testfall: TCGA-BRCA-Cases → RDF/OWL-Tripel (Turtle), Kern-Ausschnitt
case/project/demographic/diagnosis. Konzept: [`wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL`](wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL%20-%20Kopie.pdf);
Ontologie: [`wissensnetz/ontology/`](wissensnetz/ontology/).

```bash
# Basis-Ontologie (TBox) zur Inspektion
curl http://localhost:8000/ontology

# GDC-Cases live abrufen und nach RDF/OWL transformieren (nur Turtle-Text)
curl -X POST http://localhost:8000/transform \
  -H "Content-Type: application/json" \
  -d '{"source": "gdc", "project_id": "TCGA-BRCA", "size": 5}'

# Dasselbe, aber zusätzlich direkt in graph-db (Fuseki) schreiben
curl -X POST http://localhost:8000/transform \
  -H "Content-Type: application/json" \
  -d '{"source": "gdc", "project_id": "TCGA-BRCA", "size": 5, "load": true}'
```

Mit `"load": true` schreibt der Mediator das erzeugte Turtle direkt per Graph
Store Protocol in `graph-db` (optional `"graph": "<IRI>"` für einen Named
Graph) — die Antwort enthält dann zusätzlich `"loaded": true`. Ohne `load`
bleibt `/transform` wie bisher eine reine Text-Senke (kein Seiteneffekt);
das Laden erfolgt dann extern, z. B. über
[`scripts/load_gdc.py`](scripts/load_gdc.py) oder `wissensnetz load`.

Ein vollständiges, lokal ausführbares Beispiel mit TCGA-BRCA-Beispieldaten
(ohne laufenden Service) liegt unter
[`mediator/scripts/example_gdc_to_rdf.py`](mediator/scripts/example_gdc_to_rdf.py).

Seit Kurzem unterstützt `/transform` neben `"gdc"` auch `"geo"`, `"ena"` und
`"cbioportal"` (je eigenes Mapping-Modul, teils dieselben `db:`-Klassen wie
GDC wiederverwendet, z. B. für cBioPortal-Klinikdaten). Vollständige
Label-Tabellen je Quelle + Wiederverwendungsprinzip + bekannte Grenzen:
[`mediator/app/semantic/README.md`](mediator/app/semantic/README.md).
Neue Quellen anbinden: [`docs/adding_new_sources.md`](docs/adding_new_sources.md).
