# Aufgabe 5 (nur): MP-Lite-Hover wie das Original-MP-Tool von Oviedo

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich diese Aufgabe** um, **ausschließlich in `wissensnetz/`**.
Strikte Komponentengrenze: **NICHT** `mediator/` und **NICHT** `wrappers/` editieren,
und die eingefrorene Fixture `wissensnetz/data/sample/cases_brca_sample.ttl`
**NICHT** von Hand ändern (die gehört dem Mediator-Mapping). Kopplung nur über
den Graphen/SPARQL. Branch `Wissensnetz`, kleine Commits.

## Ziel
Der Maus-Hover über einen Punkt in MP-Lite soll dieselben Felder zeigen wie das
Original-MP-Tool von Oviedo, in genau dieser Reihenfolge und mit diesen Labels:
  Sample, cancer, type, race, gender, ethnicity, tumor_stage, morphology,
  site_of_resection_or_biopsy, primary_diagnosis, has_metastasis, vital_status
Fehlende Werte werden als "--" angezeigt (wie im Oviedo-Tool). In dieser Aufgabe
werden **keine** Demo-Daten erfunden – Felder, die noch nicht im Graphen liegen,
zeigen "--", bis Mediator/Wrapper sie liefern (siehe Hand-off-Notiz, Deliverable 4).

## Worauf du aufbaust (vorhandener Code, nicht neu erfinden)
- `prototype/mp_lite/app.py` — Bokeh-App; hier sitzt der aktuelle HoverTool
  (`("Sample","@tumor"), ("Cancer","@cancer"), ("im Graph","@in_graph")`) und die
  Startlogik mit `IN_GRAPH`/`SYNTHETIC`-Proben und der `ColumnDataSource`.
- `src/wissensnetz/enrichment.py` — `case_context(store, barcode)` liefert heute
  `case_iri, submitter_id, project_id, gender, diagnoses[{iri,label,
  age_at_diagnosis,aligned_concept}]`. Darauf baust du auf (tolerante OPTIONALs).
- `ontology/databridge-core.ttl` — TBox; bestehende Property-Deklarationen als
  Stil-Vorlage (rdfs:label / rdfs:domain / rdfs:range / rdfs:comment).
- `src/wissensnetz/config.py` — `PREFIXES`, Namespaces `DB`, `INSTANCE`, …
- `tests/conftest.py` — Fixtures `store`/`loaded_store` (Skip ohne Fuseki).

## Feld-Abbildung (Oviedo -> DataBridge)
Bereits im Graph vorhanden:
  Sample            -> db:submitterId (Case)
  gender            -> db:gender (Demographic)
  primary_diagnosis -> db:primaryDiagnosisLabel (erste Diagnosis)
  cancer            -> aus db:projectId ableiten: "TCGA-PRAD" -> "PRAD"
                       (Präfix "TCGA-" abschneiden; sonst projectId unverändert)
Neu (nur zeigen, Wert vorerst meist "--"):
  race        -> db:race (Demographic)                       [NEU]
  ethnicity   -> db:ethnicity (Demographic)                  [NEU]
  vital_status-> db:vitalStatus (Demographic)                [NEU]
  tumor_stage -> db:tumorStage (Diagnosis)                   [NEU]
  morphology  -> db:morphology (Diagnosis)                   [NEU]
  site_of_resection_or_biopsy -> db:siteOfResectionOrBiopsy (Diagnosis)  [NEU]
  has_metastasis -> db:metastasisAtDiagnosis (Diagnosis)     [NEU]
  type (sample_type) -> derzeit KEIN passender Knoten im Modell (GDC-"sample"
       ist noch nicht modelliert). In dieser Aufgabe NICHT neu erfinden:
       Spalte anlegen, aber fest "--" zeigen und in der Hand-off-Notiz vermerken.

## Deliverables

### 1) TBox erweitern — `ontology/databridge-core.ttl`
Neue `owl:DatatypeProperty` deklarieren, im Stil der bestehenden Properties
(rdfs:label, rdfs:domain, rdfs:range xsd:string, kurzer rdfs:comment):
  db:race, db:ethnicity, db:vitalStatus          (rdfs:domain db:Demographic)
  db:tumorStage, db:morphology, db:siteOfResectionOrBiopsy,
  db:metastasisAtDiagnosis                        (rdfs:domain db:Diagnosis)
`db:sampleType` NICHT anlegen (braucht eine Sample-Klasse -> Hand-off-Notiz).

### 2) `case_context` erweitern — `src/wissensnetz/enrichment.py`
Die bestehende SPARQL-Abfrage um OPTIONAL-Blöcke für die neuen Properties ergänzen
(Demographic: race/ethnicity/vitalStatus; Diagnosis: tumorStage/morphology/
siteOfResectionOrBiopsy/metastasisAtDiagnosis). Rückgabe-Dict erweitern:
`race`, `ethnicity`, `vital_status` auf Top-Ebene; die vier Diagnose-Felder pro
Diagnose-Eintrag (in `_diagnosis_row`). Tolerant bleiben: fehlt ein Wert, `None`
zurückgeben (keine Exception). Docstring anpassen.

### 3) MP-Lite-Hover umbauen — `prototype/mp_lite/app.py`
- Beim Start für jede `IN_GRAPH`-Probe `case_context(store, barcode)` aufrufen und
  die Werte in NEUE `ColumnDataSource`-Spalten schreiben: `cancer` (aus projectId
  abgeleitet), `sample_type`, `race`, `gender`, `ethnicity`, `tumor_stage`,
  `morphology`, `site_biopsy`, `primary_diagnosis`, `has_metastasis`,
  `vital_status` (erste Diagnose verwenden).
  Für `SYNTHETIC`-Punkte und jeden fehlenden Wert "--" eintragen.
  Kleine Helper-Funktion `_dash(v)` -> `str(v)` wenn v nicht None/"" sonst "--".
  Robust bleiben, wenn `STORE_OK` False ist (dann überall "--").
- Den HoverTool ersetzen durch die volle Oviedo-Feldliste, exakte Reihenfolge:
    [("Sample","@tumor"), ("cancer","@cancer"), ("type","@sample_type"),
     ("race","@race"), ("gender","@gender"), ("ethnicity","@ethnicity"),
     ("tumor_stage","@tumor_stage"), ("morphology","@morphology"),
     ("site_of_resection_or_biopsy","@site_biopsy"),
     ("primary_diagnosis","@primary_diagnosis"),
     ("has_metastasis","@has_metastasis"), ("vital_status","@vital_status")]
- Seitenpanel-Kontext (② case_context) und Rückkanal (③) bleiben unverändert
  funktionsfähig.

### 4) Hand-off-Notiz anlegen — `prototype/mp_lite/HANDOFF_oviedo_felder.md`
Dokumentieren, was Mediator (Pablo) + GDC-Wrapper (Julian) ergänzen müssen, damit
echte Werte statt "--" erscheinen (deren Code wird hier NICHT angefasst):
- GDC-Wrapper: diese Felder anfragen: demographic.race, demographic.ethnicity,
  demographic.vital_status, diagnoses.morphology,
  diagnoses.site_of_resection_or_biopsy, diagnoses.ajcc_pathologic_stage (bzw.
  tumor_stage), diagnoses.metastasis_at_diagnosis, samples.sample_type,
  project.disease_type.
- Mediator: TRANSFORM_CASE_FIELDS (mediator/app/main.py) + cases_to_graph
  (mediator/app/semantic/mapping.py) müssen diese Felder als Tripel auf die neuen
  db:-Properties schreiben; danach Fixture cases_brca_sample.ttl neu aus dem
  Mediator ziehen (example_gdc_to_rdf.py). "type"/sample_type braucht zusätzlich
  eine Sample/Biospecimen-Klasse in der TBox (offener Modell-Punkt).

## Verifikation
- `tests/test_enrichment.py`: Test ergänzen, der prüft, dass `case_context` für
  eine Fixture-Probe die neuen Keys enthält (Werte dürfen None sein) und keine
  Exception wirft. Bestehende Tests bleiben grün: `pytest wissensnetz/tests -q`.
- TBox-Syntax prüfen (rdflib parst `databridge-core.ttl` ohne Fehler).
- Kurzcheck: `bokeh serve --show wissensnetz/prototype/mp_lite/app.py`, über eine
  grüne (IN_GRAPH) Probe hovern -> alle 12 Zeilen erscheinen, gefüllte Felder
  zeigen Werte, der Rest "--".

Halte dich strikt an die Komponentengrenze. Wenn etwas nur durch Änderungen an
`mediator/` oder `wrappers/` lösbar wäre, setze es NICHT um, sondern schreib es in
die Hand-off-Notiz.
