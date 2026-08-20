# DataBridge Core Ontology

TBox für den ersten Ausschnitt des GDC-Datenmodells (`case`, `project`,
`demographic`, `diagnosis`), umgesetzt nach den Konstrukt-Regeln aus
[`../Mapping-Konzept_GDC-zu-RDF-OWL - Kopie.pdf`](../Mapping-Konzept_GDC-zu-RDF-OWL%20-%20Kopie.pdf):
`node` → `owl:Class`, `property`+`type` → `owl:DatatypeProperty`,
`link`+`target_type` → `owl:ObjectProperty`, `backref` → `owl:inverseOf`,
`enum`-Werte → Alignment auf externe Bio-Ontologien, `required` →
`owl:minCardinality`, `title`/`description` → `rdfs:label`/`rdfs:comment`.

- `databridge-core.ttl` – die TBox selbst. Wird vom Mediator zur Laufzeit
  über die Umgebungsvariable `DATABRIDGE_ONTOLOGY_DIR` eingebunden (siehe
  `mediator/app/semantic/paths.py`) und unter `GET /ontology` ausgeliefert.
- `alignment/` – Alignment-Tabellen enum-Wert → externe Bio-Ontologie
  (aktuell: `ncit_primary_diagnosis.json`, GDC `primary_diagnosis` → NCIt).
  Bewusst leer angelegt — das Befüllen ist ein eigener, sorgfältiger Schritt
  (Nachschlagen über OLS/BioPortal), kein Teil der automatisierten Pipeline.
  Nicht gelistete Werte fallen auf `db:primaryDiagnosisLabel` (Literal)
  zurück, statt eine ungeprüfte Zuordnung zu erzwingen.

Namespace: `db:` = `http://databridge.hka/onto#`.

Erweiterung um neue Klassen/Properties oder eine neue Quelle:
siehe [`/docs/adding_new_sources.md`](../../docs/adding_new_sources.md).
