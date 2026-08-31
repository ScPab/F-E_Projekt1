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
2. **Wer berechnet die tSNE (`obsm`)?** Im Oviedo-Original vorab trainiert
   (`pancancer_morphing.hdf`). Vorschlag: ein Scanpy-Vorverarbeitungsschritt
   (Mediator oder separates Skript), Ergebnis in `obsm`. Alternativ liefert DataBridge
   nur `X`+`obs`+`var` und Oviedo rechnet selbst.
3. **Genumfang:** alle ~20k Gene oder ein Subset (Oviedo nutzte den
   Cancer-Gene-Census-Filter)? Beeinflusst Größe/Performance stark.
4. **Übergabeweg des `.h5ad`:** Datei-Pfad, Download-Endpoint oder Volume — wie bekommt
   der Prototyp/das Oviedo-Frontend die Datei?

## 6) Definition of Done
- **Julian:** Manifest+Download liefern für ein TCGA-Projekt die Expression-Files je Probe
  + Feature-IDs + Proben↔Case-Zuordnung; Test gegen echte GDC-Files (klein, z. B.
  TCGA-BRCA size 5). `to_anndata` bleibt bewusst `NotImplementedError`.
- **Pablo:** `/export/anndata` erzeugt ein valides `.h5ad`, das mit `scanpy.read_h5ad()`
  öffnet und `X`, vollständige `obs` (alle Oviedo-Felder aus dem Wissensnetz), `var` und
  — falls entschieden — `obsm`-tSNE enthält.
- **Gemeinsam:** ein Referenz-`.h5ad` für TCGA-BRCA (klein) als Fixture, analog zu
  `cases_brca_sample.*`, als Grundlage für die MP-lite-Integration.

## 7) Grenze
Wrapper/Mediator werden von der Wissensnetz-Seite nicht angefasst. Das Wissensnetz liefert
`obs`/`var`-Anreicherung über SPARQL und integriert das fertige `.h5ad` anschließend in
MP-lite. Die Matrix selbst bleibt außerhalb des RDF-Stores.
