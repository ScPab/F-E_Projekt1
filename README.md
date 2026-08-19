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
- `wrappers/` – Wrapper-Module je Datenquelle (Mediator-Wrapper-Muster).
  Erste Quelle: `wrappers/gdc` (GDC Developer API / TCGA). Liegt als
  Python-Package im Mediator-Container, siehe
  [ADR-0001](docs/adr/0001-wrapper-als-python-package.md).
- `graph-db/` – Austauschbarer Platzhalter für die Graph-Speicherung
  (aktuell Apache Jena Fuseki/TDB2; Wahl zwischen RDF-Triple-Store und
  Property-Graph noch offen, siehe
  [ADR-0002](docs/adr/0002-graph-db-wahl-offen.md)).
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
