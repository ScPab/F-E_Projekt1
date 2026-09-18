# GDC / TCGA — Klinische Datenfelder (Labels)

> Referenzliste aller klinischen Properties aus dem offiziellen **GDC Data Dictionary**, organisiert nach den Knoten (Nodes), wie sie auch in der GDC-API auftauchen (z. B. `/cases?expand=demographic,diagnoses,exposures,family_histories,follow_ups`).
>
> Feldnamen sind im Original-`snake_case` angegeben, da dies die tatsächlichen API-Property-Namen sind. **Fett markierte Felder** sind laut GDC Data Dictionary Pflichtfelder (*Required*).
>
> Quelle: [GDC Clinical Data Table](https://gdc.cancer.gov/clinical-data-table) · Details/Permissible Values pro Feld: [GDC Data Dictionary Viewer](https://docs.gdc.cancer.gov/Data_Dictionary/viewer/)

---

## Demographic

- `age_at_index`
- `age_is_obfuscated`
- `cause_of_death`
- `cause_of_death_source`
- `country_of_birth`
- `country_of_residence_at_enrollment`
- `days_to_birth`
- `days_to_death`
- `education_level`
- **`ethnicity`**
- `marital_status`
- `occupation_duration_years`
- `population_group`
- **`race`**
- **`sex_at_birth`** *(GDC-Pendant zu "gender")*
- **`vital_status`**
- `year_of_birth`
- `year_of_birth_range`
- `year_of_death`

## Diagnosis

- `adrenal_hormone`
- **`age_at_diagnosis`**
- `ajcc_clinical_m`, `ajcc_clinical_n`, `ajcc_clinical_stage`, `ajcc_clinical_t`
- `ajcc_pathologic_m`, `ajcc_pathologic_n`, `ajcc_pathologic_stage`, `ajcc_pathologic_t`
- `ajcc_serum_tumor_markers`
- `ajcc_staging_system_edition`
- `ann_arbor_b_symptoms`, `ann_arbor_b_symptoms_described`, `ann_arbor_b_symptoms_described_array`
- `ann_arbor_clinical_stage`
- `ann_arbor_extranodal_involvement`
- `ann_arbor_pathologic_stage`
- `best_overall_response`
- `burkitt_lymphoma_clinical_variant`
- `calgb_risk_group`
- `cancer_detection_method`
- `child_pugh_classification`
- `clark_level`
- `classification_of_tumor`
- `cog_liver_stage`
- `cog_neuroblastoma_risk_group`
- `cog_renal_stage`
- `cog_rhabdomyosarcoma_risk_group`
- `contiguous_organ_invaded`
- `days_to_best_overall_response`
- `days_to_diagnosis`
- `days_to_last_follow_up`
- `days_to_last_known_disease_status`
- `days_to_recurrence`
- **`diagnosis_is_primary_disease`**
- `double_expressor_lymphoma`
- `double_hit_lymphoma`
- `eln_risk_classification`
- `enneking_msts_grade`, `enneking_msts_metastasis`, `enneking_msts_stage`, `enneking_msts_tumor_site`
- `ensat_clinical_m`
- `ensat_pathologic_n`, `ensat_pathologic_stage`, `ensat_pathologic_t`
- `esophageal_columnar_dysplasia_degree`
- `esophageal_columnar_metaplasia_present`
- `fab_morphology_code`
- `figo_stage`
- `figo_staging_edition_year`
- `first_symptom_longest_duration`
- `first_symptom_prior_to_diagnosis`
- `gastric_esophageal_junction_involvement`
- `gleason_grade_group`, `gleason_grade_tertiary`
- `gleason_patterns_percent`
- `gleason_score`
- `goblet_cells_columnar_mucosa_present`
- `icd_10_code`
- `igcccg_stage`
- `inpc_grade`
- `inpc_histologic_group`
- `inrg_stage`
- `inss_stage`
- `international_prognostic_index`
- `irs_group`
- `irs_stage`
- `ishak_fibrosis_score`
- `iss_stage`
- `last_known_disease_status`
- `laterality`
- `margin_distance`
- `margins_involved_site`
- `masaoka_stage`
- `max_tumor_bulk_site`
- `medulloblastoma_molecular_classification`
- `melanoma_known_primary`
- `metastasis_at_diagnosis`
- `method_of_diagnosis`
- `mitosis_karyorrhexis_index`
- **`morphology`**
- `ovarian_specimen_status`
- `ovarian_surface_involvement`
- `pediatric_kidney_staging`
- `peritoneal_fluid_cytological_status`
- **`primary_diagnosis`**
- `primary_gleason_grade`
- `prior_malignancy`
- `prior_treatment`
- `progression_or_recurrence`
- `residual_disease`
- `satellite_nodule_present`
- `secondary_gleason_grade`
- **`site_of_resection_or_biopsy`**
- `sites_of_involvement`, `sites_of_involvement_count`
- `supratentorial_localization`
- `synchronous_malignancy`
- **`tissue_or_organ_of_origin`**
- `tumor_burden`
- `tumor_confined_to_organ_of_origin`
- `tumor_depth`
- `tumor_focality`
- `tumor_grade`, `tumor_grade_category`
- `tumor_of_origin`
- `tumor_regression_grade`
- `uicc_clinical_m`, `uicc_clinical_n`, `uicc_clinical_stage`, `uicc_clinical_t`
- `uicc_pathologic_m`, `uicc_pathologic_n`, `uicc_pathologic_stage`, `uicc_pathologic_t`
- `uicc_staging_system_edition`
- `ulceration_indicator`
- `weiss_assessment_findings`, `weiss_assessment_score`
- `who_cns_grade`
- `who_nte_grade`
- `wilms_tumor_histologic_subtype`
- `year_of_diagnosis`

## Exposure

- `age_at_last_exposure`
- `age_at_onset`
- `alcohol_days_per_week`
- `alcohol_drinks_per_day`
- `alcohol_frequency`
- `alcohol_history`
- `alcohol_intensity`
- `alcohol_type`
- `asbestos_exposure_type`
- `chemical_exposure_type`
- `cigarettes_per_day`
- `environmental_tobacco_smoke_exposure`
- `exposure_duration`, `exposure_duration_hrs_per_day`, `exposure_duration_years`
- `exposure_source`
- `exposure_type`
- `occupation_duration_years`
- `occupation_type`
- `pack_years_smoked`
- `parent_with_radiation_exposure`
- `secondhand_smoke_as_child`
- `smoking_frequency`
- `time_between_waking_and_first_smoke`
- `tobacco_smoking_onset_year`
- `tobacco_smoking_quit_year`
- `tobacco_smoking_status`
- `type_of_smoke_exposure`
- `type_of_tobacco_used`
- `use_per_day`

## Family History

- `relationship_age_at_diagnosis`
- `relationship_primary_diagnosis`
- `relationship_sex_at_birth`
- `relationship_type`
- `relative_deceased`
- `relative_smoker`
- `relative_with_cancer_history`
- `relatives_with_cancer_history_count`

## Molecular Test

- `aa_change`
- `aneuploidy`
- `antigen`
- `biospecimen_type`
- `biospecimen_volume`
- `blood_test_normal_range_lower`, `blood_test_normal_range_upper`
- `cell_count`
- `chromosomal_translocation`
- `chromosome`, `chromosome_arm`
- `clonality`
- `copy_number`
- `cytoband`
- `days_to_test`
- `exon`
- **`gene_symbol`**
- `histone_family`, `histone_variant`
- `hpv_strain`
- `intron`
- `laboratory_test`
- `loci_abnormal_count`
- `loci_count`
- `locus`
- `mismatch_repair_mutation`
- `mitotic_count`, `mitotic_total_area`
- **`molecular_analysis_method`**
- `molecular_consequence`
- `mutation_codon`
- `pathogenicity`
- `ploidy`
- `second_exon`
- `second_gene_symbol`
- `specialized_molecular_test`
- `staining_intensity_scale`, `staining_intensity_value`
- `test_analyte_type`
- **`test_result`**
- `test_units`
- `test_value`, `test_value_range`
- `timepoint_category`
- `transcript`
- `variant_origin`
- `variant_type`
- `zygosity`

## Other Clinical Attribute

- `aids_risk_factors`
- `bmi`
- `body_surface_area`
- `cd4_count`
- `cdc_hiv_risk_factors`
- `comorbidities`
- `comorbidity_method_of_diagnosis`
- `days_to_comorbidity`
- `days_to_risk_factor`
- `diabetes_treatment_type`
- `dlco_ref_predictive_percent`
- `exercise_frequency_weekly`
- `eye_color`
- `fertility_history`
- `fev1_fvc_post_bronch_percent`, `fev1_fvc_pre_bronch_percent`
- `fev1_ref_post_bronch_percent`, `fev1_ref_pre_bronch_percent`
- `haart_treatment_indicator`
- `height`
- `hepatitis_sustained_virological_response`
- `hiv_viral_load`
- `hormonal_contraceptive_type`, `hormonal_contraceptive_use`
- `hormonal_replacement_therapy_status`
- `hormone_replacement_therapy_type`
- `hysterectomy_margins_involved`
- `hysterectomy_type`
- `immunosuppressive_treatment_type`
- `menopause_status`
- `myasthenia_gravis_classification`
- `nadir_cd4_count`
- `nononcologic_therapeutic_agents`
- `number_of_pregnancies`
- `oxygen_use_indicator`, `oxygen_use_type`
- `pancreatitis_onset_year`
- `pregnancy_outcome`
- `pregnant_at_diagnosis`
- `premature_at_birth`
- `reflux_treatment_type`
- `risk_factor_method_of_diagnosis`
- `risk_factor_treatment`
- `risk_factors`
- `treatment_frequency`
- `undescended_testis_corrected`, `undescended_testis_corrected_age_range`, `undescended_testis_corrected_laterality`, `undescended_testis_corrected_method`
- `undescended_testis_history`, `undescended_testis_history_laterality`
- `viral_hepatitis_serology_tests`
- `weeks_gestation_at_birth`
- `weight`

## Pathology Detail

- `additional_pathology_findings`
- `anaplasia_present`, `anaplasia_present_type`
- `bone_marrow_malignant_cells`
- `breslow_thickness`, `breslow_thickness_category`
- `circumferential_resection_margin`
- `columnar_mucosa_present`
- `consistent_pathology_review`
- `days_to_pathology_detail`
- `dysplasia_degree`, `dysplasia_type`
- `epithelioid_cell_percent_range`
- `extracapsular_extension`, `extracapsular_extension_present`
- `extranodal_extension`
- `extraocular_nodule_size`
- `extrascleral_extension_present`
- `extrathyroid_extension`
- `greatest_tumor_dimension`
- `gross_tumor_weight`
- `histologic_progression_type`
- `intratubular_germ_cell_neoplasia_present`
- `largest_extrapelvic_peritoneal_focus`
- `lymph_node_dissection_method`, `lymph_node_dissection_site`
- `lymph_node_involved_site`, `lymph_node_involvement`
- `lymph_nodes_positive`, `lymph_nodes_removed`, `lymph_nodes_tested`
- `lymphatic_invasion_present`
- `margin_status`
- `measurement_type`, `measurement_unit`
- `metaplasia_present`
- `micrometastasis_present`
- `morphologic_architectural_pattern`
- `necrosis_percent`, `necrosis_present`
- `non_nodal_regional_disease`
- `non_nodal_tumor_deposits`
- `number_proliferating_cells`
- `percent_tumor_invasion`, `percent_tumor_nuclei`
- `perineural_invasion_present`
- `peripancreatic_lymph_nodes_positive`, `peripancreatic_lymph_nodes_tested`
- `prcc_type`
- `prostatic_chips_positive_count`, `prostatic_chips_total_count`
- `prostatic_involvement_percent`
- `residual_tumor`, `residual_tumor_measurement`
- `rhabdoid_percent`, `rhabdoid_present`
- `sarcomatoid_percent`, `sarcomatoid_present`
- `spindle_cell_percent_range`
- `transglottic_extension`
- `tumor_basal_diameter`
- `tumor_burden`
- `tumor_depth_descriptor`, `tumor_depth_measurement`
- `tumor_infiltrating_lymphocytes`, `tumor_infiltrating_macrophages`
- `tumor_largest_dimension_diameter`
- `tumor_length_measurement`
- `tumor_level_prostate`
- `tumor_shape`
- `tumor_thickness`
- `tumor_width_measurement`
- `vascular_invasion_present`, `vascular_invasion_type`
- `zone_of_origin_prostate`

## Treatment

- `chemo_concurrent_to_radiation`
- `clinical_trial_indicator`
- `course_number`
- `days_to_treatment_end`, `days_to_treatment_start`
- `drug_category`
- `embolic_agent`
- `initial_disease_status`
- `lesions_treated_number`
- `margin_distance`, `margin_status`, `margins_involved_site`
- `number_of_cycles`, `number_of_fractions`
- `prescribed_dose`, `prescribed_dose_units`
- `pretreatment`
- `protocol_identifier`
- `radiosensitizing_agent`
- `reason_treatment_ended`, `reason_treatment_not_given`
- `regimen_or_line_of_therapy`
- `residual_disease`
- `route_of_administration`
- `therapeutic_agents`
- `therapeutic_levels_achieved`
- `therapeutic_target_level`
- `treatment_anatomic_sites`
- `treatment_dose`, `treatment_dose_max`, `treatment_dose_units`
- `treatment_duration`
- `treatment_effect`, `treatment_effect_indicator`
- `treatment_intent_type`
- `treatment_or_therapy`
- `treatment_outcome`, `treatment_outcome_duration`
- `treatment_type`
- **`treatment_type_administered`**

## Follow Up

> ⚠️ Diese Liste war an der Quelle (Webseite) abgeschnitten und ist unvollständig. Für die vollständige Liste im [GDC Data Dictionary Viewer](https://docs.gdc.cancer.gov/Data_Dictionary/viewer/#?view=table-definition-view&id=follow_up) nachschlagen.

- `adverse_event`, `adverse_event_grade`
- `barretts_esophagus_goblet_cells_present`
- `cause_of_response`
- `days_to_adverse_event`
- `days_to_first_event`
- **`days_to_follow_up`**
- `days_to_imaging`
- `days_to_progression`, `days_to_progression_free`
- `days_to_recurrence`
- `discontiguous_lesion_count`
- `disease_response`
- `ecog_performance_status`
- `evidence_of_progression_type`
- `evidence_of_recurrence_type`
- `first_event`
- `histologic_progression`
- `history_of_tumor`, `history_of_tumor_type`
- *(weitere Felder — Liste an der Quelle abgeschnitten)*

---

## Hinweis: Nicht-klinische Node-Kategorien

Diese Liste deckt nur den **klinischen** Teil des GDC Data Dictionary ab. Daneben existieren separate Node-Kategorien, die für die DataBridge-Architektur ebenfalls relevant sein dürften:

- **Biospecimen**: `sample`, `portion`, `analyte`, `aliquot` — Gewebe-/Proben-Metadaten
- **Files / Administrativ**: `data_type`, `data_category`, `experimental_strategy`, `platform`, u. a. — Metadaten zu den eigentlichen Dateien (FASTQ, BAM, VCF, ...)

Diese sind bei Bedarf separat aus dem [GDC Data Dictionary Viewer](https://docs.gdc.cancer.gov/Data_Dictionary/viewer/) zu extrahieren.
