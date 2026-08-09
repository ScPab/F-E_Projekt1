# graph-db – Platzhalter für die Graph-Speicherung

Die endgültige Wahl der Graph-Speicherung ist noch offen:

- **RDF-Triple-Store**, z. B. Apache Jena TDB2 (über Fuseki-Server)
- **Property-Graph**, z. B. JanusGraph oder Memgraph

Siehe [`/docs/adr/0002-graph-db-wahl-offen.md`](../docs/adr/0002-graph-db-wahl-offen.md)
für die Abwägung und den aktuellen Stand der Entscheidung.

## Aktueller Platzhalter: Apache Jena Fuseki (TDB2)

`docker-compose.yml` startet aktuell probeweise einen Jena-Fuseki-Container
(offizielles Image, TDB2 als persistentes Backend) unter dem Service-Namen
`graph-db`. Es ist **kein eigener Code** enthalten, nur Konfiguration.

- `init/` – Ablage für künftige Initialisierungs-/Konfigurationsdateien
  (z. B. Fuseki-Dataset-Assembler, initiale Turtle-Dateien). Aktuell leer.

## Austausch gegen eine Property-Graph-DB

Der Service ist bewusst so gehalten, dass er austauschbar bleibt:

1. In `docker-compose.yml` den Service `graph-db` auf ein anderes Image
   umstellen (z. B. `janusgraph/janusgraph` oder `memgraph/memgraph`) und
   Port/Volumes entsprechend anpassen.
2. In `.env.example` / `.env` die Verbindungsparameter anpassen
   (`GRAPH_DB_*`-Variablen).
3. Im Mediator (sobald die Anbindung implementiert wird) die Zugriffsschicht
   austauschen: SPARQL-Client (RDF) vs. Gremlin/Cypher-Treiber (Property
   Graph). Diese Anbindung existiert aktuell noch nicht (Grundgerüst-Phase).

Der Service-Name `graph-db` bleibt bei einem Wechsel unverändert, damit
abhängige Konfiguration (z. B. `.env`) nicht mehrfach angepasst werden muss.
