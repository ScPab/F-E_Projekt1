# graph-db – Platzhalter für die Graph-Speicherung

Die endgültige Wahl der Graph-Speicherung ist noch offen:

- **RDF-Triple-Store**, z. B. Apache Jena TDB2 (über Fuseki-Server)
- **Property-Graph**, z. B. JanusGraph oder Memgraph

Siehe [`/docs/adr/0002-graph-db-wahl-offen.md`](../docs/adr/0002-graph-db-wahl-offen.md)
für die Abwägung und den aktuellen Stand der Entscheidung.

## Aktueller Platzhalter: Apache Jena Fuseki (TDB2)

`docker-compose.yml` startet aktuell probeweise einen Jena-Fuseki-Container
(offizielles Image, TDB2 als persistentes Backend) unter dem Service-Namen
`graph-db`. Es ist **kein eigener Code** enthalten, nur Konfiguration — dieser
Ordner enthält ausschließlich dieses README.

Früher lag hier ein leerer Ordner `init/`, gedacht als Ablage für einen
Fuseki-Dataset-Assembler und als `./graph-db/init:/init:ro` in den Container
gemountet. Beides ist entfallen: für die Dataset-Anlage wurde der ENV-Weg
gewählt (siehe unten), der Mount zeigte nicht auf Fusekis
Konfigurationsverzeichnis, und nichts im Projekt hat `/init` je gelesen.

## Dataset-Initialisierung (Wissensnetz)

Gewählter Weg, passend zum `stain/jena-fuseki`-Image: **Dataset per ENV-Variable
beim Container-Start, TBox anschließend per `wissensnetz init`.**

1. **Dataset anlegen** — `docker-compose.yml` setzt im `graph-db`-Service
   `FUSEKI_DATASET_1=${GRAPH_DB_DATASET:-databridge}`. Das Image legt daraus
   beim Start ein **persistentes TDB2-Dataset** an (`TDB=2`); der generierte
   Assembler landet unter `/fuseki/configuration/databridge.ttl`, die Daten
   unter `/fuseki/databases/databridge` — beides im benannten Volume
   `graph-db-data`, also über Container-Neustarts hinweg persistent. Nach
   `docker compose up graph-db` existiert das Dataset unter
   `http://localhost:3030/databridge`.

2. **TBox laden** — die Ontologie `wissensnetz/ontology/databridge-core.ttl`
   wird nicht vom Container, sondern vom Wissensnetz-Client geladen (idempotent,
   über SPARQL/Graph Store Protocol):

   ```
   pip install -e ./wissensnetz
   wissensnetz init          # Dataset sicherstellen + TBox laden
   ```

   `wissensnetz init` legt das Dataset zusätzlich über die Fuseki-Admin-API an,
   falls es fehlt — der Schritt funktioniert also auch, wenn der Container ohne
   `FUSEKI_DATASET_1` gestartet wurde.

Der End-to-End-Ablauf (up → init → load → query → feedback) ist in
[`../wissensnetz/README.md`](../wissensnetz/README.md) beschrieben.

**Zugriffsschutz:** Die `shiro.ini` des Images (nicht in diesem Repo) erlaubt
SPARQL-*Query* anonym,
verlangt für SPARQL-*Update* und Graph Store Protocol (`/*/update`, `/*/data`)
sowie die Admin-API (`/$/`) aber Basic-Auth (`admin`/`admin`). Der
Wissensnetz-Client sendet die Admin-Credentials für Schreibzugriffe automatisch
(konfigurierbar über `GRAPH_DB_ADMIN_PASSWORD`).

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
