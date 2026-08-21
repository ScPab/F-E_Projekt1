# Wissensnetz — Arbeitskontext für Claude Code

Diese Datei gilt für Arbeiten im Ordner `wissensnetz/` (Teilbereich Marcel).
Sie beschreibt den **dauerhaften** Kontext und die harten Regeln. Die konkrete,
abzuarbeitende Aufgabenliste steht in `wissensnetz/TASKS_wissensnetz.md`.

## Projektkontext
DataBridge (Master-FuE-Projekt, HS Karlsruhe / Uni Oviedo) koppelt TCGA-Daten
(GDC-API) an die Visualisierungstools der Uni Oviedo (Morphing Projections,
GEM-i). Arbeitsteilung im Team:
- **Wrapper** (`wrappers/gdc/`): GDC-API-Zugriff — FERTIG (Kollege A).
- **Mediator + Konvertierung** (`mediator/`): FastAPI + GDC→RDF-Mapping
  (`app/semantic/mapping.py`, `POST /transform` liefert Turtle-Text),
  anndata (später) — FERTIG/laufend (Kollege B).
- **Wissensnetz** (`wissensnetz/`, MEIN Teil): RDF-Store + SPARQL + Rückkanal.

## Komponentengrenze (strikt)
> Der Mediator produziert RDF/Turtle. Das Wissensnetz besitzt den RDF-Store und
> seine Lese-/Schreib-Oberfläche. Naht = RDF/Turtle. Kommunikation nur über
> HTTP/SPARQL gegen den `graph-db`-Service (Apache Jena Fuseki).

## Harte Regeln
- **Nur unter `wissensnetz/` schreiben.** `mediator/` und `wrappers/` NICHT ändern.
- Kein Import von Code aus `mediator/` oder `wrappers/`
  (Abhängigkeitsrichtung nur Mediator→Wissensnetz, nie umgekehrt).
- **Das GDC→RDF-Mapping NICHT nachbauen** — B besitzt es; wir konsumieren nur
  den fertigen Turtle-Output.
- Kein anndata, kein GDC-API-Zugriff (fremde Teile).
- Eigenständiges, installierbares Python-Paket (Muster wie `wrappers/pyproject.toml`),
  damit der Mediator es später optional per `pip install -e ./wissensnetz` nutzen kann.
- Git-Branch `Wissensnetz` verwenden (auschecken/anlegen, falls nötig), kleine Commits.

## Wo was liegt (zum Verstehen lesen, nicht ändern)
- Ontologie/TBox (unser): `wissensnetz/ontology/databridge-core.ttl`,
  `ontology/alignment/ncit_primary_diagnosis.json`, `ontology/README.md`
  (Namespace `db:` = `http://databridge.hka/onto#`, Instanzen
  `http://databridge.hka/instance/`).
- Turtle-Erzeugung von B (nur als Referenz): `mediator/app/semantic/mapping.py`,
  `mediator/app/main.py` (`/transform`, `/ontology`),
  `mediator/scripts/example_gdc_to_rdf.py`, `mediator/sample_data/cases_brca_sample.json`.
- Konzepte (PDF, in `recherche/`): `Wissensnetz_Gesamtueberblick`,
  `Mapping-Konzept_GDC-zu-RDF-OWL`, `Rueckkanal-Konzept_MP-zu-RDF`.
- Entscheidung Graph-Modell: `docs/adr/0002-graph-db-wahl-offen.md` (RDF/OWL + RDF-star).
- Infrastruktur: `docker-compose.yml` (Service `graph-db`), `.env.example`, `graph-db/README.md`.

## Technik & Fuseki-Konfiguration
- `rdflib` (Graph bauen/serialisieren) + `requests`/`SPARQLWrapper` für Fuseki-HTTP
  (SPARQL Query, SPARQL Update, Graph Store Protocol).
- Fuseki (`graph-db`): lokal `http://localhost:3030`, in Compose `http://graph-db:3030`;
  Dataset `databridge` (ENV `GRAPH_DB_DATASET`), Admin-Passwort `admin`.
  Konfiguration über ENV lesen (Muster wie `.env.example`).
- **RDF-star-Falle:** `serialize_with_provenance` hängt `<< s p o >>`-Blöcke als
  Text an — das ist KEIN gültiges Turtle 1.1; rdflib parst es je nach Version nicht.
  Solche Ausgaben direkt in Fuseki laden (nativer RDF-star-Support, ADR-0002) bzw.
  für den Rückkanal SPARQL-star-INSERT nutzen; verifizieren, dass die Aussagen
  wieder abfragbar sind.
