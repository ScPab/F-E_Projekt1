# Hand-off an Pablo (Mediator): Den Auftrag ins `.h5ad` schreiben

**Von:** Marcel (Wissensnetz / Oberfläche)
**Datum:** 2026-09-24
**Bezug:** `mediator/app/main.py::_build_anndata_from_hits`,
`mediator/app/semantic/expression.py::build_anndata`, ADR-0003 („Die Auswahl ist der
Auftrag und damit der Vertrag")
**Status:** Anforderung, noch nicht umgesetzt. Die Oberfläche funktioniert ohne sie, aber
nur mit einer verlustbehafteten Behelfslösung (unten, Abschnitt 5).

---

## 1 Worum es geht

Ein `.h5ad` ist heute ein Ergebnis ohne Herkunft. Man sieht die Proben, aber nicht mehr,
**welche Auswahl zu ihnen geführt hat**. Ich bitte darum, den Auftrag beim Erzeugen in
`uns` mitzuschreiben — ein Feld, eine JSON-Zeichenkette, keine Schemaänderung sonst.

## 2 Befund, an den Dateien gemessen

`uns` ist in **allen** vorhandenen Exporten leer:

| Datei | Proben | `uns` |
|---|---|---|
| `wissensnetz/data/selection_demo.h5ad` | 6 | `{}` |
| `wissensnetz/data/pancancer.h5ad` | 160 | `{}` |
| `Export Anndata/0465461fa8628e8a284a866e.h5ad` | 6 | `{}` |

Das ist kein Fehler, sondern schlicht eine Lücke: `expression.build_anndata()` nimmt
`X`, `obs`, `var` und optional `obsm` entgegen — für `uns` gibt es keinen Parameter, und
keiner der drei Aufrufer (`main.py` Zeilen 873, 1010, 1269) hätte einen, den er übergeben
könnte.

## 3 Warum die Oberfläche das braucht

Der Explorer hat seit dieser Woche die Schaltfläche **`Auftrag aus .h5ad …`**: man öffnet
eine früher erzeugte Datei, und die Oberfläche stellt die Auswahl wieder her — Kohorten,
Attribute, Probenzahl — und zeichnet das Wissensnetz dazu. Das ist der Weg, eine frühere
Suche wieder aufzunehmen, ohne sie aus dem Kopf zu rekonstruieren.

Ohne `uns` muss ich raten, und zwar an drei Stellen unterschiedlich gut:

| was | woher heute | verlässlich? |
|---|---|---|
| Kohorten | `obs["project_id"]` | ja |
| Attribute | die **belegten** `obs`-Spalten | **nein** (siehe unten) |
| `size` | größte Fallzahl je Kohorte | nur, solange nichts nachträglich gefiltert wurde |
| Datenquelle | — | **gar nicht**, steht nirgends in der Datei |
| Modalität | — | gar nicht |
| `recipe_key` | — | gar nicht |

Der wunde Punkt sind die Attribute. Du legst in `build_obs` **immer** dieselben Spalten an
und füllst nur die angefragten; ein Attribut, das im Auftrag stand, aber für *jede* Probe
leer zurückkam, ist damit von einem nie angefragten nicht zu unterscheiden. Gemessen an
`selection_demo.h5ad`: dort sind `race`, `gender`, `ethnicity`, `vital_status`,
`morphology`, `site_of_resection_or_biopsy`, `has_metastasis`, `age_at_diagnosis` in
0 von 6 Zeilen gefüllt. Ob die acht nie angefragt wurden oder GDC nichts lieferte, sagt
die Datei nicht.

## 4 Die Anforderung

**Beim Erzeugen eines `.h5ad` den Auftrag unter `uns["databridge_selection"]` ablegen**,
als JSON-Zeichenkette.

```json
{
  "schema": 1,
  "recipe_key": "27d36cf9a95b1b03de629ba4",
  "created": "2026-09-24T12:03:11Z",
  "endpoint": "/selection/generate",
  "source": "gdc",
  "cohorts": ["TCGA-BRCA", "TCGA-LUAD"],
  "modality": "gene_expression",
  "attributes": ["sex_at_birth", "primary_diagnosis"],
  "size": 20,
  "per_cohort_size": null,
  "experimental_strategy": "RNA-Seq"
}
```

Alle Werte liegen an der Stelle, an der `_build_anndata_from_hits` das `.h5ad` baut,
bereits vor: `recipe_key` nutzt du zwei Zeilen später für den Dateinamen, die übrigen
kommen aus `SingleSelection` und `SelectionRequest`.

**Warum eine JSON-Zeichenkette und kein verschachteltes Dict:** `uns` wird in HDF5 als
Gruppe abgelegt; Listen von Zeichenketten und `None`-Werte kommen je nach anndata-Version
als `array(dtype=object)`, als Bytes oder gar nicht zurück. Eine Zeichenkette geht
verlustfrei hin und zurück, ist mit `json.loads` in einer Zeile gelesen und lässt sich
versionieren (`"schema": 1`). Genau dieselbe Überlegung wie bei Turtle im Store: ein Format,
das beim Roundtrip nichts verliert.

**Konkret vorgeschlagen:**

```python
# expression.py
def build_anndata(X, obs, var, *, obsm=None, uns: Optional[dict] = None) -> AnnData:
    adata = AnnData(X=X, obs=obs, var=var)
    if obsm:
        for key, value in obsm.items():
            adata.obsm[key] = value
    if uns:
        adata.uns.update(uns)
    return adata
```

```python
# main.py, _build_anndata_from_hits (und sinngemäß die beiden anderen Aufrufer)
adata = expression_export.build_anndata(
    X, obs, var, obsm=obsm or None,
    uns={"databridge_selection": json.dumps(selection_dict, ensure_ascii=False)},
)
```

`selection_dict` müsste `_build_anndata_from_hits` durchgereicht bekommen — dieselbe
Ebene, aus der auch `recipe_key` kommt.

**Auch bei `/export/anndata`**, nicht nur bei `/selection/generate`: dort gibt es keine
Ebenen, aber Kohorten, Größe und Strategie stehen im `AnndataExportRequest`. Dann ist
`"endpoint"` das Feld, das die beiden Fälle unterscheidet.

## 5 Was ich bis dahin mache

Die Oberfläche leitet den Auftrag weiter aus den Daten ab (`frontend/morph.py::
auftrag_aus_modell`) und **sagt in der Statuszeile, dass es eine Rekonstruktion ist**:
„Datenquelle bleibt unverändert; leer gebliebene Attribute sind nicht rekonstruierbar."

Sobald `uns["databridge_selection"]` da ist, lese ich es vorrangig und nutze die Ableitung
nur noch als Rückfall für ältere Dateien. **Es geht nichts kaputt, wenn das Feld fehlt** —
und nichts, wenn es dazukommt.

## 6 Abnahme

```powershell
.\start_all.ps1 -DemoGenerate
```

```python
import anndata as ad, json
a = ad.read_h5ad(r"wissensnetz\data\selection_demo.h5ad")
sel = json.loads(a.uns["databridge_selection"])
assert sel["cohorts"] == ["TCGA-BRCA"]
assert sel["source"] == "gdc"
assert "sex_at_birth" in sel["attributes"]
```

1. Ein frisch erzeugtes `.h5ad` trägt das Feld, und der Inhalt entspricht **Zeichen für
   Zeichen** dem abgeschickten Auftrag — insbesondere stehen dort auch Attribute, die
   leer zurückkamen.
2. Ältere Dateien ohne das Feld lassen sich weiterhin öffnen (in der Oberfläche und mit
   `anndata`).
3. `POST /export/anndata` schreibt es ebenfalls, mit `"endpoint": "/export/anndata"`.

## 7 Ausdrücklich **nicht** Teil dieser Anforderung

- Keine Änderung an `obs`, `var`, `X` oder `obsm`. Nur ein Schlüssel in `uns`.
- Keine Änderung an den Antwortschemata von `/selection/*`. Das Feld steht in der Datei,
  nicht in der HTTP-Antwort.
- Kein Umbau des `recipe_key` und keine neue Endpunkt-Variante.

## 8 Nebenbei aufgefallen, eigene Entscheidung

`wissensnetz/data/selection_demo.h5ad` trägt noch die alte Spalte `gender`, die neueren
Exporte `sex_at_birth`. GDC hat das Feld umbenannt (siehe `_sex_at_birth_hinweis` in
`frontend/config/panel.json`); die Oberfläche zieht `gender` beim Lesen auf `sex_at_birth`.
Ob die alten Dateien neu erzeugt werden sollen, ist eine eigene Frage und gehört nicht in
diese Anforderung.
