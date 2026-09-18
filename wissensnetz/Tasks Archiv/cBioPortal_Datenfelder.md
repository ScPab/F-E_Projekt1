# cBioPortal — Datenfelder (Labels)

> ⚠️ **Wichtiger struktureller Unterschied zu GDC/GEO/ENA**: cBioPortal hat **kein zentrales, festes Daten-Dictionary** für klinische Felder. Die REST-API-Objekte (Study, Sample, Patient, Mutation, ...) haben ein festes Schema (unten, Abschnitt 1) — aber die eigentlichen **klinischen Attribute** (Alter, Stadium, Überleben etc.) werden pro Studie individuell in deren `data_clinical_patient.txt`/`data_clinical_sample.txt`-Dateien definiert und sind daher grundsätzlich **studienspezifisch**. Abschnitt 2 listet die de-facto standardisierten Attribut-IDs, die über die meisten TCGA-basierten Studien hinweg konsistent verwendet werden (z. B. im cBioPortal Datahub / PanCancer-Atlas-Studien) — das ist Konvention, kein Dictionary-Zwang.
>
> Um die tatsächlich verfügbaren Felder einer konkreten Studie zu ermitteln: `GET /api/studies/{studyId}/clinical-attributes`.
>
> Quellen: [cBioPortal REST API Doku](https://docs.cbioportal.org/web-api-and-clients.md) · [cBioPortal API Swagger](https://www.cbioportal.org/api/swagger-ui/index.html) · [cBioPortal Datahub](https://github.com/cBioPortal/datahub)

---

## 1. REST-API-Objektschema (fest)

### CancerStudy
`studyId`, `name`, `description`, `publicStudy`, `pmid`, `citation`, `groups`, `status`, `importDate`, `cancerTypeId`, `cancerType`, `allSampleCount`, `readPermission`, `referenceGenome`

### Sample
`sampleId`, `patientId`, `studyId`, `sampleType` *(z. B. Primary Solid Tumor, Metastatic)*, `sequenced`, `copyNumberSegmentPresent`, `uniqueSampleKey`, `uniquePatientKey`

### Patient
`patientId`, `studyId`, `uniquePatientKey`

### ClinicalAttribute *(Metadaten über ein klinisches Feld)*
`clinicalAttributeId`, `displayName`, `description`, `datatype` *(STRING/NUMBER/BOOLEAN)*, `patientAttribute` *(true/false — Patient- vs. Sample-Ebene)*, `priority`, `studyId`

### ClinicalData *(der eigentliche Wert)*
`clinicalAttributeId`, `value`, `patientId`, `sampleId`, `studyId`, `uniqueSampleKey`, `uniquePatientKey`

### MolecularProfile
`molecularProfileId`, `studyId`, `molecularAlterationType` *(MUTATION_EXTENDED, COPY_NUMBER_ALTERATION, MRNA_EXPRESSION, PROTEIN_LEVEL, STRUCTURAL_VARIANT, METHYLATION, ...)*, `datatype`, `name`, `description`, `showProfileInAnalysisTab`, `pivotThreshold`, `sortOrder`

### Gene
`entrezGeneId`, `hugoGeneSymbol`, `type`, `cytoband`, `length`

### Mutation
`entrezGeneId`, `sampleId`, `studyId`, `patientId`, `center`, `mutationStatus`, `validationStatus`, `tumorAltCount`, `tumorRefCount`, `normalAltCount`, `normalRefCount`, `startPosition`, `endPosition`, `chr`, `referenceAllele`, `variantAllele`, `proteinChange`, `mutationType`, `ncbiBuild`, `variantType`, `keyword`, `driverFilter`, `driverFilterAnnotation`, `driverTiersFilter`, `driverTiersFilterAnnotation`

### CopyNumberSeg
`studyId`, `sampleId`, `chr`, `start`, `end`, `numProbes`, `segmentMean`

### StructuralVariant
`structuralVariantId`, `sampleId`, `studyId`, `site1EntrezGeneId`, `site1HugoSymbol`, `site1EnsemblTranscriptId`, `site2EntrezGeneId`, `site2HugoSymbol`, `site2EnsemblTranscriptId`, `eventInfo`, `variantClass`, `connectionType`, `annotation`, `comments`

### GenePanel
`genePanelId`, `description`

### SampleList
`sampleListId`, `studyId`, `category`, `name`, `description`, `sampleCount`

---

## 2. Häufig verwendete standardisierte klinische Attribut-IDs (Konvention, nicht garantiert)

> Diese IDs tauchen konsistent in den meisten TCGA-abgeleiteten cBioPortal-Studien (z. B. PanCancer-Atlas) auf, sind aber **kein** verpflichtendes Schema — jede Studie kann eigene/zusätzliche Attribute definieren oder einzelne dieser IDs weglassen.

**Demografie**
`AGE`, `SEX`, `GENDER`, `RACE`, `ETHNICITY`

**Überleben / Verlauf**
`OS_STATUS`, `OS_MONTHS` *(Overall Survival)*, `DFS_STATUS`, `DFS_MONTHS` *(Disease-Free Survival)*, `PFS_STATUS`, `PFS_MONTHS` *(Progression-Free Survival)*, `DSS_STATUS`, `DSS_MONTHS` *(Disease-Specific Survival)*

**Tumor-Klassifikation**
`CANCER_TYPE`, `CANCER_TYPE_DETAILED`, `ONCOTREE_CODE`, `SAMPLE_TYPE`, `TUMOR_TYPE`, `TUMOR_SITE`, `SUBTYPE`, `HISTOLOGICAL_DIAGNOSIS`, `GRADE`

**Staging**
`AJCC_PATHOLOGIC_TUMOR_STAGE`, `AJCC_STAGING_EDITION`, `PATH_T_STAGE`, `PATH_N_STAGE`, `PATH_M_STAGE`, `CLIN_T_STAGE`, `CLIN_N_STAGE`, `CLIN_M_STAGE`

**Genomische Summary-Metriken**
`MUTATION_COUNT`, `FRACTION_GENOME_ALTERED`, `TMB_NONSYNONYMOUS` *(Tumor Mutational Burden)*, `MSI_SCORE`, `MSI_TYPE` *(Mikrosatelliteninstabilität)*, `ANEUPLOIDY_SCORE`

**Behandlung / Krankheitsverlauf**
`PRIOR_DX`, `RADIATION_THERAPY`, `PHARMACEUTICAL_TX_ADJUVANT`, `RADIATION_TX_ADJUVANT`, `PERSON_NEOPLASM_CANCER_STATUS`, `NEW_TUMOR_EVENT_AFTER_INITIAL_TREATMENT`

**Allgemeinzustand / Lebensstil**
`KARNOFSKY_PERFORMANCE_SCORE`, `ECOG_SCORE`, `WEIGHT`, `HEIGHT`, `BMI`, `TOBACCO_SMOKING_HISTORY`, `ALCOHOL_HISTORY`

---

## Hinweis zur Datenintegration

Da cBioPortal-Studien häufig direkt aus GDC/TCGA-Daten abgeleitet sind (viele Attribute in Abschnitt 2 entsprechen 1:1 GDC-Feldern, nur in SCREAMING_SNAKE_CASE statt snake_case, z. B. `AGE` ≈ `age_at_index`, `RACE` ≈ `race`, `AJCC_PATHOLOGIC_TUMOR_STAGE` ≈ `ajcc_pathologic_stage`), könnte für DataBridge ein Mapping zwischen den beiden Namenskonventionen sinnvoll sein, falls cBioPortal als zusätzliche/alternative Datenquelle neben GDC dient.
