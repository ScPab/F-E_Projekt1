# Aufgabe 3 (nur): SPARQL-Anreicherung — Lesen aus dem Wissensnetz

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich Aufgabe 3** aus `wissensnetz/TASKS_wissensnetz.md` um —
NICHT Aufgabe 4 (Rückkanal). Aufgabe 1 (Dataset+TBox-Init) und 2 (Graphstore-
Client) sind bereits fertig; du baust darauf auf, ohne sie zu ändern.
Branch `Wissensnetz`, kleine Commits.

## Worauf du aufbaust (vorhandener Code, nicht neu erfinden)
- `src/wissensnetz/graphstore.py` — `GraphStore.query(sparql) -> list[dict]`
  (SELECT → `{var: wert}`-Dicts, Werte als String; `ask()` für ASK). Nutze das.
- `src/wissensnetz/config.py` — `PREFIXES` (db:, ncit:, prov:, oa:, owl:, rdfs:, …)
  und Namespace-Konstanten. Stelle `PREFIXES` deinen Abfragen voran.
- `src/wissensnetz/cli.py` — bestehendes argparse-Muster (`status|init|load|query`).
- `src/wissensnetz/init.py` — TBox liegt im **Default-Graph** (zusammen mit ABox).
- Beispieldaten: `data/sample/cases_brca_sample.ttl` (eingefrorene Mediator-Ausgabe,
  4 Cases im Projekt `TCGA-BRCA`, TBox-Klassen Project/Case/Demographic/Diagnosis).
- Tests: `tests/conftest.py` liefert Fixtures `store` und `loaded_store`
  (Skip ohne Fuseki). Test-Isolations-Lektion beachten (§5.1 der CHANGES): gegen
  einen **persistenten** Store Abfragen auf `TCGA-BRCA` eingrenzen bzw. eigene
  Named Graphs nutzen und im `finally` per `DROP GRAPH` verwerfen.

## Daten-Realität (WICHTIG, bestimmt das Testdesign)
- Die Alignment-Tabelle ist leer → aktuell gibt es **kein** `db:primaryDiagnosis`
  (NCIt-Link), nur `db:primaryDiagnosisLabel` (Literal). Der aligned-Concept ist
  also ein **optionales** Feld (OPTIONAL im SPARQL), das aktuell leer bleibt.
- Es ist **keine** Krankheitshierarchie geladen (NCIt nicht im Store), und die
  TBox-Klassen sind alle top-level (kein mehrstufiges `rdfs:subClassOf`). Die
  Hierarchie-Funktion daher **generisch** bauen und mit einer **isolierten
  Test-Fixture** prüfen (siehe Tests), nicht gegen nicht vorhandene Echtdaten.

## Deliverables

### 1) Neues Modul `src/wissensnetz/enrichment.py` (Funktionen, wiederverwendbar)
Reine Lese-Funktionen, die strukturierte Daten zurückgeben (damit sie später auch
der Mediator/eine API nutzen kann — Richtung Mediator→Wissensnetz):

- `subclasses(store, class_ref, *, include_self=True) -> list[str]`
  via Property-Path `rdfs:subClassOf*` (transitiv, generisch für beliebige
  Klasse). `class_ref` akzeptiert CURIE (`db:Case`) oder volle IRI.
- `superclasses(store, class_ref, *, include_self=True) -> list[str]`
  (inverse Richtung, `^rdfs:subClassOf*` oder `rdfs:subClassOf*` mit getauschten
  Positionen).
- `case_context(store, case_ref) -> dict` — `case_ref` = Case-IRI **oder**
  `submitterId`. Liefert: `project_id`, `gender`, und `diagnoses` als Liste von
  `{iri, label, age_at_diagnosis, aligned_concept?}` (aligned_concept via
  OPTIONAL, aktuell leer).
- `diagnosis_context(store, diagnosis_ref) -> dict` — analog für eine Diagnose
  (zugehöriger Case/submitterId, Label, Alter, optional aligned_concept).

Robust gegen persistenten Store: Abfragen auf konkrete IRIs/`submitterId` bzw.
das Projekt einschränken; keine ungebundenen `SELECT * WHERE { ?s ?p ?o }`.

### 2) CLI-Erweiterung in `cli.py`
Zwei neue Unterbefehle (klarer als der generische `query`):
- `wissensnetz hierarchy <klasse> [--up]` → Sub- bzw. (mit `--up`) Superklassen.
- `wissensnetz context <case-oder-diagnosis-ref>` → verknüpfte Konzepte hübsch
  ausgegeben (Projekt, Geschlecht, Diagnosen mit Label/Alter/optional NCIt).
Tabellen-/Listenausgabe im Stil der vorhandenen `query`-Ausgabe.

### 3) Tests `tests/test_enrichment.py`
- **Kontext (Echtdaten):** gegen `loaded_store` (Projekt `TCGA-BRCA`) prüfen, z. B.
  `case_context("TCGA-A1-A0SB")` → project_id `TCGA-BRCA`, gender `female`,
  Diagnose-Label „Infiltrating duct carcinoma, NOS", age 21200.
  `diagnosis_context` analog für `d-11111111`.
- **Hierarchie (isolierte Fixture):** eine kleine Klassenhierarchie in einen
  **eigenen Named Graph** laden (z. B. `:B rdfs:subClassOf :A . :A rdfs:subClassOf
  db:Disease .`), `subclasses("db:Disease")` muss `:A` und `:B` enthalten, danach
  `DROP GRAPH` im `finally`. So ist der `rdfs:subClassOf*`-Pfad bewiesen, ohne von
  NCIt/Alignment abzuhängen. (Hinweis: Named-Graph-Daten sind nur sichtbar, wenn
  die Abfrage sie einbezieht — ggf. `FROM`/`GRAPH` oder Default-Union beachten.)
- Skip ohne Fuseki (Fixtures übernehmen das bereits).

### 4) Doku
`wissensnetz/README.md`: CLI-Tabelle + Beispiele um `hierarchy` und `context`
ergänzen. Kurz notieren, dass `aligned_concept`/Krankheitshierarchie erst mit
befüllter Alignment-Tabelle bzw. geladenem NCIt echte Werte liefern.

## Grenzen (aus CLAUDE.md)
Nur unter `wissensnetz/` schreiben; `mediator/` und `wrappers/` nicht anfassen;
kein Import aus fremden Teilen; Kommunikation nur per HTTP/SPARQL gegen `graph-db`;
Mapping nicht nachbauen.

## Definition of Done
`enrichment.py` mit den vier Funktionen; CLI `hierarchy` + `context` lauffähig;
`pytest` grün gegen laufendes Fuseki (Skip ohne, self-isolating gegen persistenten
Store); README aktualisiert. Aufgabe 4 bleibt unangetastet.
```
