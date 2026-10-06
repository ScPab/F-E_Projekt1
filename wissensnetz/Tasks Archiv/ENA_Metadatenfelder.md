# ENA (European Nucleotide Archive) — Metadatenfelder (Labels)

> Referenzliste aller Metadaten-/Returnable Fields aus dem **ENA Metadata Model**, organisiert nach dessen sechs Kernobjekten: **Study**, **Sample**, **Experiment**, **Run**, **Analysis**, **Submission**. Feldnamen entsprechen den `columnId`-Werten der ENA **Portal API** (`GET /returnFields`), wie sie auch in der Advanced Search und im `filereport`-Endpoint verwendet werden.
>
> Quellen: [ENA Metadata Model](https://ena-docs.readthedocs.io/en/latest/meta_01.html) · [ENA Portal API – Returnable Fields](https://www.ebi.ac.uk/ena/portal/api/returnFields?dataPortal=ena&format=tsv&result=read_run) · [ENA Portal API Doku](https://www.ebi.ac.uk/ena/portal/api/doc)

---

## Study

- `study_accession`
- `secondary_study_accession`
- `study_alias`
- `study_title`
- `center_name`
- `broker_name`
- `first_public`
- `last_updated`
- `project_name`
- `secondary_project`

## Sample

> Samples sind mit **Checklists** assoziiert (z. B. `ERC000011` Standard-Checklist, `ERC000033` Virus-Pathogen-Checklist), die zusätzlich definieren, welche Felder für einen bestimmten Sample-Typ Pflicht sind. Die folgende Liste deckt die verbreitetsten, checklist-übergreifenden Felder ab.

- `sample_accession`
- `secondary_sample_accession`
- `sample_alias`
- `sample_title`
- `sample_description`
- `sample_material`
- `sample_capture_status`
- `sample_collection`
- `sample_prep_interval`, `sample_prep_interval_units`
- `sample_storage`, `sample_storage_processing`
- `checklist` *(verwendete ENA-Checklist)*
- `ncbi_reporting_standard` *(verwendetes NCBI BioSample Package)*
- `tax_id`
- `scientific_name`
- `tax_lineage`
- `taxonomic_classification`
- `taxonomic_identity_marker`
- `strain`, `sub_strain`, `sub_species`
- `serotype`, `serovar`
- `isolate`
- `cultivar`, `ecotype`, `variety`
- `mating_type`
- `host`, `host_scientific_name`, `host_tax_id`
- `host_body_site`, `host_genotype`, `host_gravidity`, `host_growth_conditions`, `host_phenotype`, `host_sex`, `host_status`
- `submitted_host_sex`
- `sex`
- `age`
- `dev_stage`
- `cell_line`, `cell_type`
- `tissue_type`, `tissue_lib`
- `disease`
- `isolation_source`
- `environmental_sample`
- `environment_biome`, `environment_feature`, `environment_material`
- `environmental_medium`
- `broad_scale_environmental_context`, `local_environmental_context`
- `germline`
- `identified_by`, `collected_by`
- `collection_date`, `collection_date_start`, `collection_date_end`
- `country`
- `location`, `location_start`, `location_end`
- `lat`, `lon`
- `altitude`, `elevation`, `depth`
- `salinity`, `temperature`, `ph`
- `marine_region`
- `sampling_campaign`, `sampling_platform`, `sampling_site`
- `bio_material`, `culture_collection`, `specimen_voucher`

## Experiment

- `experiment_accession`
- `experiment_alias`
- `experiment_title`
- `experiment_target`
- `experimental_factor`
- `experimental_protocol`
- `control_experiment`
- `protocol_label`
- `investigation_type`
- `target_gene`
- `instrument_platform`
- `instrument_model`
- `library_name`
- `library_layout` *(SINGLE/PAIRED)*
- `library_strategy` *(z. B. WGS, RNA-Seq, ChIP-Seq)*
- `library_source` *(z. B. GENOMIC, TRANSCRIPTOMIC)*
- `library_selection` *(z. B. RANDOM, PCR)*
- `faang_library_selection`
- `library_construction_protocol`, `library_gen_protocol`
- `library_max_fragment_size`, `library_min_fragment_size`
- `library_pcr_isolation_protocol`
- `library_prep_date`, `library_prep_date_format`
- `library_prep_latitude`, `library_prep_longitude`, `library_prep_location`
- `nominal_length`, `nominal_sdev`
- `extraction_protocol`
- `bisulfite_protocol`
- `cage_protocol`
- `chip_ab_provider`, `chip_protocol`, `chip_target`
- `dnase_protocol`
- `hi_c_protocol`
- `pcr_isolation_protocol`
- `restriction_enzyme`, `restriction_enzyme_target_sequence`, `restriction_site`
- `rna_integrity_num`
- `rna_prep_3_protocol`, `rna_prep_5_protocol`
- `rna_purity_230_ratio`, `rna_purity_280_ratio`
- `rt_prep_protocol`
- `transposase_protocol`
- `sequencing_method`
- `sequencing_date`, `sequencing_date_format`
- `sequencing_location`, `sequencing_longitude`
- `sequencing_primer_catalog`, `sequencing_primer_lot`, `sequencing_primer_provider`

## Run

- `run_accession`
- `run_alias`
- `run_date`
- `read_count`
- `base_count`
- `read_strand`
- `fastq_bytes`, `fastq_md5`, `fastq_ftp`, `fastq_aspera`, `fastq_galaxy`, `fastq_file_role`
- `sra_bytes`, `sra_md5`, `sra_ftp`, `sra_aspera`, `sra_galaxy`, `sra_file_role`
- `submitted_bytes`, `submitted_md5`, `submitted_ftp`, `submitted_aspera`, `submitted_galaxy`, `submitted_format`, `submitted_file_role`, `submitted_read_type`
- `bam_bytes`, `bam_md5`, `bam_ftp`, `bam_aspera`, `bam_galaxy`, `bam_file_role`
- `file_location`

## Analysis

> Analysis-Objekte enthalten sekundäre Analyseergebnisse (z. B. Genom-Assemblies, Varianten-Calls) abgeleitet aus Run-Daten.

- `analysis_accession`
- `analysis_alias`
- `analysis_title`
- `analysis_type` *(z. B. SEQUENCE_ASSEMBLY, SEQUENCE_VARIATION)*
- `assembly_quality`
- `assembly_software`
- `binning_software`
- `completeness_score`
- `contamination_score`
- `aligned`
- `submitted_bytes`, `submitted_md5`, `submitted_ftp`, `submitted_aspera`, `submitted_galaxy` *(Analyse-Ergebnisdateien)*

## Submission / Administrativ

- `submission_accession`
- `submission_tool`
- `status`
- `datahub` *(DCC-Datahub-Name, für private Submissions)*
- `tag` *(Klassifikations-Tags)*
- `first_created`
- `surveillance_target`

---

## Hinweis: Objektbeziehungen

Die ENA-Objekte bilden eine Hierarchie: **Study** → **Sample** (n:m über Experiments) → **Experiment** → **Run** (Rohdaten) bzw. **Analysis** (abgeleitete Ergebnisse). Ein Sample ist dabei immer mit genau einem Taxon (`tax_id`) verknüpft, kann aber in mehreren Experiments/Studies wiederverwendet werden. Für automatisierten Abruf ist der **ENA Portal API**-Endpoint `/search` (mit `result=read_run|sample|study|analysis` und frei wählbarem `fields`-Parameter) der zentrale Einstiegspunkt — die obigen Felder sind direkt als `fields`-Werte nutzbar.
