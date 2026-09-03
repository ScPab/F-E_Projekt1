# Semantische Mapping-Schicht (`app/semantic/`)

Übersetzt Rohdaten aller vier angebundenen Quellen (GDC, GEO, ENA,
cBioPortal) nach RDF/OWL gegen die gemeinsame Ontologie
[`wissensnetz/ontology/databridge-core.ttl`](../../../wissensnetz/ontology/databridge-core.ttl)
(Namespace `db:` = `http://databridge.hka/onto#`, Instanzen unter
`http://databridge.hka/instance/`). Erreichbar über `POST /transform`
(`source` wählt die Quelle) und `GET /ontology` (liefert die TBox), siehe
[`app/main.py`](../main.py).

Jede Quelle hat ein eigenes Mapping-Modul (Global-as-View, siehe
[`/docs/adding_new_sources.md`](../../../docs/adding_new_sources.md)):

| Modul | Quelle | Eingabe | Kern-Funktion |
|---|---|---|---|
| [`mapping.py`](mapping.py) | GDC | `cases`-Treffer (`GDCWrapper.search`) | `cases_to_graph()` |
| [`mapping_geo.py`](mapping_geo.py) | GEO | Series-Treffer (`GEOWrapper.search(entry_type="gse")`) | `series_to_graph()` |
| [`mapping_ena.py`](mapping_ena.py) | ENA | `read_run`-Treffer (`ENAWrapper.search`) | `runs_to_graph()` |
| [`mapping_cbioportal.py`](mapping_cbioportal.py) | cBioPortal | PATIENT-/SAMPLE-Klinikdaten (`CBioPortalWrapper.get_clinical_data`) | `clinical_data_to_graph()` |

Alle vier geben `(rdflib.Graph, list[StarAnnotation])` zurück — dieselbe Form
wie `mapping.cases_to_graph` — damit `mapping.serialize_with_provenance()`
(Turtle-Serialisierung + RDF-star-Provenienz-Anhang) unverändert für alle
Quellen wiederverwendet werden kann. Nur GDC füllt die Annotationsliste
aktuell tatsächlich (NCIt-Alignment für `primary_diagnosis`); GEO/ENA/
cBioPortal liefern immer eine leere Liste (kein Enum-Alignment in diesem
ersten Ausschnitt, siehe "Grenzen" unten).

## Wiederverwendungsprinzip

Die Ontologie ist bewusst quellenunabhängig (`db:` statt z. B. `gdc:`) — wo
ein Konzept zwischen Quellen wirklich übereinstimmt, nutzen mehrere Module
dieselbe Klasse/Property, statt sie zu duplizieren:

| Klasse/Property | Genutzt von | Rolle |
|---|---|---|
| `db:Project`, `db:Case`, `db:Demographic`, `db:Diagnosis`, `db:Sample` | GDC **und** cBioPortal | cBioPortal bereitet häufig dieselben TCGA/GDC-Ursprungsdaten auf (siehe `wrappers/cbioportal/client.py`-Docstring) |
| `db:gender`, `db:race`, `db:ethnicity`, `db:vitalStatus`, `db:sampleType`, `db:tumorStage` | GDC **und** cBioPortal | identische Properties, gleiche `rdfs:domain` (Demographic/Sample/Diagnosis) |
| `db:Run` | GEO **und** ENA | "ein Lauf/Sample innerhalb einer Serie/Studie" — dieselbe Rolle, unabhängig von der Elternklasse |
| `db:hasRun` / `db:isRunOf` | GEO **und** ENA | verlinkt sowohl `db:Series` (GEO) als auch `db:Study` (ENA) mit `db:Run` |
| `db:organism` | GEO **und** ENA | Taxon-Angabe (GEO `taxon`, ENA `scientific_name`) |
| `db:sampleCount` | GEO **und** cBioPortal | Probenanzahl (GEO `n_samples`, cBioPortal `allSampleCount` — Feld aktuell nicht abgerufen, Property vorbereitet) |

`db:Series` (GEO) und `db:Study` (ENA) bleiben bewusst **eigene** Klassen statt
in `db:Project` hineingezwungen zu werden — die Identifikator-/Feld-Semantik
ist zu unterschiedlich (GSE-Accession + Organismus/Plattform-Metadaten vs.
TCGA-Projekt-Code). Eine gemeinsame Oberklasse ("benannter Container mit
Proben") ist eine bewusst offen gelassene, spätere Ontologie-Entscheidung.

## Label-Tabellen je Quelle

### GDC (`mapping.py`, Felder aus `TRANSFORM_CASE_FIELDS` in `app/main.py`)

| GDC-Feld (roh) | Mediator-/Ontologie-Label | Zielklasse | Bemerkung |
|---|---|---|---|
| `case_id` | `db:caseId` | `db:Case` | |
| `submitter_id` | `db:submitterId` | `db:Case` | |
| `project.project_id` | `db:projectId` | `db:Project` | über `db:belongsToProject`/`db:hasCase` verlinkt |
| `demographic.gender` | `db:gender` | `db:Demographic` | |
| `demographic.race` | `db:race` | `db:Demographic` | |
| `demographic.ethnicity` | `db:ethnicity` | `db:Demographic` | |
| `demographic.vital_status` | `db:vitalStatus` | `db:Demographic` | |
| `diagnoses.primary_diagnosis` | `db:primaryDiagnosisLabel` (immer) + `db:primaryDiagnosis` (bei Alignment-Treffer) | `db:Diagnosis` | NCIt-Alignment über `ontology/alignment/ncit_primary_diagnosis.json`, sonst nur Literal |
| `diagnoses.age_at_diagnosis` | `db:ageAtDiagnosis` | `db:Diagnosis` | `xsd:integer` |
| `diagnoses.morphology` | `db:morphology` | `db:Diagnosis` | |
| `diagnoses.site_of_resection_or_biopsy` | `db:siteOfResectionOrBiopsy` | `db:Diagnosis` | |
| `diagnoses.ajcc_pathologic_stage` | `db:tumorStage` | `db:Diagnosis` | Label weicht bewusst vom Rohfeld ab (GDC hat kein `tumor_stage`) |
| `diagnoses.metastasis_at_diagnosis` | `db:metastasisAtDiagnosis` | `db:Diagnosis` | |
| `samples.sample_id` | *(nur Instanz-IRI)* | `db:Sample` | kein eigenes Literal, nur URI-Bildung |
| `samples.sample_type` | `db:sampleType` | `db:Sample` | |

### GEO (`mapping_geo.py`, `entry_type="gse"`-Treffer)

| GEO-Feld (esummary) | Mediator-Label | Zielklasse | Bemerkung |
|---|---|---|---|
| `accession` | `db:seriesId` | `db:Series` | |
| `title` | `rdfs:label` | `db:Series` | |
| `summary` | `rdfs:comment` | `db:Series` | |
| `taxon` | `db:organism` | `db:Series` | |
| `gdstype` | `db:experimentType` | `db:Series` | |
| `pdat` | `db:releaseDate` | `db:Series` | Rohtext, kein garantiertes ISO-8601 |
| `n_samples` | `db:sampleCount` | `db:Series` | `xsd:integer` |
| `ftplink` | `db:ftpLink` | `db:Series` | `xsd:anyURI` |
| `samples[].accession` | `db:runId` | `db:Run` | GSM-Accession |
| `samples[].title` | `rdfs:label` | `db:Run` | |

Verknüpfung: `db:hasRun`/`db:isRunOf` (Series → Run).

### ENA (`mapping_ena.py`, `result="read_run"`-Treffer)

| ENA-Feld | Mediator-Label | Zielklasse | Bemerkung |
|---|---|---|---|
| `run_accession` | `db:runId` | `db:Run` | |
| `description` | `rdfs:label` | `db:Run` | |
| `library_strategy` | `db:libraryStrategy` | `db:Run` | |
| `instrument_platform` | `db:instrumentPlatform` | `db:Run` | |
| `scientific_name` | `db:organism` | `db:Run` | |
| `read_count` | `db:readCount` | `db:Run` | String → `xsd:integer` gecastet |
| `study_accession` | `db:studyId` | `db:Study` | |

Verknüpfung: `db:hasRun`/`db:isRunOf` (Study → Run) — dieselben Properties wie bei GEO.

### cBioPortal (`mapping_cbioportal.py`, PATIENT- + SAMPLE-Klinikdaten)

Long-Format (`clinicalAttributeId`/`value` je Zeile) wird vor dem Mapping
nach `patientId`/`sampleId` pivotiert.

| cBioPortal `clinicalAttributeId` | Mediator-Label | Zielklasse | Bemerkung |
|---|---|---|---|
| `SEX` / `GENDER` | `db:gender` | `db:Demographic` | wiederverwendet von GDC |
| `VITAL_STATUS` | `db:vitalStatus` | `db:Demographic` | wiederverwendet von GDC |
| `RACE` | `db:race` | `db:Demographic` | wiederverwendet von GDC |
| `ETHNICITY` | `db:ethnicity` | `db:Demographic` | wiederverwendet von GDC |
| `AGE` | `db:age` | `db:Case` | **neu** — anders als `db:ageAtDiagnosis` nicht an ein Diagnose-Ereignis gebunden |
| `AJCC_PATHOLOGIC_TUMOR_STAGE` / `TUMOR_STAGE` | `db:tumorStage` | `db:Diagnosis` | wiederverwendet von GDC |
| `SAMPLE_TYPE` (SAMPLE-Ebene) | `db:sampleType` | `db:Sample` | wiederverwendet von GDC |
| `ONCOTREE_CODE` (SAMPLE-Ebene) | `db:oncotreeCode` | `db:Sample` | **neu** |
| *(Studie)* `study_id` | `db:projectId` | `db:Project` | wiederverwendet von GDC, nur ID (kein Name/Beschreibung abgerufen) |

Verknüpfung: `db:belongsToProject`/`db:hasCase` (Project ↔ Case),
`db:hasDemographic`/`db:isDemographicOf` (Case ↔ Demographic, nur falls
mindestens ein Demographic-Attribut vorhanden ist), `db:hasDiagnosis`/
`db:describesCase` (Case ↔ Diagnosis, nur falls ein Tumor-Stage-Attribut
vorhanden ist), `db:hasSample`/`db:isSampleOf` (Case ↔ Sample) — alles
dieselben Properties wie bei GDC.

## Grenzen dieses ersten Ausschnitts

- **Kein Enum-Alignment für GEO/ENA/cBioPortal.** Nur GDCs
  `primary_diagnosis` wird optional auf NCIt abgebildet (siehe
  `wissensnetz/ontology/alignment/`). Für die anderen Quellen wäre das
  nächste sinnvolle Alignment vermutlich `db:organism` → NCBI Taxonomy bzw.
  `db:tumorStage`/`db:oncotreeCode` → NCIt/DO — bewusst nicht spekulativ
  vorweggenommen (siehe `docs/adding_new_sources.md`, "Prozess ist manuell").
- **`clinicalAttributeId`s sind studienspezifisch.** cBioPortal hat kein
  global festes klinisches Schema (anders als GDC) — die Attribut-Tabellen in
  `mapping_cbioportal.py` decken nur gebräuchliche, über TCGA-abgeleitete
  Studien hinweg wiederkehrende IDs ab. Andere/seltenere Attribut-Namen
  (z. B. Studien-eigene IDs) werden derzeit stillschweigend ignoriert, nicht
  geraten gemappt.
- **`db:Diagnosis`-Cardinality-Restriktion.** Die TBox verlangt für
  `db:Diagnosis` mindestens `db:primaryDiagnosisLabel` (`owl:minCardinality
  1`, aus dem GDC-Konstrukt `required: [primary_diagnosis]`). Von
  cBioPortal erzeugte `db:Diagnosis`-Knoten tragen nur `db:tumorStage`,
  erfüllen diese Restriktion also nicht — folgenlos ohne OWL-Reasoning
  (Fuseki/Jena ohne Inferenz speichert die Tripel trotzdem), aber ein
  aktivierter Reasoner würde das als inkonsistent melden. Bekannte
  Inkonsistenz, keine stille Verletzung.
- **ENA/cBioPortal liefern keine Gesamttrefferzahl** (siehe die jeweiligen
  Wrapper-Docstrings) — `size` in `POST /transform` ist daher bei diesen
  beiden Quellen eine Obergrenze pro Aufruf, keine Aussage über die
  Gesamtmenge.
- **Kein direkter GDC↔cBioPortal-Instanz-Abgleich.** Auch wenn dieselbe
  TCGA-Kohorte über beide Quellen erreichbar ist, erzeugen GDC- und
  cBioPortal-Mapping unabhängige `db:Case`-Instanzen (IRI aus `case_id` bzw.
  `patientId` — i. d. R. unterschiedliche IDs für dieselbe Person). Eine
  `owl:sameAs`-Verknüpfung wäre ein sinnvoller nächster Schritt, ist hier
  aber nicht Teil des ersten Ausschnitts.

## Beispielaufrufe

```bash
# GDC (bestehend)
curl -X POST http://localhost:8000/transform \
  -H "Content-Type: application/json" \
  -d '{"source": "gdc", "project_id": "TCGA-BRCA", "size": 5}'

# GEO
curl -X POST http://localhost:8000/transform \
  -H "Content-Type: application/json" \
  -d '{"source": "geo", "organism": "Homo sapiens", "size": 5}'

# ENA
curl -X POST http://localhost:8000/transform \
  -H "Content-Type: application/json" \
  -d '{"source": "ena", "study_accession": "PRJEB1234", "size": 5}'

# cBioPortal (study_id ist Pflicht)
curl -X POST http://localhost:8000/transform \
  -H "Content-Type: application/json" \
  -d '{"source": "cbioportal", "study_id": "acbc_mskcc_2015", "size": 20}'
```

Alle vier akzeptieren zusätzlich `load: true` (+ optional `graph: "<IRI>"`),
um das Ergebnis direkt per Graph Store Protocol in `graph-db` (Fuseki) zu
schreiben, sowie rohe Treffer statt Live-Abruf (`cases`/`series`/`runs`/
`patient_data`+`sample_data` — siehe `TransformRequest` in `app/schemas.py`
für die vollständige, quellenspezifische Feldliste).

## Neue Quelle hinzufügen

Siehe [`/docs/adding_new_sources.md`](../../../docs/adding_new_sources.md) —
dieselben fünf Schritte (Ontologie-Abgleich → ggf. erweitern → neues
`mapping_<source>.py` → Endpunkt-Verdrahtung in `app/main.py` → Test), nach
denen GEO/ENA/cBioPortal hier umgesetzt wurden.
