# Aufgabe 9 (nur): Expressions-`.h5ad` in MP-Lite integrieren (Oberfläche)

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich diese Aufgabe** um, **ausschließlich in `wissensnetz/`**.
Strikte Komponentengrenze: `mediator/` und `wrappers/` werden NICHT editiert. Das
`.h5ad` wird nur **gelesen** (es ist ein Mediator-Artefakt). Branch `Wissensnetz`,
kleine Commits. Aufgaben 5–8 sind umgesetzt; Teil 3 (anndata) ist mediator-/
wrapper-seitig fertig (Commits 07a26dc/8f49ca4).

## Ziel
Die in Aufgabe 6 gebauten, aber mangels Daten **deaktivierten** Expressions-Slider
sollen echt morphen. Grundlage ist das vom Mediator erzeugte anndata/`.h5ad`
(`mediator/sample_data/tcga_brca_sample.h5ad` als Referenz; später der Export-
Endpoint). MP-Lite liest daraus die Expressionsmatrix + vorberechnete tSNE und
ersetzt die synthetischen Platzhalter-Layouts.

## Bekannte Struktur des `.h5ad` (aus mediator/app/semantic/expression.py)
- `X`: float32, **Proben × Gene** (TPM).
- `obs`: Index = `sample_id`; Spalten: `sample_type, submitter_id, project_id,
  race, gender, ethnicity, vital_status, tumor_stage, morphology,
  site_of_resection_or_biopsy, has_metastasis, primary_diagnosis,
  age_at_diagnosis, cancer` (also die volle Oviedo-Feldliste, schon fertig).
- `var`: Index = `feature_id` (Gen-ID, z. B. Ensembl); Spalte `symbol` (Gen-Name,
  z. B. "CA9").
- `obsm["X_tsne_genes"]`: 2D-tSNE der Gen-Profile (fehlt bei ≤3 Proben oder ohne
  scikit-learn). `X_tsne_mirna` ist derzeit NICHT enthalten (Fixture nur RNA-Seq).

## Worauf du aufbaust (vorhandener Code)
- `prototype/mp_lite/app.py` — Morph-Engine (Aufgabe 6): `E`-Stack, softmax-CustomJS,
  Slider je Variable; heute Basis-Views `L0`/`L1` synthetisch, Expressions-Slider
  deaktiviert. Datenquelle bisher `all_cases()` (Graph) bzw. Synthetik-Fallback.
- `prototype/mp_lite/encodings.py` — `linear_encoding`, `is_encodable`.
- `prototype/mp_lite/cohorts.py` bzw. `wissensnetz.cohorts` — `OVIEDO_COHORTS`,
  `cancer_code` (Färbung).

## Deliverables (alle in `wissensnetz/`)

### 1) Abhängigkeit
`anndata` (+ Transitiv: numpy/pandas/h5py) zur Prototyp-Umgebung ergänzen
(requirements bzw. Doku im prototype-README). Import defensiv: fehlt `anndata`,
sauber auf den bisherigen Pfad zurückfallen (kein harter Crash).

### 2) Loader — neues Modul `prototype/mp_lite/h5ad_source.py`
- `load_h5ad(path) -> AnnData | None` (None bei fehlender Datei/`anndata`).
- Pfad konfigurierbar: ENV `DATABRIDGE_H5AD` ODER Default auf das Referenz-`.h5ad`
  (`<repo>/mediator/sample_data/tcga_brca_sample.h5ad`), relativ robust auflösen.
- Kleine Zugriffshelfer: `points_from_obs(adata)` (eine Zeile je Sample mit den
  Oviedo-Hover-Feldern + `cancer`, `tumor`=`submitter_id`), `marker_column(adata,
  symbol)` (X-Spalte per `var["symbol"]`-Lookup, None wenn nicht vorhanden).

### 3) MP-Lite: Datenquellen-Priorität in `app.py`
Reihenfolge beim Start:
1. **`.h5ad` vorhanden** → Punkte/Hover aus `obs` bauen (enthält bereits alle
   Oviedo-Felder + `cancer`), Expressionsdaten aus `X`/`obsm` (Deliverable 4).
2. sonst **Graph** (`all_cases()`, Aufgabe 7) → wie bisher, Expressions-Slider
   deaktiviert.
3. sonst **Synthetik-Fallback**.
Statuszeile (`DATA_SOURCE`) den gewählten Pfad anzeigen lassen (z. B.
"N Proben aus tcga_brca_sample.h5ad").
Hinweis/Designentscheidung: Das Referenz-`.h5ad` ist klein (BRCA); der Pancancer-
Graph-Pfad (Aufgabe 7) bleibt die Alternative, bis ein Pancancer-`.h5ad` aus dem
Export-Endpoint vorliegt. Beide Pfade koexistieren, `.h5ad` hat Vorrang, wenn da.

### 4) Encodings aus dem `.h5ad` (der eigentliche Kern)
- `obsm["X_tsne_genes"]` → Basis-Encoding `E[0]` ("genes") statt des synthetischen
  `L0`. Ist `obsm["X_tsne_mirna"]` vorhanden → `E[1]` ("miRNA"), sonst diese
  Basis-View synthetisch lassen oder deaktivieren (ehrlich kennzeichnen).
- **Einzelmarker-Slider** aus `X`-Spalten: konfigurierbare Liste von Gensymbolen
  (Default z. B. `["CA9", "SAA1"]`, im Original auch `miRNA-210-3p`). Je Marker
  `linear_encoding(X[:, marker_column])`; Slider nur aktiv, wenn das Symbol in
  `var` existiert (`is_encodable`), sonst deaktiviert mit Hinweis.
- Klinische Circular-Encodings (Aufgabe 6) weiter aus `obs` — funktioniert
  unverändert, jetzt eben aus der `.h5ad`-`obs`.
- Achtung Achsen-Skalierung: tSNE-Koordinaten und die klinischen Encodings liegen
  in unterschiedlichen Wertebereichen — die bestehende Normalisierung/Skalierung
  der Encodings so anwenden, dass das Morphen zwischen tSNE und klinischen Views
  optisch sinnvoll bleibt (ggf. tSNE auf denselben Bereich skalieren wie die
  circular/linear Encodings).

### 5) Hover/Färbung/Rückkanal unverändert
Hover-Feldliste (Aufgabe 5), Färbung nach Krebsart + Legende (Aufgabe 7) und
Rückkanal ③ bleiben funktionsfähig — sie lesen jetzt aus `obs` statt aus dem Graph.

## Verifikation
- `pip install anndata` in der Prototyp-Env; `bokeh serve --show
  wissensnetz/prototype/mp_lite/app.py` startet mit dem Referenz-`.h5ad`:
  Statuszeile zeigt die `.h5ad`-Quelle, der "genes"-Slider bewegt die Punkte
  entlang der echten tSNE, aktive Marker-Slider (CA9/SAA1, falls im Fixture) morphen
  linear, Hover zeigt `obs`-Werte.
- Fallback: ohne `.h5ad` (ENV leer + Datei weg) startet die App weiter über den
  Graph-/Synthetik-Pfad; ohne `anndata`-Paket ebenfalls kein Crash.
- Unit-Test (`tests/`, skip ohne `anndata`): `h5ad_source` lädt das Referenz-`.h5ad`
  (oder ein winziges selbstgebautes), `points_from_obs` liefert die erwarteten
  Spalten, `marker_column` findet ein vorhandenes Symbol und gibt None für ein
  unbekanntes.
- Bestehende Tests bleiben grün: `pytest wissensnetz/tests -q`.

## Grenze / Hinweise
- Nur lesen: das `.h5ad` ist ein Mediator-Artefakt; MP-Lite erzeugt es nicht und
  editiert `mediator/`/`wrappers/` nicht.
- Der Export-Endpoint (`POST /export/anndata`) braucht `gdc-client` und lädt live —
  für diese Aufgabe genügt das statische Referenz-`.h5ad`. Die spätere Anbindung an
  den Endpoint (dynamisch, Pancancer) ist eine Folgeaufgabe.
- Sample-granulare `obs` (statt Case-Duplikat) bleibt eine optionale Wissensnetz-
  Verfeinerung (niedrige Priorität), siehe HANDOFF_anndata.md, Abschnitt 3c.
