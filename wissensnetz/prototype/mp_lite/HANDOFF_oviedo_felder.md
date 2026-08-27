# Hand-off: Oviedo-MP-Hover-Felder mit echten Werten füllen

Der MP-lite-Hover zeigt jetzt die volle Oviedo-Feldliste (Aufgabe 5), in exakter
Reihenfolge:

    Sample, cancer, type, race, gender, ethnicity, tumor_stage, morphology,
    site_of_resection_or_biopsy, primary_diagnosis, has_metastasis, vital_status

Fehlende Werte erscheinen als `"--"` — genau wie im Original-MP-Tool von Oviedo.

Auf der Wissensnetz-Seite ist alles vorbereitet: Die TBox
(`wissensnetz/ontology/databridge-core.ttl`) deklariert die neuen
`db:`-Properties, `case_context()`
(`wissensnetz/src/wissensnetz/enrichment.py`) fragt sie tolerant per OPTIONAL ab,
und MP-lite (`app.py`) rendert sie. **Solange Mediator und GDC-Wrapper diese
Felder aber nicht als Tripel in den Graphen schreiben, bleiben sie leer (`"--"`).**
Es werden hier bewusst **keine** Demo-Werte erfunden.

Damit echte Werte statt `"--"` erscheinen, sind Änderungen **außerhalb** des
Wissensnetz-Teilbereichs nötig (dieser Code wird hier NICHT angefasst — strikte
Komponentengrenze):

## 1) GDC-Wrapper (Julian) — Felder aus der GDC-API anfragen

Die folgenden GDC-Felder zusätzlich in die Abfrage/Ausgabe aufnehmen, damit sie
im Case-JSON ankommen, das an den Mediator geht:

| Oviedo-Feld                   | GDC-Feld                                   |
|-------------------------------|--------------------------------------------|
| race                          | `demographic.race`                         |
| ethnicity                     | `demographic.ethnicity`                    |
| vital_status                  | `demographic.vital_status`                 |
| morphology                    | `diagnoses.morphology`                     |
| site_of_resection_or_biopsy   | `diagnoses.site_of_resection_or_biopsy`    |
| tumor_stage                   | `diagnoses.ajcc_pathologic_stage` (bzw. `tumor_stage`) |
| has_metastasis                | `diagnoses.metastasis_at_diagnosis`        |
| type (sample_type)            | `samples.sample_type`                      |
| (cancer)                      | `project.disease_type` — optional; MP-lite leitet `cancer` heute bereits aus `project.project_id` ab ("TCGA-PRAD" → "PRAD") |

## 2) Mediator (Pablo) — Felder als Tripel auf die neuen `db:`-Properties mappen

- `TRANSFORM_CASE_FIELDS` (`mediator/app/main.py`) und `cases_to_graph`
  (`mediator/app/semantic/mapping.py`) müssen die neuen Felder auf diese schon in
  der TBox deklarierten Ziel-Properties schreiben:

  - Demographic → `db:race`, `db:ethnicity`, `db:vitalStatus`
  - Diagnosis   → `db:tumorStage`, `db:morphology`,
    `db:siteOfResectionOrBiopsy`, `db:metastasisAtDiagnosis`

- Danach die eingefrorene Fixture
  `wissensnetz/data/sample/cases_brca_sample.ttl` **neu aus dem Mediator ziehen**
  (`mediator/scripts/example_gdc_to_rdf.py`) — sie gehört dem Mediator-Mapping und
  wird im Wissensnetz nicht von Hand editiert.

## 3) Offener Modell-Punkt: `type` / `sample_type`

`type` (GDC `samples.sample_type`, z. B. "Primary Tumor" / "Solid Tissue Normal")
hat **derzeit keinen passenden Knoten** im DataBridge-Modell: es gibt noch keine
Sample-/Biospecimen-Klasse. Deshalb wurde in Aufgabe 5 bewusst **keine**
`db:sampleType`-Property angelegt (eine Datatype-Property ohne tragende Klasse
wäre modellwidrig). Die Hover-Spalte `type` existiert, zeigt aber fest `"--"`.

Damit `type` echte Werte bekommt, ist zuerst eine Modell-Erweiterung nötig
(gemeinsam abzustimmen):

1. Neue Klasse `db:Sample` (Biospecimen) + ObjectProperty `db:hasSample`
   (Case → Sample) in `databridge-core.ttl`.
2. Datatype-Property `db:sampleType` (`rdfs:domain db:Sample`, `xsd:string`).
3. Mediator: `samples.sample_type` auf `db:sampleType` mappen.
4. `case_context()` um einen OPTIONAL-Block für `db:hasSample`/`db:sampleType`
   ergänzen und MP-lite `sample_type` daraus füllen.

Bis dahin bleibt `type` = `"--"`.
