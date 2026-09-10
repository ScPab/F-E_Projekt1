# Hand-off an Pablo (Mediator): `obs`-Fallback auf die GDC-Projekt-ID

> **STATUS: bereits umgesetzt** (auf Marcels Wunsch direkt eingebaut, Commit-fähig). Dieses Dokument erklärt Pablo den Change in seiner Komponente `mediator/` — Diff in `app/semantic/expression.py::build_obs` und `app/main.py::export_anndata`. Funktion isoliert getestet.


## Problem (mit Daten belegt)
Die Pancancer-`.h5ad` (`POST /export/anndata`, 40 Proben) hat fast leere Klinik-
`obs`: `project_id`/`cancer` sind nur bei **7 von 40** Proben gefüllt (alle
„TCGA-LUAD"), `gender` bei 0, `vital_status` bei 7 — dagegen `sample_type` bei
**40/40**. MP-Lite färbt nach `obs["cancer"]`, also erscheinen 33 Proben grau und
die Legende zeigt nur eine Kohorte.

## Ursache
In `mediator/app/semantic/expression.py::build_obs` kommen `sample_type` aus der
GDC-Files-Abfrage (deshalb überall gefüllt), aber `project_id`/`cancer`/`gender`/…
**ausschließlich** aus dem Wissensnetz (`enrichment.all_cases()`), verknüpft über
`sample_case_map` (`sample_id -> submitter_id`) → `cases_by_submitter`. Die per
Export geholten Expressions-**Proben** gehören aber zu anderen Cases als die per
`load_gdc` in den Graphen geladenen — die Mengen überlappen kaum (hier nur 7 LUAD-
Cases). Fehlt der Case im Store, bleibt `case = {}` → `project_id=None` →
`cancer=None` → grau.

## Fix (klein, Mediator-seitig)
Die GDC-Projekt-ID **liegt pro Probe bereits vor** — der Endpoint fragt in
`export_anndata` (`app/main.py`) das Feld `cases.project.project_id` in
`file_fields` ab. Sie wird bisher nur für die Zuordnung genutzt, nicht für `obs`.

**Schritt 1 — im Endpoint (`app/main.py`, `export_anndata`)** neben
`sample_case_map` auch eine Projekt-Zuordnung aus denselben Treffern bauen:
```python
sample_project_map = {}  # sample_id -> project_id (aus GDC)
...
for hit in hits:
    case = (hit.get("cases") or [{}])[0]
    sample = (case.get("samples") or [{}])[0]
    sample_id = sample.get("sample_id") or file_id
    proj = (case.get("project") or {}).get("project_id")
    if proj:
        sample_project_map[sample_id] = proj
    # (submitter_id/sample_type wie bisher)
```
und an `build_obs` durchreichen:
```python
obs = expression_export.build_obs(
    sample_case_map, cases_by_submitter,
    sample_types=sample_types,
    gdc_project_by_sample=sample_project_map,   # NEU
)
```

**Schritt 2 — in `expression.build_obs`** einen optionalen Parameter ergänzen und
`project_id`/`cancer` (und optional `submitter_id`) aus GDC füllen, wenn der Store
nichts liefert:
```python
def build_obs(sample_case_map, cases_by_submitter, *, sample_types=None,
              gdc_project_by_sample=None):
    sample_types = sample_types or {}
    gdc_project_by_sample = gdc_project_by_sample or {}
    ...
    for sample_id, submitter_id in sample_case_map.items():
        case = cases_by_submitter.get(submitter_id, {})
        row = {"sample_type": sample_types.get(sample_id)}
        for obs_col, case_key in _OBS_CASE_FIELDS:
            row[obs_col] = case.get(case_key)
        # Fallback: project_id/cancer aus der GDC-Files-Abfrage, wenn der Case
        # (noch) nicht im Wissensnetz liegt — damit JEDE Probe nach Kohorte
        # gefärbt werden kann, auch ohne vollständige Klinik-Metadaten.
        if not row.get("project_id"):
            row["project_id"] = gdc_project_by_sample.get(sample_id)
        if not row.get("submitter_id"):
            row["submitter_id"] = submitter_id
        row["cancer"] = cancer_code(row.get("project_id"))
        rows.append(row)
    ...
```
(`cancer_code` wird bereits importiert.)

## Ergebnis
Jede Probe trägt danach `project_id`/`cancer` aus GDC (auch ohne Store-Case) →
MP-Lite färbt alle Kohorten, die Legende zeigt die volle Pancancer-Vielfalt. Die
reicheren Klinikfelder (gender, tumor_stage, …) bleiben nur dort gefüllt, wo der
Case im Wissensnetz liegt — das ist ok und unverändert.

## Optional (später, sauberer)
Statt nur des Fallbacks könnte der Endpoint die fehlenden Cases on-the-fly ins
Wissensnetz laden (`/transform` für die betroffenen `submitter_id`s) und dann
anreichern — dann wären auch die übrigen Klinikfelder vollständig. Nicht nötig für
die Färbung, aber die vollständige Lösung.

## Bezug
Wissensnetz-Seite (MP-Lite Färbung/Legende, Aufgabe 7/9) ist fertig und erwartet
`obs["cancer"]`. Der balancierte Abruf (`scripts/fetch_pancancer_h5ad.py
--balanced`) sorgt für gleichmäßige Kohorten, zeigt aber erst MIT diesem Fix echte
Farben statt Grau.
