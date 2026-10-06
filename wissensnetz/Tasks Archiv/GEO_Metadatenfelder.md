# GEO (Gene Expression Omnibus) — Metadatenfelder (Labels)

> Referenzliste aller Metadaten-Felder von GEO (NCBI), organisiert nach den vier Kern-Entitäten des GEO-Datenmodells: **Series (GSE)**, **Sample (GSM)**, **Platform (GPL)** und dem kuratierten, aber inzwischen legacy **DataSet (GDS)**. Feldnamen entsprechen den offiziellen SOFT/MINiML-Tags (ohne führendes `!Series_`/`!Sample_`/`!Platform_`) bzw. den Spaltennamen aus GEOmetadb (SQLite-Abbild der GEO-Datenbank), die 1:1 den SOFT-Feldern entsprechen.
>
> Quellen: [GEO SOFT/MINiML-Format](https://www.ncbi.nlm.nih.gov/geo/info/soft2.html) · [GEOmetadb (Bioconductor)](https://bioconductor.org/packages/release/bioc/vignettes/GEOmetadb/inst/doc/GEOmetadb.html) · [GEOparse (Python)](https://geoparse.readthedocs.io/)

---

## Series (GSE) — die Studie/Experimentserie

- `title`
- `gse` *(Accession, z. B. GSE12345)*
- `status`
- `submission_date`
- `last_update_date`
- `pubmed_id`
- `summary`
- `type` *(z. B. "Expression profiling by high throughput sequencing")*
- `contributor`
- `web_link`
- `overall_design`
- `repeats`
- `repeats_sample_list`
- `variable`
- `variable_description`
- `contact` *(bzw. aufgeschlüsselt: `contact_name`, `contact_email`, `contact_institute`, `contact_department`, `contact_address`, `contact_city`, `contact_zip_postal_code`, `contact_country`)*
- `supplementary_file`
- `platform_id` *(Referenz auf zugehörige GPL)*
- `sample_id` / `sample_taxid` *(Referenzen auf zugehörige GSM-Liste)*

## Sample (GSM) — die einzelne Probe/Hybridisierung

- `gsm` *(Accession, z. B. GSM123456)*
- `title`
- `gse` *(Referenz auf übergeordnete Series)*
- `gpl` *(Referenz auf verwendete Platform)*
- `status`
- `submission_date`
- `last_update_date`
- `type` *(z. B. "SRA", "RNA")*
- `channel_count`
- `source_name_ch1`, `source_name_ch2`
- `organism_ch1`, `organism_ch2`
- `taxid_ch1`, `taxid_ch2`
- `characteristics_ch1`, `characteristics_ch2` *(freie Key-Value-Paare, z. B. "age: 45", "tissue: liver")*
- `molecule_ch1`, `molecule_ch2` *(z. B. "total RNA")*
- `label_ch1`, `label_ch2`
- `treatment_protocol_ch1`, `treatment_protocol_ch2`
- `extract_protocol_ch1`, `extract_protocol_ch2`
- `label_protocol_ch1`, `label_protocol_ch2`
- `hyb_protocol`
- `scan_protocol`
- `description`
- `data_processing`
- `data_row_count`
- `supplementary_file`
- `contact` *(bzw. `contact_name`, `contact_institute`, `contact_address`, `contact_city`, `contact_zip_postal_code`, `contact_country`, `contact_department`)*

> ⚠️ Wichtiger Hinweis für die Datenintegration: `characteristics_ch1`/`_ch2` sind **unstrukturierter Freitext** ohne kontrolliertes Vokabular — Submitter können z. B. "diagnosis" oder "disease state" völlig frei benennen. Es gibt kein festes Set an klinischen Labels wie bei GDC/TCGA; jede Series definiert ihre eigenen Characteristics-Keys.

## Platform (GPL) — das Array/Sequenzierungsgerät

- `gpl` *(Accession, z. B. GPL570)*
- `title`
- `status`
- `submission_date`
- `last_update_date`
- `technology` *(z. B. "high-throughput sequencing", "in situ oligonucleotide")*
- `distribution`
- `organism`
- `manufacturer`
- `manufacture_protocol`
- `coating`
- `catalog_number`
- `support`
- `description`
- `web_link`
- `contact`
- `data_row_count`
- `supplementary_file`
- `bioc_package` *(Bioconductor-Annotationspaket, falls vorhanden)*

## DataSet (GDS) — kuratierter Legacy-Datensatz

> GDS ist ein von NCBI-Kuratoren zusätzlich aufbereiteter, vergleichbarer Datensatz (i. d. R. eine Teilmenge einer GSE mit vereinheitlichten Subsets/Faktoren). Wird von NCBI nicht mehr aktiv für neue Submissions gepflegt, ist aber für viele ältere Studien noch die einzige kuratierte Quelle.

- `gds` *(Accession, z. B. GDS1234)*
- `title`
- `description`
- `type`
- `pubmed_id`
- `gpl` *(Referenz auf Platform)*
- `platform_organism`
- `platform_technology_type`
- `feature_count`
- `sample_organism`
- `sample_type`
- `channel_count`
- `sample_count`
- `value_type`
- `gse` *(Referenz auf zugrunde liegende Series)*
- `order`
- `update_date`
- **`gds_subset`** (verknüpfte Tabelle mit den experimentellen Faktoren/Gruppierungen je Sample): `subset_id`, `dataset_id`, `description`, `sample_id`, `type` *(z. B. "disease state", "age", "tissue")*

---

## Hinweis zur Datenmodell-Struktur

GEO ist bewusst **schema-flexibel**: nur die strukturellen Felder oben (Series/Sample/Platform-Metadaten) sind fest, die eigentlichen biologisch-klinischen Annotationen stecken in `characteristics_ch1` als freier Text. Für automatisierte Pipelines bedeutet das: Parsing/Normalisierung der `characteristics`-Keys ist ein eigener Verarbeitungsschritt (kein festes Ziel-Schema wie bei GDC), z. B. über Text-Mining/LLM-basierte Normalisierung oder Mapping auf Ontologien.
