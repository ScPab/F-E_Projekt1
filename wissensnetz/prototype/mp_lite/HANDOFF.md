# Hand-off an Julian (Wrapper) & Pablo (Mediator): MP-lite an Oviedo angleichen

Dieses Dokument fasst zusammen, was in **euren** Komponenten (`wrappers/` bzw.
`mediator/`) noch passieren muss, damit MP-lite die Oviedo-Funktionalität voll
ausspielt. Es ersetzt die früheren Einzeldokumente `HANDOFF_oviedo_felder.md`
und `HANDOFF_morphing_daten.md`.

## Stand auf der Wissensnetz-Seite (fertig — nichts weiter nötig)
Aufgaben 5–7 sind umgesetzt (Marcel, nur `wissensnetz/` + `scripts/`):
- **Hover (Aufg. 5):** MP-lite zeigt die volle Oviedo-Feldliste; fehlende Werte
  als `"--"`. TBox-Properties deklariert, `case_context()` fragt sie tolerant ab.
- **Morphing (Aufg. 6):** ein Slider pro Variable, `Σ aᵢ·E[i]`,
  `a = softmax(10·slider)`, clientseitig (CustomJS). **Datengetrieben:** hat eine
  Variable ≥2 verschiedene Nicht-Null-Werte, aktiviert sich ihr Slider von selbst;
  sonst erscheint er deaktiviert (ehrliche Datenlücke im UI).
- **Pancancer (Aufg. 7):** alle 32 TCGA-Kohorten via `load_gdc.py --pancancer`;
  MP-lite liest echte Fälle (`enrichment.all_cases`) und färbt nach Krebsart.

**Wichtig:** Weil jetzt die echte Pancancer-Kohorte im Graphen liegt, sind
`cancer`, `gender`, `primary_diagnosis` bereits variantenreich → diese Slider
morphen schon. Die **übrigen** klinischen Felder bleiben `"--"` bzw. ihre Slider
deaktiviert, bis Wrapper + Mediator sie liefern. Genau das ist euer Teil.

Sobald ein Feld echt im Graphen steht, aktivieren sich Hover **und** der zugehörige
Morph-Slider **automatisch** — es ist dafür KEIN weiterer MP-lite-Code nötig, nur
Daten.

---

## Teil 1 — Klinische Oviedo-Felder befüllen

Zielreihenfolge im Hover (zur Erinnerung):
`Sample, cancer, type, race, gender, ethnicity, tumor_stage, morphology,
site_of_resection_or_biopsy, primary_diagnosis, has_metastasis, vital_status`.

Fehlend sind aktuell: `race, ethnicity, vital_status, tumor_stage, morphology,
site_of_resection_or_biopsy, has_metastasis` (sowie `type`, siehe Teil 2).

### 1a) Julian — GDC-Wrapper: Felder aus der GDC-API anfragen
Diese GDC-Felder zusätzlich in die Abfrage/Ausgabe aufnehmen, damit sie im
Case-JSON ankommen, das an den Mediator geht:

| Oviedo-Feld                   | GDC-Feld                                                |
|-------------------------------|---------------------------------------------------------|
| race                          | `demographic.race`                                      |
| ethnicity                     | `demographic.ethnicity`                                 |
| vital_status                  | `demographic.vital_status`                              |
| morphology                    | `diagnoses.morphology`                                  |
| site_of_resection_or_biopsy   | `diagnoses.site_of_resection_or_biopsy`                 |
| tumor_stage                   | `diagnoses.ajcc_pathologic_stage` (bzw. `tumor_stage`)  |
| has_metastasis                | `diagnoses.metastasis_at_diagnosis`                     |
| type (sample_type)            | `samples.sample_type` (→ Teil 2)                        |
| (cancer)                      | `project.disease_type` — optional; MP-lite leitet `cancer` schon aus `project.project_id` ab ("TCGA-PRAD" → "PRAD") |

### 1b) Pablo — Mediator: Felder als Tripel auf die (schon deklarierten) `db:`-Properties mappen
`TRANSFORM_CASE_FIELDS` (`mediator/app/main.py`) und `cases_to_graph`
(`mediator/app/semantic/mapping.py`) erweitern, sodass die neuen Felder auf diese
bereits in der TBox (`wissensnetz/ontology/databridge-core.ttl`) vorhandenen
Ziel-Properties geschrieben werden:

- Demographic → `db:race`, `db:ethnicity`, `db:vitalStatus`
- Diagnosis   → `db:tumorStage`, `db:morphology`, `db:siteOfResectionOrBiopsy`,
  `db:metastasisAtDiagnosis`

Danach die eingefrorene Fixture `wissensnetz/data/sample/cases_brca_sample.ttl`
**neu aus dem Mediator ziehen** (`mediator/scripts/example_gdc_to_rdf.py`) — sie
gehört dem Mediator-Mapping und wird im Wissensnetz nicht von Hand editiert.

**Definition of Done Teil 1:** nach `python scripts\load_gdc.py --pancancer`
tragen die Cases die neuen `db:`-Felder; `wissensnetz context <submitterId>` zeigt
race/ethnicity/vital_status/… ; im MP-lite-Hover stehen echte Werte statt `"--"`,
und die entsprechenden Morph-Slider werden aktiv.

---

## Teil 2 — `type` / `sample_type`: Wissensnetz-Seite fertig, nur Mediator offen

`type` (GDC `samples.sample_type`, z. B. "Primary Tumor" / "Solid Tissue Normal")
braucht eine Sample-/Biospecimen-Klasse im Modell. Die **Wissensnetz-Seite ist
jetzt komplett** (Aufgabe 8) — es fehlt **nur noch der Mediator-Schritt**, dann
zeigt `type` ohne weitere Wissensnetz-Änderung echte Werte.

Schritte (Reihenfolge; Owner in Klammern):
1. ✅ **erledigt** (Marcel/Wissensnetz) — Klasse `db:Sample` + ObjectProperty
   `db:hasSample`/`db:isSampleOf` (Case ↔ Sample) in `databridge-core.ttl`.
2. ✅ **erledigt** (Marcel/Wissensnetz) — Datatype-Property `db:sampleType`
   (`rdfs:domain db:Sample`, `xsd:string`).
3. ✅ **erledigt** (Pablo/Mediator) — `samples.sample_type` auf `db:sampleType`
   mappen: `TRANSFORM_CASE_FIELDS` (`mediator/app/main.py`) + `cases_to_graph`
   (`mediator/app/semantic/mapping.py`) müssen je Sample einen `db:Sample`-Knoten
   an den Case hängen (`db:hasSample`) und `samples.sample_type` als
   `db:sampleType`-Literal schreiben; danach die Fixture
   `wissensnetz/data/sample/cases_brca_sample.ttl` neu ziehen
   (`mediator/scripts/example_gdc_to_rdf.py`).
4. ✅ **erledigt** (Marcel/Wissensnetz) — `case_context()`/`all_cases()` lesen
   `db:hasSample`/`db:sampleType` (tolerant), MP-lite füllt `sample_type` daraus.

**Definition of Done Teil 2:** Sobald Schritt 3 steht, tragen die Cases
`db:hasSample`-Samples mit `db:sampleType`; MP-lite zeigt `type` im Hover mit
echten Werten und der `type`-Morph-Slider aktiviert sich automatisch (≥2 distinct
Werte). Bis dahin bleibt `type` = `"--"` (Slider deaktiviert) — **die
Wissensnetz-Seite ist bereit, kein weiterer MP-lite-Code nötig.**
F-E_Projekt1\wissensnetz\prototype\mp_lite\HANDOFF_oviedo_felder.md
---

## Teil 3 — Expressionsdaten integrieren (größere, gemeinsame Aufgabe)

Die Morph-Slider `genes`-tSNE, `miRNA`-tSNE sowie Einzelmarker (`miRNA-210-3p`,
`CA9`, `SAA1` …) existieren im Wissensnetz **noch gar nicht**. MP-lite nutzt an
ihrer Stelle derzeit synthetische Platzhalter-Layouts (`L0`/`L1`). Benötigt:

1. **Expressionsvektoren pro Probe** (DNA/miRNA) — der `anndata`/`.h5ad`-Teil der
   DataBridge-Architektur, aktuell nicht integriert (Wrapper `to_anndata` ist
   Platzhalter/`NotImplementedError`).
2. **Vorberechnete 2D-tSNE-Layouts** für genes und miRNA (im Oviedo-Original in
   `pancancer_morphing.hdf`, Spalten `genes_x/y`, `mirna_x/y`) — liefern `E[0]`/`E[1]`.
3. **Einzel-Marker-Spalten** (Ensembl-Gen- / MIMAT-miRNA-IDs) als Basis für
   lineare Encodings einzelner Marker.

### Offene Architekturfrage — zuerst im Team klären
Kommen Expressionswerte über den **Graphen** (Tripel/Literals an Case/Sample) oder
über einen **Seitenkanal** (h5ad direkt in den Prototyp, am RDF-Store vorbei)?
Das betrifft Wrapper, Mediator **und** Wissensnetz gemeinsam und ist Voraussetzung,
bevor die Expressions-Slider gebaut werden. → Bitte gemeinsam entscheiden, dann
Umsetzung planen. Dies ist die größte verbleibende Lücke Richtung „echte
Oviedo-Cancer-Map".

---

## Kurz-Checkliste

- [x] Julian: GDC-Wrapper fragt die 7 klinischen Felder (+ optional disease_type) an
      — kein Code-Änderung nötig, `GDCWrapper.query()`/`.search()` reichen `fields`
      generisch durch; live gegen die echte GDC-API verifiziert (2026-08-28):
      alle 7 Felder existieren im `cases`-Schema und liefern echte Werte, außer
      `diagnoses.tumor_stage` (existiert nicht — `diagnoses.ajcc_pathologic_stage`
      verwenden, siehe Feld-Tabelle oben).
- [x] Pablo: Mediator mappt sie auf `db:race/ethnicity/vitalStatus/tumorStage/
      morphology/siteOfResectionOrBiopsy/metastasisAtDiagnosis`; Fixture neu gezogen
      (`TRANSFORM_CASE_FIELDS` + `cases_to_graph` in `mediator/app/main.py` bzw.
      `mediator/app/semantic/mapping.py` erweitert; Beispieldaten in
      `mediator/sample_data/cases_brca_sample.json` um die neuen Felder ergänzt).
- [x] Marcel: `db:Sample`-Modell für `type` angelegt (Teil 2, Schritte 1/2/4 erledigt).
- [x] Pablo: Mediator mappt `samples.sample_type` → `db:hasSample`/`db:sampleType`; Fixture neu (Teil 2, Schritt 3).
- [ ] Team: Architekturentscheidung Expressionsdaten (Graph vs. h5ad-Seitenkanal, Teil 3).
