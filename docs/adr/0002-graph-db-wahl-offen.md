# ADR-0002: Wahl der Graph-Speicherung (RDF-Triple-Store vs. Property-Graph)

**Status:** Vorgeschlagen (offen)
**Datum:** 2026-08-09

## Kontext

DataBridge soll Daten aus öffentlichen Repositorien (Testfall: GDC/TCGA) für
Visualisierungswerkzeuge im Bereich Onkologie/Genetik aufbereiten. Für die
Graph-Speicherung stehen zwei grundlegende Modelle zur Diskussion (siehe auch
`recherche/DataBridge_Literaturrecherche.md`, Teil 2):

- **RDF-Triple-Store** (z. B. Apache Jena TDB2) – Subjekt-Prädikat-Objekt-
  Tripel, W3C-Standardstack (RDFS/OWL/SPARQL), formale Semantik/Reasoning,
  Stärke bei Ontologie-Integration und Interoperabilität.
- **Property-Graph** (z. B. JanusGraph, Memgraph) – Knoten/Kanten mit
  direkt angehefteten Properties, Abfragesprachen wie Cypher/Gremlin/GQL,
  Stärke bei Performance und intuitiver Modellierung großer, sich häufig
  ändernder Datenmengen.

Ein zentrales Projektziel ist Flexibilität gegenüber sich entwickelnden
Datenstrukturen/Ontologien – dies spricht tendenziell für RDF/OWL (formale
Versionierung, Ontology Alignment), während Property Graphs bei schneller
struktureller Anpassung ohne strikte Schemabindung Vorteile bieten. Auch ein
hybrides Modell ist denkbar.

## Entscheidung

**Noch offen.** Um die Architektur nicht zu blockieren, wird im Grundgerüst
ein austauschbarer Platzhalter-Service `graph-db` verwendet (aktuell: Jena
Fuseki/TDB2 als Default, siehe `docker-compose.yml` und
`graph-db/README.md`). Die finale Entscheidung wird in einer Aktualisierung
dieses ADRs (Status → „Angenommen") festgehalten, sobald die Abwägung
(insb. Reasoning-Bedarf vs. Analytics-/Performance-Anforderungen der
Visualisierungsschicht) abgeschlossen ist.

## Betrachtete Alternativen

- RDF-Triple-Store (z. B. Apache Jena TDB2)
- Property-Graph (z. B. JanusGraph oder Memgraph)
- Hybrides Modell (z. B. RDF als Ontologie-/Integrationsschicht, Property
  Graph als Analytics-/Abfrageschicht) – bislang nicht vertieft untersucht

## Konsequenzen

- Der Mediator darf bis zur endgültigen Entscheidung keine feste Kopplung
  an eine SPARQL- oder Cypher/Gremlin-spezifische Zugriffsschicht
  eingehen; eine solche Anbindung ist im aktuellen Grundgerüst noch nicht
  implementiert.
- Der Service-Name `graph-db` bleibt bei einem späteren Wechsel stabil,
  damit Konfiguration (`.env`) nicht mehrfach angepasst werden muss.
