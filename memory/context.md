# Projektkontext DataBridge

Stand: 2026-08-09

## Ziel

Konzeption und prototypische Umsetzung einer Systemarchitektur zur
automatisierten Datenintegration für Visualisierungswerkzeuge im Bereich
Onkologie/Genetik (Kooperation Hochschule Karlsruhe / Universität Oviedo,
26ss_CB_DataBridge). Testfall: TCGA-Daten über die GDC Developer API.
Fokus: Flexibilität gegenüber sich entwickelnden Datenstrukturen/Ontologien.

## Architektur (Grundgerüst, Stand siehe /docs/adr)

- **Muster:** Mediator-Wrapper. Zentraler Mediator-Service (Python/FastAPI,
  `/mediator`) nimmt Anfragen entgegen; Wrapper-Module je Datenquelle
  (`/wrappers`, erste Quelle: `gdc`).
- **Wrapper-Platzierung:** als Python-Package im Mediator-Container, nicht
  als eigener Docker-Service — siehe [ADR-0001](../docs/adr/0001-wrapper-als-python-package.md).
- **Zielformat der Ausgabe:** anndata (`.h5ad`).
- **Graph-Speicherung:** entschieden für RDF-Triple-Store mit OWL (Apache
  Jena Fuseki/TDB2), Kanten-Metadaten via RDF-star; Property-Graph und
  hybrides Modell verworfen — siehe
  [ADR-0002](../docs/adr/0002-graph-db-wahl-offen.md) (Status: Angenommen,
  2026-08-15).
- **Frontend/Visualisierung:** noch nicht entschieden, aktuell nur leerer
  Platzhalter-Ordner `/frontend`, kein Compose-Service.
- **Orchestrierung:** Docker Compose; Python-Service intern über
  Conda/Mamba (`mediator/environment.yml`) für wissenschaftliche Pakete
  (anndata, scanpy).

## Offene Punkte

- Wahl der Frontend-/Visualisierungstechnologie.
<<<<<<< HEAD
- Ontologie-/Schema-Design des Wissensnetzes (Konzepte, Relationen,
  Wiederverwendung von Bio-Ontologien wie GO/NCIt/DO/SO).
- Semantic-ETL-Mapping GDC-Schema (YAML/JSON) → RDF/OWL sowie Übergabeformat
  zwischen GDC-Wrapper (API-Teil) und Wissensnetz.
- Konkrete Abfrage-/Transformationslogik im GDC-Wrapper (`wrappers/gdc`)
  sowie Anbindung Mediator ↔ graph-db (bislang nicht implementiert, nur
  Grundgerüst).
=======
- Anbindung Mediator ↔ graph-db (bislang nicht implementiert).
- Ontologie-/Mapping-Schicht: `GDCWrapper.get_schema()` liefert GDC-Rohfelder,
  `query`/`search` geben Ergebnisse noch mit GDC-Originalfeldnamen zurück —
  Übersetzung in ein einheitliches internes Schema ist noch offen (siehe
  Docstring in `wrappers/gdc/client.py`).
- Cache-Tiers 2 (materialisierte anndata-Objekte) und 3 (transiente
  Rohdaten) haben nur ein Datei-Grundgerüst (`wrappers/gdc/cache.py`); echte
  Nutzung folgt erst mit der anndata-Transformation bzw. dem
  `gdc-client`-Bulk-Download.

## Umgesetzt seit letztem Stand (2026-08-19)

- Abfrage-/Schema-Introspektionslogik im GDC-Wrapper implementiert
  (`GDCWrapper.query/search/get_schema/build_manifest`,
  `wrappers/gdc/client.py`) und live gegen die echte GDC-API verifiziert
  (Testfall TCGA-BRCA/RNA-Seq/open).
- Mediator exponiert dies über REST (`POST /query`, `GET /schema/{endpoint}`,
  `POST /manifest`, `mediator/app/main.py`) — weiterhin als Python-Package im
  Mediator-Container gemäß ADR-0001, kein eigener `wrapper-gdc`-Service.
- Datei-basiertes Cache-Grundgerüst für die drei Cache-Tiers
  (`wrappers/gdc/cache.py`, Verzeichnis über `DATABRIDGE_CACHE_DIR`).
>>>>>>> 7c7a87c1384af8888f1272294a697d20faf5613f

## Verweise

- Architekturentscheidungen: `/docs/adr`
- Literaturrecherche (Ontologien, RDF vs. Property Graph): `/recherche`
- Organisatorisches: `/Orga`
