# Hand-off an Pablo (Mediator): Kohorten-Färbung der Pancancer-`.h5ad`

**Von:** Marcel (Wissensnetz) · **Kontext:** Aufgabe 10 (Pancancer-`.h5ad` live über
`POST /export/anndata` in MP-Lite). Betrifft `mediator/app/main.py` +
`mediator/app/semantic/expression.py`. Reines Mediator-Thema — ich fasse es bewusst
nicht selbst an (es berührt deine dokumentierte Design-Entscheidung „obs aus dem
Wissensnetz", HANDOFF_anndata.md 3b).

## Was schon läuft (verifiziert)
Die Aufgabe-10-Kette funktioniert end-to-end: `scripts/fetch_pancancer_h5ad.py`
→ `POST /export/anndata` (Container mit `gdc-client` 2.3) → Download →
`wissensnetz/data/pancancer.h5ad`. Ergebnis eines Laufs: **30 Proben × 60.660 Gene**,
echte `obsm["X_tsne_genes"]`, `var["symbol"]` mit CA9/SAA1. MP-Lite lädt die Datei
automatisch (Aufgabe 9/10, Pfad-Priorität in `prototype/mp_lite/h5ad_source.py`).

Zwei kleine Mediator-Fixes waren dafür nötig (auf Marcels ausdrückliche Anweisung,
je eigener Commit — bitte gegenlesen/übernehmen oder ersetzen):
1. **`mediator/Dockerfile`**: `gdc-client` aus bioconda ins `databridge-mediator`-Env
   (ohne das → 503 beim Bulk-Download; auf Windows-Host gibt es kein conda-Paket,
   daher im Linux-Image).
2. **`mediator/app/semantic/expression.py::build_obs`**: object-`obs`-Spalten mit
   `None` zu `""` normalisieren vor `write_h5ad`. Sonst wirft h5py
   `TypeError: Can't implicitly convert non-string objects to strings` (key `gender`),
   sobald ein Klinik-Feld fehlt — bei echten GDC-Proben unvermeidlich.

## Das offene Problem: Punkte bleiben grau (keine Kohorten-Färbung)
In der erzeugten `.h5ad` haben **23 von 30 Proben eine leere `submitter_id`** (und damit
leeres `cancer`). Diagnose (submitter_id der `obs` gegen `all_cases()` geprüft):
- 23/30 Proben: **gar keine `submitter_id`** → keine Anreicherung möglich → grau.
- 7/30 Proben (LUAD): `submitter_id` vorhanden, **alle** im Graphen gefunden → korrekt
  gefärbt. Die Graph-Abdeckung (1604 Fälle) ist also NICHT der Engpass.

### Ursache (Mediator)
In `mediator/app/main.py` (export_anndata, ~Zeile 487–521) wird die GDC-Files-Suche mit
den Feldern gefahren:
```python
file_fields = ["file_id", "file_name",
               "cases.submitter_id", "cases.project.project_id",
               "cases.samples.sample_id", "cases.samples.sample_type"]
...
case = (hit.get("cases") or [{}])[0]
sample = (case.get("samples") or [{}])[0]
sample_id = sample.get("sample_id") or file_id      # Fallback file_id
sample_case_map[sample_id] = case.get("submitter_id")  # -> None, wenn cases leer
```
Für die meisten Treffer kommt `hit["cases"]` **leer** zurück → `submitter_id` = `None`,
`sample_id` fällt auf `file_id` zurück. Damit findet `build_obs` keinen Case, und
`cancer = cancer_code(case.get("project_id"))` bleibt leer. Zusätzlich wird
`cases.project.project_id` zwar **angefragt, aber nie verwendet** (nicht in
`sample_case_map`/`build_obs` übernommen).

## Zwei Lösungsrichtungen (deine Entscheidung)
1. **GDC-Files-Suche so fixen, dass jede Datei ihr `cases.submitter_id` mitbringt.**
   Vermutlich Feld-Expansion/`expand` im GDC-Wrapper (`wrappers/gdc`) bzw. die
   `query("files", fields=…)`-Übergabe — die verschachtelten `cases.*`-Felder kommen
   für RNA-Seq-Files nicht zuverlässig zurück. Sobald der Barcode da ist, greift die
   bestehende Graph-Anreicherung (die 7 LUAD zeigen: der Weg funktioniert).
2. **Fallback direkt aus dem GDC-Projekt der Datei.** `cases.project.project_id` wird
   bereits abgefragt — beim Aufbau von `sample_case_map` mitnehmen und in `build_obs`
   als Quelle für `cancer`/`project_id` nutzen, wenn der Graph-Case fehlt. Färbt jede
   Probe nach Kohorte unabhängig von der Graph-Abdeckung — weicht aber bewusst von
   „obs nur aus Wissensnetz" ab. Hinweis: hilft nur, wenn der Treffer überhaupt
   `cases.project` trägt; bei komplett leerem `cases` (die 23 oben) bleibt Option 1
   nötig.

Empfehlung: erst **Option 1** prüfen (Datenlücke an der Wurzel), Option 2 als
robusten Zusatz-Fallback.

## Repro
```powershell
docker compose up -d --build mediator            # Mediator-Container (mit gdc-client)
python scripts/load_gdc.py --pancancer --size 50 # Graph füllen (obs-Quelle)
python scripts/fetch_pancancer_h5ad.py --size 30 # -> wissensnetz/data/pancancer.h5ad
```
Dann `obs["submitter_id"]`/`obs["cancer"]` prüfen: aktuell die Mehrheit leer.
