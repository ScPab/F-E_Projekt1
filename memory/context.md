# Projektkontext DataBridge

Stand: 2026-08-28

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
- **Zielformat der Ausgabe:** anndata (`.h5ad`) für Messmatrizen, RDF/OWL
  (Turtle) für die semantische Schicht (Wissensnetz).
- **Graph-Speicherung:** entschieden für RDF-Triple-Store mit OWL (Apache
  Jena Fuseki/TDB2), Kanten-Metadaten via RDF-star; Property-Graph und
  hybrides Modell verworfen — siehe
  [ADR-0002](../docs/adr/0002-graph-db-wahl-offen.md) (Status: Angenommen,
  2026-08-15).
- **Wissensnetz/Semantic ETL:** Teilbereich von Marcel, siehe
  `wissensnetz/Wissensnetz_Konzept-Entwurf` (übergeordnetes Konzept) und
  `wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL` (konkretes GDC→RDF-Mapping).
  Ontologie unter `wissensnetz/ontology/`, Mapping-Code unter
  `mediator/app/semantic/`.
- **Frontend/Visualisierung:** noch nicht entschieden, aktuell nur leerer
  Platzhalter-Ordner `/frontend`, kein Compose-Service.
- **Orchestrierung:** Docker Compose; Python-Service intern über
  Conda/Mamba (`mediator/environment.yml`) für wissenschaftliche Pakete
  (anndata, scanpy, rdflib).

## Offene Punkte

- Mediator-Anbindung für die drei neuen Wrapper `geo`/`ena`/`cbioportal`
  (Routing analog zu `/query`, `/schema/{endpoint}` für `gdc` in
  `mediator/app/main.py`) — noch offen.
- Mediator muss die 7 neuen klinischen GDC-Felder + `sample_type` auf die
  bereits deklarierten `db:`-Properties mappen (`TRANSFORM_CASE_FIELDS` in
  `mediator/app/main.py`, `cases_to_graph` in
  `mediator/app/semantic/mapping.py`); danach `cases_brca_sample.ttl`
  neu ziehen. Siehe `wissensnetz/prototype/mp_lite/HANDOFF.md` Teil 1/2.
- Team-Entscheidung Expressionsdaten (Graph vs. h5ad-Seitenkanal) für die
  Morphing-Slider `genes`/`miRNA`/Einzelmarker — siehe HANDOFF.md Teil 3.
- Wahl der Frontend-/Visualisierungstechnologie.
- Ontologie-/Schema-Design des Wissensnetzes über den jetzigen Kern-Ausschnitt
  hinaus (weitere GDC-Nodes, Wiederverwendung von GO/SO neben NCIt/DO).
- Alignment-Tabellen (`wissensnetz/ontology/alignment/`) sind noch leer —
  Befüllung mit verifizierten NCIt-/DO-Codes ist offener nächster Schritt
  (Wissensnetz-Teilbereich, Marcel).
- Cache-Tiers 2 (materialisierte anndata-Objekte) und 3 (transiente
  Rohdaten) haben nur ein Datei-Grundgerüst (`wrappers/gdc/cache.py`); echte
  Nutzung folgt erst mit der anndata-Transformation bzw. dem
  `gdc-client`-Bulk-Download.
- Global-as-View reicht für die aktuell einzige Quelle (GDC); bei weiteren
  Quellen ggf. Local-as-View-Formalisierung prüfen (siehe Mapping-Konzept).

## Umgesetzt seit letztem Stand (2026-08-28)

- Drei neue Wrapper analog zu `wrappers/gdc` (Julian): `wrappers/geo`,
  `wrappers/ena`, `wrappers/cbioportal` — je eigenständiges Python-Unterpaket
  gemäß ADR-0001, mit Metadaten-Suche, Schema-Introspektion und
  Bulk-Tier-Äquivalent; live gegen die echten APIs verifiziert. `to_anndata`
  bewusst `NotImplementedError` (außerhalb Wrapper-Scope). **Noch nicht an
  den Mediator angebunden** (kein `/query`/`/schema`-Routing in
  `mediator/app/main.py` für diese drei Quellen).
- Pytest-Unit-Tests für `wrappers/gdc` ergänzt (gemocktes `requests`,
  kein Netzwerkzugriff): `build_filters`, `query`/`search`-Pagination,
  `get_schema`, Fehlerfälle (HTTP-Fehler, unbekannter Endpunkt).
- Wissensnetz-Seite (Marcel) hat MP-lite in mehreren Schritten an das
  Original-Tool von Oviedo angeglichen (Aufgaben 5–8, siehe
  `wissensnetz/TASKS_aufgabe5.md` bis `_aufgabe8.md`): Hover mit voller
  Oviedo-Feldliste, Multi-Variablen-Morphing (ein Slider pro Variable,
  clientseitig), alle 32 TCGA-Kohorten (Pancancer) über `scripts/load_gdc.py
  --pancancer`, sowie ein `db:Sample`-Modell für das Feld `type`
  (`sample_type`). Offene Gegenstücke dazu sind in
  `wissensnetz/prototype/mp_lite/HANDOFF.md` present: Mediator muss die
  neuen klinischen Felder (race/ethnicity/vital_status/tumor_stage/
  morphology/site_of_resection_or_biopsy/has_metastasis/sample_type) auf die
  bereits deklarierten `db:`-Properties mappen (Pablo) — Wrapper-seitig
  (Julian) ist das bereits möglich, siehe unten.
- GDC-Wrapper-seitige Prüfung für HANDOFF Teil 1a (Julian): live gegen die
  echte GDC-API verifiziert, dass `GDCWrapper.query()`/`.search()` die 7
  angeforderten klinischen Felder (`demographic.race/ethnicity/vital_status`,
  `diagnoses.morphology/site_of_resection_or_biopsy/
  ajcc_pathologic_stage/metastasis_at_diagnosis`) unverändert unterstützen —
  der `fields`-Parameter wird generisch durchgereicht, kein Wrapper-Code
  nötig. `diagnoses.tumor_stage` existiert im aktuellen GDC-Schema **nicht**
  (stattdessen `ajcc_pathologic_stage` verwenden).

## Umgesetzt seit letztem Stand (2026-08-24)

- Direkte Anbindung Mediator → graph-db: `POST /transform` akzeptiert
  `load: true` (optional `graph: <IRI>`) und schreibt das erzeugte Turtle
  dann direkt per Graph Store Protocol in Fuseki (`wissensnetz.GraphStore.
  load_turtle`), statt es nur als Text zurückzugeben. Dazu installiert der
  Mediator das `wissensnetz`-Package (`mediator/environment.yml`,
  `mediator/Dockerfile`: `-e /wissensnetz`); in `docker-compose.yml` zeigt
  `GRAPH_DB_URL` beim Mediator-Service fest auf `http://graph-db:3030`
  (Compose-internes Netzwerk statt host-seitigem `GRAPH_DB_PORT`).
  Abhängigkeitsrichtung bleibt Mediator → Wissensnetz, wie in
  `wissensnetz/pyproject.toml` von Anfang an vorgesehen. `scripts/load_gdc.py`
  (zweistufiger externer Weg: Turtle abrufen, dann `GraphStore.load_turtle`)
  bleibt als Alternative bestehen, z. B. für lokale Mediator-Läufe ohne
  Docker/GRAPH_DB_URL-Override.

## Umgesetzt seit vorletztem Stand (2026-08-20)

- Semantische Mapping-Ebene GDC → RDF/OWL für den Kern-Ausschnitt
  case/project/demographic/diagnosis, aufbauend auf Marcels
  Wissensnetz-Konzept (`wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL`,
  `wissensnetz/Wissensnetz_Konzept-Entwurf`): Pro-Node-Klassen
  (`db:Case`/`db:Project`/`db:Demographic`/`db:Diagnosis`, Namespace
  `http://databridge.hka/onto#`) statt abstrahierter Klassen, RDF-star für
  Provenienz/Konfidenz von Alignment-Aussagen (passend zu ADR-0002).
- Basis-Ontologie (TBox) unter `wissensnetz/ontology/databridge-core.ttl`,
  Alignment-Gerüst unter `wissensnetz/ontology/alignment/` (bewusst leer,
  keine ungeprüften NCIt-Codes committet).
- Mapping-Code als reines Python/`rdflib` (`mediator/app/semantic/mapping.py`)
  — kein RML/Java-Unterbau, passt zum bestehenden Conda/Mamba-Stack.
- Mediator exponiert dies über `POST /transform` (GDC-Cases → Turtle) und
  `GET /ontology` (TBox-Inspektion), `mediator/app/main.py`.
- End-to-End-Beispiel mit TCGA-BRCA-Beispieldaten:
  `mediator/sample_data/cases_brca_sample.json`,
  `mediator/scripts/example_gdc_to_rdf.py`.
- Anleitung für neue Quellen: `docs/adding_new_sources.md`.

## Umgesetzt davor (2026-08-19)

- Abfrage-/Schema-Introspektionslogik im GDC-Wrapper implementiert
  (`GDCWrapper.query/search/get_schema/build_manifest`,
  `wrappers/gdc/client.py`) und live gegen die echte GDC-API verifiziert
  (Testfall TCGA-BRCA/RNA-Seq/open).
- Mediator exponiert dies über REST (`POST /query`, `GET /schema/{endpoint}`,
  `POST /manifest`, `mediator/app/main.py`) — weiterhin als Python-Package im
  Mediator-Container gemäß ADR-0001, kein eigener `wrapper-gdc`-Service.
- Datei-basiertes Cache-Grundgerüst für die drei Cache-Tiers
  (`wrappers/gdc/cache.py`, Verzeichnis über `DATABRIDGE_CACHE_DIR`).

## Verweise

- Architekturentscheidungen: `/docs/adr`
- Literaturrecherche (Ontologien, RDF vs. Property Graph): `/recherche`
- Organisatorisches: `/Orga`
