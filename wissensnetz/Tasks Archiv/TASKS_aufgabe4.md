# Aufgabe 4 (nur): Rückkanal — Expertenwissen zurück ins Wissensnetz

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich Aufgabe 4** aus `wissensnetz/TASKS_wissensnetz.md` um.
Aufgabe 1–3 sind fertig (config/graphstore/init/enrichment/cli + Tests, auf `main`);
du baust darauf auf, ohne sie zu ändern. Branch `Wissensnetz`, kleine Commits.

Fachliche Grundlage: `recherche/Rueckkanal-Konzept_MP-zu-RDF` (Methoden, Beispiel).
Kurzfassung der Empfehlung dort: Interaktions-Event → `oa:Annotation` mit
PROV-O-Provenienz und **RDF-star** für die Kern-Aussage, geschrieben per
SPARQL-Update in einen **Named Graph pro Nutzer**.

## Worauf du aufbaust (vorhandener Code, nicht neu erfinden)
- `src/wissensnetz/graphstore.py` — `GraphStore.update(sparql)` (SPARQL Update mit
  Admin-Auth), `query()`, `ask()`, `load_turtle(text_or_path, graph=…)`. Nutze das.
- `src/wissensnetz/config.py` — `Settings`, `PREFIXES` (enthält bereits `db:`,
  `ncit:`, `prov:`, `oa:`, `owl:`, `rdfs:`, `xsd:`) und Namespace-Konstanten
  `DB`, `INSTANCE`, `NCIT`, `PROV`, `OA`. Verwende diese Prefixe/IRIs.
- `src/wissensnetz/cli.py` — bestehendes argparse-Muster (status/init/load/query/
  hierarchy/context); hier neue Unterbefehle ergänzen.
- `tests/conftest.py` — Fixtures `store`/`loaded_store` (Skip ohne Fuseki).
  Test-Isolation: eigener Named Graph + `DROP GRAPH` im `finally`
  (siehe `tests/test_graphstore.py::test_load_turtle_into_named_graph`).

## Wichtige technische Hinweise (RDF-star / Named Graph)
- **RDF-star bevorzugt per SPARQL-star-Update erzeugen**, nicht über rdflib
  serialisieren (rdflib-Turtle-star ist versionsabhängig; Fuseki unterstützt
  SPARQL-star nativ, siehe ADR-0002). Also: `feedback.py` baut einen
  `INSERT DATA { GRAPH <g> { … } }`-String (inkl. `<< s p o >>`-Aussage) und
  ruft `graphstore.update()`.
- **Named Graph pro Nutzer:** ein konfigurierbares IRI-Schema, z. B.
  `http://databridge.hka/graph/user/<slug>`. So bleibt die Kern-TBox/ABox im
  Default-Graph sauber getrennt und Erkenntnisse sind pro Nutzer widerrufbar.

## Deliverables

### 1) Neues Modul `src/wissensnetz/feedback.py`
- Ein **Event-Modell** für die MP-Selektion (dataclass oder pydantic), passend zu
  `data/sample/selection_event.json`. Felder mindestens: `user`, `samples`
  (Liste von Proben-IRIs oder `submitterId`s), `hypothesis` (z. B.
  Reclassification `from`→`to` als NCIt/DB-IRI, plus freier `note`/`tag`),
  `view` (z. B. „gene-tSNE ↔ miRNA-tSNE"), `morph_param` (t), `confidence`,
  `timestamp`.
- `selection_to_sparql(event) -> str` — erzeugt das `INSERT DATA`-Update:
  eine `oa:Annotation , db:ExpertFinding` mit `prov:wasAttributedTo`,
  `prov:generatedAtTime`, `db:inView`, `db:morphParam`, `db:confidence`,
  `oa:hasTarget` (die Proben) und `db:hypothesis` (Reclassification from→to),
  **plus** die RDF-star-Kern-Aussage
  `<< db:sample-X db:reclassifiedAs <ziel> >> prov:wasDerivedFrom <anno> ; db:confidence … .`
- `write_feedback(store, event) -> graph_iri` — schreibt in den Nutzer-Named-Graph
  (via `graphstore.update()`), gibt das Graph-IRI zurück.
- `list_findings(store, user=None) -> list[dict]` — liest Annotationen (und ihre
  Ziele/Hypothese) per SPARQL wieder aus; für Nutzer optional gefiltert.

### 2) Vokabular
Neue Terme (`db:ExpertFinding`, `db:hypothesis`, `db:Reclassification`,
`db:from`, `db:to`, `db:reclassifiedAs`, `db:inView`, `db:morphParam`,
`db:confidence`) definieren — entweder in `ontology/databridge-core.ttl` oder in
einer eigenen `ontology/feedback.ttl` (dann von `init.py` mitladen). Kurz
dokumentieren. `oa:`/`prov:`-Terme werden wiederverwendet, nicht neu definiert.

### 3) CLI-Erweiterung in `cli.py`
- `wissensnetz feedback <event.json> [--user <id>]` → schreibt das Event, gibt
  das Named-Graph-IRI aus.
- `wissensnetz findings [--user <id>]` → listet gespeicherte Erkenntnisse.

### 4) Beispieldaten `data/sample/selection_event.json`
Das Fallstudie-1-Beispiel (PAAD→PanNET) aus dem Rückkanal-Konzept: ~6 Proben,
Hypothese Reclassification `PAAD`→`PanNET`, Sicht, Morph-t, Konfidenz, Nutzer.

### 5) Tests `tests/test_feedback.py`
- Event in einen **isolierten Named Graph** schreiben, per SPARQL wieder auslesen:
  Annotation vorhanden, alle Proben als `oa:hasTarget`, Hypothese from→to korrekt,
  und die **RDF-star-Aussage** abfragbar (SELECT mit `<< ?s ?p ?o >>`-Muster).
  Im `finally` `DROP GRAPH`. Skip ohne Fuseki (Fixtures übernehmen das).

### 6) Doku
`wissensnetz/README.md`: CLI-Tabelle + End-to-End-Ablauf um `feedback`/`findings`
ergänzen; kurz die Named-Graph-pro-Nutzer-Ablage und RDF-star-Provenienz erklären.

## Grenzen (aus CLAUDE.md)
Nur unter `wissensnetz/` schreiben; `mediator/` und `wrappers/` nicht anfassen;
kein Import aus fremden Teilen; nur HTTP/SPARQL gegen `graph-db`.

## Definition of Done
`feedback.py` mit Event-Modell + write/read; Vokabular geladen; CLI `feedback` +
`findings` lauffähig; `pytest` grün gegen laufendes Fuseki (Skip ohne,
self-isolating); README aktualisiert. Damit sind alle drei Richtungen (①②③) des
Wissensnetzes umgesetzt.
