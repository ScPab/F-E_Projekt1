# ADR-0002: Wahl der Graph-Speicherung (RDF-Triple-Store vs. Property-Graph)

**Status:** Angenommen
**Datum:** 2026-08-15 (ersetzt den offenen Stand vom 2026-08-09)

> Hinweis: Der Dateiname endet weiterhin auf `-wahl-offen`, um bestehende
> Querverweise (README, `memory/context.md`, `graph-db/README.md`) nicht zu
> brechen. Der Inhalt ist nun eine getroffene Entscheidung.

## Kontext

DataBridge soll Daten aus öffentlichen Repositorien (Testfall: GDC/TCGA) für
Visualisierungswerkzeuge im Bereich Onkologie/Genetik aufbereiten. Für die
Graph-Speicherung standen zwei grundlegende Modelle zur Diskussion (siehe auch
`recherche/DataBridge_Literaturrecherche.md`, Teil 2):

- **RDF-Triple-Store** (z. B. Apache Jena TDB2) – Subjekt-Prädikat-Objekt-
  Tripel, W3C-Standardstack (RDFS/OWL/SPARQL), formale Semantik/Reasoning,
  Stärke bei Ontologie-Integration und Interoperabilität.
- **Property-Graph** (z. B. JanusGraph, Memgraph, Neo4j) – Knoten/Kanten mit
  direkt angehefteten Properties, Abfragesprachen wie Cypher/Gremlin/GQL,
  Stärke bei Performance und intuitiver Modellierung großer, sich häufig
  ändernder Datenmengen.

### Entscheidungskriterien (aus Aufgabenstellung und Projektunterlagen)

Die Kriterien sind projektspezifisch gewichtet, nicht allgemein:

1. **Interoperabilität mit vorhandenen Bio-Ontologien.** Die relevanten
   Fachontologien (Gene Ontology, Sequence Ontology, NCI Thesaurus, Disease
   Ontology, HPO) liegen nativ als OWL/OBO vor. Sie lassen sich in einem
   RDF/OWL-Store direkt importieren und per `owl:sameAs`/Alignment verknüpfen;
   in einem Property-Graph müssten sie verlustbehaftet konvertiert werden.
2. **Flexibilität gegenüber sich entwickelnden Ontologien** (das erklärte
   Kernziel des Projekts). Ontology Versioning, Alignment und Merging sind im
   RDF/OWL-Umfeld etablierte, werkzeuggestützte Verfahren (Protégé, OWL API).
3. **Formale Semantik / Reasoning** für die semantische Anreicherung der
   Visualisierung (Ableiten impliziter Beziehungen zwischen Gen, Protein,
   Krankheit). Nur RDF/OWL bietet hier standardisierte Description-Logic-
   Semantik.
4. **Kanten-Metadaten** (Provenance, Konfidenz, Studienquelle je Beziehung,
   z. B. „Mutation X assoziiert mit Krebsart Y – Quelle: Studie Z"). Klassisch
   die Stärke der Property Graphs; mit **RDF-star** (RDF 1.2/SPARQL 1.2, W3C
   Candidate Recommendations seit April 2026) nun aber auch in RDF ergonomisch
   abbildbar.
5. **Knowledge Transfer / dynamische Manipulation zur Laufzeit** (SNQL-artiges
   Zurückschreiben von Expertenwissen in die A-Box). Erfordert schreibfähigen
   Zugriff; via `SPARQL Update` und benannte Graphen umsetzbar, die formale
   TBox/ABox-Trennung von OWL passt hier begrifflich exakt.
6. **FAIR-Prinzipien** (Findable, Accessible, Interoperable, Reusable) als
   Bezugsrahmen der automatisierten Datenakquise – RDF/Linked Data ist der
   kanonische, standardnahe Weg.
7. **Analytics-/Traversierungs-Performance auf großen Messmatrizen.** Klassisch
   die Stärke der Property Graphs – für DataBridge aber **entlastet**, weil die
   eigentlichen Genexpressionsmatrizen nach `anndata`/`.h5ad` exportiert und
   dort (Scanpy) analysiert werden, **nicht** im Graphen liegen. Der Graph
   trägt Konzepte, Relationen und Metadaten, keine Millionen Messwerte.

## Entscheidung

**Gewählt: RDF-Triple-Store mit OWL (Apache Jena Fuseki / TDB2), unter Nutzung
von RDF-star für Kanten-Metadaten.**

Ausschlaggebend ist die Kombination aus (1) nativer Interoperabilität mit den
OWL/OBO-Bio-Ontologien, (2) werkzeuggestützter Ontologie-Evolution als
erklärtem Projektkern, (3) formaler Semantik für die semantische Anreicherung
und (5) der begrifflich passenden TBox/ABox-Trennung für den Knowledge-Transfer.
Die zwei traditionellen Property-Graph-Vorteile wiegen hier gering: Kanten-
Metadaten löst RDF-star (4), und die Analytics-Last liegt ausgelagert in
anndata, nicht im Graphen (7).

Die Entscheidung bestätigt zugleich den bisherigen Platzhalter (Jena
Fuseki/TDB2) – es entsteht kein Infrastruktur-Wechsel. Der Service-Name
`graph-db` in `docker-compose.yml` bleibt unverändert.

## Betrachtete Alternativen

- **Property-Graph (Neo4j/JanusGraph/Memgraph).** Verworfen: Bio-Ontologien
  müssten konvertiert werden, keine standardisierte formale Semantik/Reasoning,
  keine formale TBox/ABox-Trennung. Vorteile (Kanten-Properties, schnelle
  Traversierung) für diesen Anwendungsfall nicht ausschlaggebend (RDF-star bzw.
  anndata-Auslagerung).
- **Hybrides Modell** (RDF als Ontologie-/Integrationsschicht, Property Graph
  als Analytics-Schicht). Konzeptionell attraktiv, aber verdoppelt den
  Betriebs- und Synchronisationsaufwand; die verlustfreie RDF↔PG-Transformation
  ist ein offenes Forschungsfeld. Für den Rahmen eines FuE-Projekts über ein
  Semester zu aufwändig – bleibt als dokumentierte Ausbau-Option für später.

## Konsequenzen

- Der Mediator bindet die Zugriffsschicht an **SPARQL** (Abfrage) und
  **SPARQL Update** (Schreiben/Knowledge-Transfer); keine Cypher/Gremlin-
  Kopplung. Update (2026-08-24): Die Schreib-Anbindung ist umgesetzt — `POST
  /transform` schreibt bei `load: true` direkt per Graph Store Protocol in
  `graph-db` (`mediator/app/main.py`, unter Nutzung von
  `wissensnetz.GraphStore`, siehe `memory/context.md`).
- **Tooling** für den Wissensnetz-Workstream: `rdflib` (Python, passt zum
  FastAPI-Mediator) für ETL/Serialisierung; Apache Jena/Fuseki als Store und
  SPARQL-Endpoint; Protégé + OWL API für Ontologie-Design und -Evolution.
- Kanten-Metadaten (Provenance/Konfidenz/Version) werden über **RDF-star**
  modelliert statt über klassische Reifikation. Jena unterstützt RDF-star in
  Fuseki und TDB2 standardmäßig.
- Der `anndata`-Export bleibt die numerische Analyseschicht und wird **nicht**
  durch den Graphen ersetzt; Graph und anndata sind komplementär (Semantik +
  Metadaten vs. Messmatrix).
- **Revidieren, falls** die Visualisierungs-/Analytics-Schicht später doch
  große graph-native Traversierungs-Workloads (Pfadsuche, Community Detection
  über Millionen Kanten) direkt auf dem Wissensnetz verlangt – aktuell
  unwahrscheinlich, da diese Daten in anndata liegen.

## Quellen

- W3C: RDF 1.2 / SPARQL 1.2 Working Group – Candidate Recommendations
  (April 2026), <https://www.w3.org/TR/sparql12-query/>
- Apache Jena – Support of RDF-star,
  <https://jena.apache.org/documentation/rdf-star/>
- Apache Jena – TDB2, <https://jena.apache.org/documentation/tdb2/>
- `recherche/DataBridge_Literaturrecherche.md`, Teil 2 (RDF/OWL vs.
  Property Graph)
