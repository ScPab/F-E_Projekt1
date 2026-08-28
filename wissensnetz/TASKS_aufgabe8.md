# Aufgabe 8 (nur): Sample/Biospecimen-Modell für `type` (Wissensnetz-Seite)

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich diese Aufgabe** um, **ausschließlich in `wissensnetz/`**.
Strikte Komponentengrenze: **NICHT** `mediator/`, **NICHT** `wrappers/` editieren;
Fixture `data/sample/cases_brca_sample.ttl` **NICHT** von Hand ändern. Branch
`Wissensnetz`, kleine Commits. Aufgaben 5–7 sind umgesetzt; du baust darauf auf.

## Hintergrund
Der MP-lite-Hover hat die Oviedo-Spalte `type` (GDC `samples.sample_type`, z. B.
"Primary Tumor" / "Solid Tissue Normal"), sie zeigt aber fest `"--"`, weil im
DataBridge-Modell **noch keine Sample-/Biospecimen-Klasse** existiert (in Aufgabe 5
bewusst nicht angelegt: eine Datatype-Property ohne tragende Klasse wäre
modellwidrig). Diese Aufgabe erledigt die **Wissensnetz-Seite** (TBox + Lesepfad +
UI), damit später **nur noch** der Mediator (Pablo) `samples.sample_type` auf
`db:sampleType` mappen muss und `type` ohne weitere Wissensnetz-Änderung echte
Werte zeigt. Siehe `prototype/mp_lite/HANDOFF.md`, Teil 2.

## Worauf du aufbaust (vorhandener Code, nicht neu erfinden)
- `ontology/databridge-core.ttl` — bestehende Klassen (db:Case/Demographic/
  Diagnosis/Project) und das Muster ObjectProperty + `owl:inverseOf` (z. B.
  `db:hasDemographic`/`db:isDemographicOf`) sowie DatatypeProperty-Deklarationen.
- `src/wissensnetz/enrichment.py` — `case_context()` (Einzelfall, OPTIONAL-Blöcke,
  Rückgabe-Dict) und `all_cases()` (Sammelabfrage aus Aufgabe 7). Beide tolerant
  gegen fehlende Werte.
- `prototype/mp_lite/app.py` — Hover-Spalte `sample_type` (aktuell hart `"--"`),
  Feldliste `_FIELDS`, Morph-Engine (aktiviert Slider automatisch bei ≥2 distinct
  Werten).
- `tests/conftest.py` — Fixtures `store`/`loaded_store`; Test-Isolation über eigenen
  Named Graph + `DROP GRAPH` im `finally` (siehe `tests/test_graphstore.py`).

## Deliverables (alle in `wissensnetz/`)

### 1) TBox erweitern — `ontology/databridge-core.ttl`
Im Stil der vorhandenen Deklarationen (rdfs:label/domain/range/comment):
- Neue Klasse `db:Sample` (owl:Class) — Biospecimen, entspricht GDC-Node `sample`.
- ObjectProperty `db:hasSample` (rdfs:domain `db:Case`, rdfs:range `db:Sample`)
  mit `owl:inverseOf db:isSampleOf`; dazu `db:isSampleOf`
  (domain `db:Sample`, range `db:Case`) — analog zu `hasDemographic`/`isDemographicOf`.
- DatatypeProperty `db:sampleType` (rdfs:domain `db:Sample`, rdfs:range `xsd:string`,
  kurzer Kommentar: Rohtext aus GDC `samples.sample_type`).

### 2) Lesepfad ergänzen — `src/wissensnetz/enrichment.py`
- `case_context()`: OPTIONAL-Block ergänzen
  `?c db:hasSample ?sample . ?sample db:sampleType ?sampleType`; im Rückgabe-Dict
  `sample_type` auf Top-Ebene liefern (erster Sample-Wert, analog `gender`).
  Bei mehreren Samples den ersten nicht-leeren Wert nehmen (`_first`-Muster).
- `all_cases()`: dieselbe OPTIONAL-Erweiterung, `sample_type` je Fall zurückgeben,
  tolerant `None`, wenn kein Sample vorhanden.
- Docstrings anpassen (neues Feld erwähnen, weiterhin optional).

### 3) MP-lite verdrahten — `prototype/mp_lite/app.py`
- Die CDS-Spalte `sample_type` nicht mehr hart `"--"` setzen, sondern aus
  `all_cases()`/`case_context()`-Feld `sample_type` füllen (über `_dash(...)`,
  fehlt der Wert -> `"--"`). Hover (Aufgabe 5) und Morph-Engine (Aufgabe 6)
  greifen dann automatisch — der `type`-Slider aktiviert sich von selbst, sobald
  echte, variierende Werte im Graphen liegen.

### 4) HANDOFF aktualisieren — `prototype/mp_lite/HANDOFF.md`
Teil 2 so anpassen, dass die Wissensnetz-Schritte als **erledigt** markiert sind
und nur noch der Mediator-Schritt offen bleibt:
- Schritt 1 (`db:Sample` + `db:hasSample`) — erledigt.
- Schritt 2 (`db:sampleType`) — erledigt.
- Schritt 4 (`case_context`/`all_cases` + MP-lite) — erledigt.
- Verbleibend (Pablo/Mediator): `samples.sample_type` auf `db:sampleType` mappen
  (`TRANSFORM_CASE_FIELDS` + `cases_to_graph`) und die Fixture neu ziehen. Bis
  dahin bleibt `type` = `"--"` (Slider deaktiviert) — Wissensnetz-Seite ist bereit.
  In die Kurz-Checkliste den `db:Sample`-Punkt entsprechend als erledigt umtragen.

## Verifikation
- TBox-Syntax: rdflib parst `databridge-core.ttl` fehlerfrei.
- `tests/test_enrichment.py` ergänzen (mit `loaded_store`, Skip ohne Fuseki):
  Eine kleine Inline-TTL mit einem `db:Case`, `db:hasSample`/`db:Sample` und
  `db:sampleType` in einen **eigenen Named Graph** laden (im `finally`
  `DROP GRAPH`), dann prüfen, dass `case_context`/`all_cases` `sample_type`
  korrekt zurückgeben. Zusätzlich: für die reine BRCA-Fixture (ohne Sample) ist
  `sample_type` = `None` und es fliegt keine Exception (Toleranz).
- Bestehende Tests bleiben grün: `pytest wissensnetz/tests -q`.
- `bokeh serve --show wissensnetz/prototype/mp_lite/app.py` startet weiterhin
  fehlerfrei; `type` zeigt `"--"` (mangels Mediator-Daten), aber ohne Fehler.

## Grenze / Hinweis
Echte `type`-Werte erscheinen erst, wenn Pablo den Mediator-Schritt umsetzt — das
ist Absicht und in `HANDOFF.md` dokumentiert. Diese Aufgabe macht ausschließlich
die Wissensnetz-Seite fertig; Mediator/Wrapper werden NICHT angefasst und die
Fixture nicht von Hand editiert.
