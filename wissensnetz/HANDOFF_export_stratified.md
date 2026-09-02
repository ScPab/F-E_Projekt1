# Hand-off an Pablo (Mediator): stratifiziertes Sampling in `/export/anndata`

## Symptom (belegt)
Ein Pancancer-Export (`POST /export/anndata` mit `project_id`=alle 32 Kohorten,
`size=40`) liefert eine `.h5ad`, in der **alle 40 Proben aus einer einzigen
Kohorte** stammen: `obs["cancer"]` = LUAD ×40. In MP-Lite erscheint deshalb nur
LUAD in der Legende, obwohl der Store alle 32 Kohorten (1604 Cases) enthält.

## Ursache (nicht die Färbung!)
Die `obs`-Färbung ist korrekt — sie kommt aus dem Wissensnetz plus dem neu
eingebauten GDC-Fallback (`build_obs(..., gdc_project_by_sample=...)`, siehe
`HANDOFF_obs_fallback.md`); alle 40 Proben sind wirklich LUAD.

Das Problem ist das **Sampling** in `export_anndata` (`app/main.py`): Die Files
werden mit **einem** GDC-Query geholt —
```python
result = wrapper.query("files", filters=file_filters, fields=file_fields, size=request.size)
```
`size` ist ein **Gesamt-Limit über alle Projekte**, ohne `sort`/Stratifizierung.
GDC gibt die ersten `size` Files in seiner Default-Reihenfolge zurück — die sind
hier komplett LUAD. Es gibt keine Garantie/Logik für „N Proben pro Kohorte".

Zusätzlich: `materialized`-Cache (`recipe_key`) gibt bei identischer Anfrage
dieselbe Datei zurück — ein erneuter Default-Lauf ändert nichts.

## Gewünschtes Verhalten
Ein Multi-Kohorten-Export soll die Proben **gleichmäßig über die Kohorten**
verteilen (globale tSNE über die kombinierte Matrix bleibt wie bisher).

## Fix (Vorschlag, Mediator-seitig)
Neues optionales Request-Feld `per_project_size: int | None` in
`AnndataExportRequest`. Ist es gesetzt (oder generell, wenn `project_id` eine
Liste ist), die Files **pro Projekt** holen statt in einem Sammel-Query:

```python
# in export_anndata, statt des einen files-Query:
projects = request.project_id if isinstance(request.project_id, list) else [request.project_id]
n_each = request.per_project_size or request.size
hits = []
for proj in projects:
    f = build_filters(project_id=proj, experimental_strategy=request.experimental_strategy,
                      access="open",
                      extra=[{"op":"in","content":{"field":"files.data_type","value":[request.data_type]}}])
    try:
        r = wrapper.query("files", filters=f, fields=file_fields, size=n_each)
    except RequestException as exc:
        # eine leere/kaputte Kohorte nicht den ganzen Export killen
        continue
    hits.extend(r["results"])
```
Der Rest (`sample_case_map`/`sample_types`/`sample_project_map` aufbauen,
Manifest, Download, `assemble_matrix`, `build_obs`, globale `compute_tsne`,
`write_h5ad`) bleibt **unverändert** — er arbeitet schon auf der aggregierten
`hits`-Liste.

Wichtig:
- `per_project_size` in das `recipe`-Dict (Cache-Key) aufnehmen, damit
  stratifizierte Anfragen einen eigenen Cache-Eintrag bekommen.
- `size`-Semantik dokumentieren: bei Liste = pro Projekt (bzw. `per_project_size`),
  Gesamtzahl = Σ. Die 200er-Obergrenze ggf. auf die Gesamtzahl beziehen.

## Ergebnis
Ein Aufruf liefert dann z. B. 5 Proben × 32 Kohorten = ~160, global geclustert →
MP-Lite färbt alle Kohorten, die Legende zeigt die volle Pancancer-Vielfalt.

## Alternative (ohne Mediator-Änderung — Kontext)
Das Client-Skript `scripts/fetch_pancancer_h5ad.py --balanced` macht genau diese
Stratifizierung schon client-seitig (ein Aufruf pro Kohorte + Merge + globale
tSNE). Aktuell schlägt es bei jeder Kohorte fehl (Grund wird jetzt inline
ausgegeben — noch zu diagnostizieren). Die Mediator-seitige Lösung oben ist aber
sauberer und für alle Consumer nutzbar; sie macht den `--balanced`-Merge
überflüssig.

## Bezug / Grenze
Wissensnetz-Seite (Färbung/Legende, Aufgabe 7/9; obs-Fallback) ist fertig und
erwartet nur ein `.h5ad` mit gemischtem `obs["cancer"]`. Diese Änderung liegt
komplett in `mediator/` (Pablo).
