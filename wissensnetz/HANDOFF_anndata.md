# Hand-off an Julian (Wrapper) & Pablo (Mediator): anndata (.h5ad) als Austauschformat (Teil 3)

Ausarbeitung von **Teil 3** aus `wissensnetz/prototype/mp_lite/HANDOFF.md`
(Expressionsdaten). Damit die expressionsbasierten Ansichten im MP-lite echt morphen
(genes/miRNA-tSNE sowie Einzelmarker wie CA9/SAA1/miRNA-210-3p), muss die
Expressionsmatrix als `anndata`/`.h5ad` durch die Pipeline — statt der heutigen
synthetischen Platzhalter-Layouts.

## 0) Architekturentscheidung (jetzt getroffen — deckt sich mit eurem Code)
Die bisher offene Frage „Expression über den Graphen (Tripel) ODER über einen
Seitenkanal (h5ad)?" ist entschieden:

> **Expression läuft NICHT als RDF-Tripel ins Wissensnetz, sondern als Matrix im
> `.h5ad`-Container. Das Wissensnetz liefert nur die semantischen Metadaten, mit
> denen `obs`/`var` angereichert werden.**

Das passt exakt zu dem, was ihr im Code schon festgelegt habt: Alle Wrapper-Docstrings
(`gdc/ena/cbioportal client.py`) sagen ausdrücklich *„Transformation nach anndata/.h5ad
ist bewusst NICHT Teil des Wrappers — separater, Mediator-seitiger Schritt"*, und
`Wrapper.to_anndata()` ist absichtlich `NotImplementedError`. Diese Aufgabe füllt genau
diese bereits vorgesehene Lücke: **Wrapper = Rohdaten beschaffen, Mediator = anndata
bauen, Wissensnetz = Metadaten liefern.**

Begründung (fachlich): Eine numerische Matrix (z. B. 10.000 Proben × 20.000 Gene) als
hunderte Millionen Tripel zu speichern, ist ineffizient und zweckfremd für den RDF-Store.
`anndata`/`.h5ad` (HDF5, von Scanpy nativ lesbar) ist das von Oviedo im Proposal
vorgeschlagene interoperable Austauschformat und verdrahtet dichte Matrizen fest mit
semantischen Metadaten.

## 1) anndata-Struktur → so mappen wir unsere Daten
| anndata-Feld | Inhalt | Quelle in DataBridge |
|---|---|---|
| `X`    | Expressionswerte, Proben × Gene/miRNA | **Wrapper (Julian):** Rohdaten-Download; **Mediator (Pablo):** Zusammenbau zur Matrix |
| `obs`  | Zeilen-Metadaten je Probe (klinisch/phänotypisch) | **Wissensnetz** via `enrichment.all_cases()` (Oviedo-Felder liegen dort schon) |
| `var`  | Spalten-Metadaten je Gen/miRNA (Symbol, Ensembl-/MIMAT-ID, ggf. GO) | **Wrapper/Mediator**; semantische Annotation später optional aus Wissensnetz |
| `obsm` | vorberechnete 2D-Layouts (tSNE genes / miRNA) | Vorverarbeitung (Scanpy) → `obsm["X_tsne_genes"]`, `obsm["X_tsne_mirna"]` |

`obsm` ist der direkte Lieferant für MP-lite/Aufgabe 6: die tSNE-Layouts werden zu den
Basis-Encodings `E[0]`/`E[1]` (genes/miRNA), die heute noch synthetisch (`L0`/`L1`)
sind. Einzelmarker-Slider (CA9, SAA1, miRNA-210-3p) speisen sich aus einzelnen Spalten
von `X`.

## 2) Position in der Pipeline
```
[ GDC / TCGA API ]
      │  (Metadaten + Expression-Rohmatrizen)
      ▼
[ DataBridge: Semantic ETL ] ──► [ RDF/OWL-Wissensnetz ]  (Ontologie, Klinik-Metadaten, Feedback)
      │                                   │
      │  X (Wrapper: Rohdaten)            │  obs/var-Anreicherung (SPARQL)
      ▼                                   ▼
                 [ anndata (.h5ad) ]  ◄── Mediator baut den Container (X + obs + var + obsm)
                        │
                        ▼
        [ Oviedo-Tools / MP-lite / Scanpy ]
```

## 3) Aufgaben nach Zuständigkeit

### 3a) Julian — Wrapper: Expressions-Rohdaten beschaffen (KEIN anndata)
Der Bulk-Tier existiert bereits (`GDCWrapper.build_manifest` +
`download_via_gdc_client`, nutzt das externe `gdc-client`). Zu tun:
- **Manifest gezielt auf Expression-Files filtern** und herunterladen:
  - RNA-Seq: `data_type = "Gene Expression Quantification"`
    (`experimental_strategy = "RNA-Seq"`, STAR-Counts/TPM).
  - miRNA-Seq: `data_type = "miRNA Expression Quantification"`
    (`experimental_strategy = "miRNA-Seq"`).
  - Offene Daten — kein Controlled-Access-Token nötig.
- Die heruntergeladenen Quantifizierungsdateien (je Probe eine Datei) in einer Form
  bereitstellen, die der Mediator zu einer Matrix zusammenbauen kann — inkl.
  **Proben↔Case-Zuordnung** (`sample_id`/Aliquot → `submitter_id`) und der
  Feature-IDs (Ensembl-Gen-IDs bzw. MIMAT-miRNA-IDs) für `var`.
- **`to_anndata` NICHT implementieren** — bleibt bewusst der Mediator-Schritt
  (so wie eure Docstrings es festlegen). Der Wrapper liefert nur Rohdaten +
  Zuordnung, keine Matrix-Semantik.
- Große Downloads über die vorhandenen Cache-Tiers puffern.

### 3b) Pablo — Mediator: anndata-Transformation + Export (`X`-Zusammenbau, `obs`, `.h5ad`)
Das ist der „separate, Mediator-seitige Schritt", auf den alle Wrapper verweisen —
neue Export-Schicht, z. B. `POST /export/anndata` (project_id, size, ggf. gene-set):
- Vom Wrapper die heruntergeladenen Expression-Files + Feature-IDs + Proben-Zuordnung
  beziehen und zu **`X`** (Zeilen = Proben, Spalten = Gene/miRNA) zusammensetzen.
- **`obs`** aus dem **Wissensnetz** füllen (nicht erneut aus GDC): `enrichment.all_cases()`
  liefert je Fall die Oviedo-Felder. `obs`-Index = Proben-ID; Klinik-Felder sind pro
  Case → per `submitter_id` an die Proben joinen (siehe Offener Punkt 5.1).
- **`var`** = Gen-Symbol/Ensembl bzw. MIMAT-IDs.
- Optional **`obsm`**: `adata.obsm["X_tsne_genes"]` / `["X_tsne_mirna"]` (vorberechnet).
- **Serialisieren:** `AnnData(X, obs, var).write_h5ad(<pfad>)`.
- `obs`-Spalten-Mapping (aus Wissensnetz):

  | obs-Spalte | Wissensnetz-Property |
  |---|---|
  | cancer / project_id | `db:belongsToProject`/`db:projectId` |
  | sample_type | `db:hasSample`/`db:sampleType` |
  | race, gender, ethnicity, vital_status | `db:race`/`db:gender`/`db:ethnicity`/`db:vitalStatus` |
  | tumor_stage, morphology, site_of_resection_or_biopsy, has_metastasis | `db:tumorStage`/`db:morphology`/`db:siteOfResectionOrBiopsy`/`db:metastasisAtDiagnosis` |
  | primary_diagnosis (+ NCIt) | `db:primaryDiagnosisLabel` (+ `db:primaryDiagnosis`) |
  | age_at_diagnosis | `db:ageAtDiagnosis` |

### 3c) Wissensnetz — Marcel (Abhängigkeit, kein Fremd-Code für euch)
- `enrichment.all_cases()` liefert `obs` schon fast vollständig. Soll der `obs`-Index die
  **Probe** (nicht der Case) sein, ergänze ich eine sample-granulare Leseabfrage (ein
  Case kann mehrere Samples haben). Sagt mir die gewählte `X`-Granularität, dann liefere
  ich die passende Funktion.
- `var`-Semantik (Gen→GO) aus dem Wissensnetz ist optional/später.

## 4) Bezug zu MP-lite (Aufgabe 6) — was danach „aufgeht"
Sobald ein Referenz-`.h5ad` existiert, lädt der Prototyp (Marcel) es und ersetzt:
- `obsm["X_tsne_genes"]`/`["X_tsne_mirna"]` → Basis-Encodings `E[0]`/`E[1]` statt der
  synthetischen `L0`/`L1`,
- einzelne `X`-Spalten (CA9, SAA1, MIMAT0000267) → lineare Encodings der Einzelmarker.
Damit werden die heute deaktivierten Expressions-Slider echt.

## 5) Offene Punkte — bitte im Team kurz abstimmen
1. **obs-Granularität:** Expression ist pro Aliquot/Sample, Klinik-Metadaten pro Case →
   ein repräsentatives Sample je Case oder alle Samples?
   → **Erste Entscheidung (Pablo, Mediator-Umsetzung):** pro Sample (`obs`-Index =
   `sample_id`), Klinik-Felder werden je Case auf seine Sample(s) dupliziert — siehe
   `app/semantic/expression.py::build_obs`-Docstring. Revidierbar, sobald das
   Wissensnetz eine sample-granulare Abfrage liefert (siehe Abschnitt 3c).
2. **Wer berechnet die tSNE (`obsm`)?** Im Oviedo-Original vorab trainiert
   (`pancancer_morphing.hdf`). Vorschlag: ein Scanpy-Vorverarbeitungsschritt
   (Mediator oder separates Skript), Ergebnis in `obsm`. Alternativ liefert DataBridge
   nur `X`+`obs`+`var` und Oviedo rechnet selbst.
   → **Erste Entscheidung (Pablo):** optional im Mediator selbst (`compute_tsne`,
   Default `false` in `POST /export/anndata` — bewusst konservativ, siehe Offener-Punkt-
   Charakter dieser Frage), via scikit-learn (`expression.py::compute_tsne`).
3. **Genumfang:** alle ~20k Gene oder ein Subset (Oviedo nutzte den
   Cancer-Gene-Census-Filter)? Beeinflusst Größe/Performance stark.
   → **Erste Entscheidung (Pablo):** kein Default-Filter (alle Gene aus den gelieferten
   Dateien); `POST /export/anndata` nimmt optional `gene_ids` als Whitelist entgegen.
4. **Übergabeweg des `.h5ad`:** Datei-Pfad, Download-Endpoint oder Volume — wie bekommt
   der Prototyp/das Oviedo-Frontend die Datei?
   → **Erste Entscheidung (Pablo):** Download-Endpoint (`GET
   /export/anndata/download/{filename}`), passend zum bestehenden REST-Stil des Mediators.

## 6) Definition of Done
- **Julian:** Manifest+Download liefern für ein TCGA-Projekt die Expression-Files je Probe
  + Feature-IDs + Proben↔Case-Zuordnung; Test gegen echte GDC-Files (klein, z. B.
  TCGA-BRCA size 5). `to_anndata` bleibt bewusst `NotImplementedError`. **Status: erledigt**
  — `GDCWrapper.download_expression_files()` (`wrappers/gdc/client.py`) filtert das
  Manifest auf `data_type`/`experimental_strategy` je Assay (`build_expression_filters`,
  `EXPRESSION_ASSAYS` = `rna_seq`/`mirna_seq`), lädt via `download_via_gdc_client` und
  liefert `sample_files`/`sample_case_map`/`sample_types` + `quantification_columns`
  (`id_column`/`value_column`/`label_column` je Assay) — direkt kompatibel zu
  `expression.assemble_matrix`/`build_obs` auf Mediator-Seite. Proben-Zuordnung
  (`extract_sample_case_rows`) live gegen die echte GDC-API verifiziert (2026-08-31):
  `files.cases.samples.sample_id` liefert exakt dieselbe Sample-UUID wie
  `cases.samples.sample_id`, auf die Pablos `db:Sample`-Mapping aufsetzt — die
  Proben-IDs beider Endpunkte sind also konsistent verknüpfbar. `to_anndata` bleibt
  `NotImplementedError`; `/export/anndata` liefert weiterhin einen 503-Fehler, solange
  `gdc-client` im Container nicht installiert ist (lokal ohne `gdc-client` getestet:
  `download`-Status `"not_run"`, `sample_case_map`/`sample_types` trotzdem vollständig).
- **Pablo:** `/export/anndata` erzeugt ein valides `.h5ad`, das mit `scanpy.read_h5ad()`
  öffnet und `X`, vollständige `obs` (alle Oviedo-Felder aus dem Wissensnetz), `var` und
  — falls entschieden — `obsm`-tSNE enthält. **Status: erledigt** — siehe
  `mediator/app/semantic/expression.py` (Assemblierung/Serialisierung) und
  `POST /export/anndata` / `GET /export/anndata/download/{filename}` in
  `mediator/app/main.py`. Live gegen die echte GDC-API getestet (Metadaten-Suche +
  Manifest-Bau); die Zusammenbau-/Export-Pipeline zusätzlich mit einer echten,
  live geladenen GDC-STAR-Gene-Counts-Datei formatverifiziert.
- **Gemeinsam:** ein Referenz-`.h5ad` für TCGA-BRCA (klein) als Fixture, analog zu
  `cases_brca_sample.*`, als Grundlage für die MP-lite-Integration. **Teilweise erledigt**
  — `mediator/sample_data/tcga_brca_sample.h5ad` (4 Proben × 5 Gene: BRCA1/CA9/GAPDH/
  TP53/SAA1, erzeugt aus `mediator/sample_data/expression/*.tsv` +
  `cases_brca_sample.json` via `mediator/scripts/example_expression_to_anndata.py`).
  Wie bei `cases_brca_sample.json` **synthetische, keine echten Patientendaten** — sobald
  Julians Wrapper-Teil steht, sollte dieselbe Fixture aus echten kleinen GDC-Files
  neu gezogen werden (analog zu `example_gdc_to_rdf.py`/`cases_brca_sample.ttl`).

## 7) Grenze
Wrapper/Mediator werden von der Wissensnetz-Seite nicht angefasst. Das Wissensnetz liefert
`obs`/`var`-Anreicherung über SPARQL und integriert das fertige `.h5ad` anschließend in
MP-lite. Die Matrix selbst bleibt außerhalb des RDF-Stores.
