# Aufgabe 10 (nur): Pancancer-`.h5ad` live über den Mediator-Export in MP-Lite

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich diese Aufgabe** um. Erlaubte Bereiche: `scripts/` und
`wissensnetz/`. **NICHT** `mediator/`, **NICHT** `wrappers/` editieren — der
`/export/anndata`-Endpoint wird nur per **HTTP** aufgerufen. Kleine Commits.
Aufgaben 5–9 sind umgesetzt; MP-Lite lädt bereits jedes `.h5ad` über
`prototype/mp_lite/h5ad_source.py` (Pfad: arg > ENV `DATABRIDGE_H5AD` > BRCA-Default).

## Ziel
Statt nur das kleine BRCA-Referenz-`.h5ad` soll MP-Lite eine **Pancancer**-
Expressions-Landkarte anzeigen — echte Gene-Expression über viele TCGA-Kohorten
mit einer **globalen** tSNE, wie im Oviedo-Original. Die Daten kommen live über
Pablos `POST /export/anndata` (+ Download-Route). MP-Lite selbst muss dafür fast
nichts ändern (es liest die Datei), der Kern ist ein Abruf-Skript.

## Endpoint-Contract (verifiziert, nur lesen/aufrufen)
`POST {mediator}/export/anndata` mit JSON (Felder aus `AnndataExportRequest`):
- `project_id`: **String ODER Liste** — eine Liste (z. B. alle `TCGA-*`) filtert
  Files über mehrere Kohorten in EINEM Aufruf; die tSNE wird über die kombinierte
  Matrix gerechnet (globale Karte).
- `experimental_strategy` (Default "RNA-Seq"), `data_type`
  (Default "Gene Expression Quantification"), `id_column`="gene_id",
  `value_column`="tpm_unstranded", `label_column`="gene_name".
- `size`: Anzahl Expressions-Dateien (~Proben), **1..200** (harte Obergrenze!).
- `compute_tsne`: bool → legt `obsm["X_tsne_genes"]` an (RNA-Seq).
- `gene_ids`: optionale Whitelist (identische `var`-Achse erzwingen — für den
  balancierten Merge-Pfad wichtig, s. u.).
Antwort = Metadaten-Dict, u. a. `n_obs`, `n_vars`, `obs_columns`, `obsm_keys`,
`filename`, `path`, **`download_url`** (`/export/anndata/download/{filename}`).
Voraussetzung im Mediator-Container: funktionierender `gdc-client` + erreichbares
Fuseki (sonst klarer 502/503). Kohortenliste + Project-IDs liegen bereits in
`wissensnetz/src/wissensnetz/cohorts.py` (`OVIEDO_COHORTS`, `COHORT_PROJECT_IDS`).

## Deliverables

### 1) Abruf-Skript — `scripts/fetch_pancancer_h5ad.py`
CLI-Argumente: `--mediator-url` (Default ENV `MEDIATOR_URL` / http://localhost:8000),
`--out` (Default `wissensnetz/data/pancancer.h5ad`), `--size` (Default 160, ≤200),
`--projects` (Default: alle `COHORT_PROJECT_IDS`; Komma-Liste erlaubt),
`--strategy`/`--data-type` (Default RNA-Seq/Gene Expression Quantification),
`--balanced` (Flag, s. Phase 2), `--per-cohort-size` (für `--balanced`, Default 5).

**Phase 1 (Default, MVP — ein Aufruf):**
- `POST /export/anndata` mit `{project_id: <projects>, size, compute_tsne: true,
  strategy/data_type/...}`.
- Fehler sauber behandeln: non-2xx → Statuscode + `detail` ausgeben und mit Fehler
  enden (bei 503 explizit auf `gdc-client`/Fuseki hinweisen, wie im Endpoint-Detail).
- Aus der Antwort `download_url` nehmen, per `GET {mediator}{download_url}` die
  Datei nach `--out` speichern (Verzeichnis anlegen). NICHT den `path` aus der
  Antwort direkt lesen (Entkopplung: der Download-Endpoint ist der vereinbarte
  Übergabeweg, HANDOFF_anndata.md Offener Punkt 4).
- Abschluss-Report: `n_obs`, `n_vars`, `obsm_keys`, wie viele/welche Kohorten in
  `obs["cancer"]`/`project_id` vertreten sind, und die genaue Zeile zum Setzen von
  `DATABRIDGE_H5AD` auf `--out`.

**Phase 2 (`--balanced`, optional — gleichmäßige Kohorten):**
Ein einzelner `size`-Aufruf verteilt die Proben nicht gleichmäßig über die
Kohorten. Für eine balancierte Karte: pro Projekt `POST /export/anndata` mit
`compute_tsne=false` und **fixierten `gene_ids`** (aus dem ersten Kohorten-Ergebnis
übernehmen, damit alle dieselbe `var`-Achse haben), jedes Kohorten-`.h5ad`
herunterladen, mit `anndata.concat(..., join="inner")` zusammenführen, danach EINE
globale 2D-tSNE über die kombinierte `X` rechnen (scikit-learn, im Skript — kein
Mediator-Code) und als `obsm["X_tsne_genes"]` ablegen, dann nach `--out` schreiben.
Klar dokumentieren, dass das der Oviedo-treue Pancancer-Weg ist, aber mehr Downloads
kostet.

### 2) MP-Lite — Pancancer-Datei bevorzugen (`prototype/mp_lite/h5ad_source.py`)
Kleine Ergänzung der Pfad-Auflösung: nach explizitem `path`/ENV, aber **vor** dem
BRCA-Default, ein vorhandenes `wissensnetz/data/pancancer.h5ad` verwenden, wenn es
existiert. So zeigt MP-Lite nach dem Abruf automatisch die Pancancer-Karte, ohne dass
man ENV setzen muss; ohne die Datei bleibt alles wie in Aufgabe 9 (BRCA-Fixture).
`app.py` braucht sonst nichts — Datenquellen-Priorität, tSNE-Skalierung, Marker und
Färbung greifen unverändert (die `obs`-Struktur ist identisch, nur mehr Zeilen/Gene).

### 3) RUNBOOK-Hinweis
Kurzer Abschnitt: „Pancancer-Karte erzeugen" → Voraussetzungen (Mediator läuft,
`gdc-client` vorhanden, Fuseki gefüllt) + `python scripts\fetch_pancancer_h5ad.py`
+ MP-Lite neu laden.

## Verifikation
- `python scripts/fetch_pancancer_h5ad.py --size 20` (kleiner Smoke-Test) gegen den
  laufenden Mediator: legt `wissensnetz/data/pancancer.h5ad` an, Report zeigt
  mehrere Kohorten und `obsm_keys=["X_tsne_genes"]`. Fehlt `gdc-client`/Fuseki →
  klare Fehlermeldung statt Stacktrace.
- `bokeh serve --show wissensnetz/prototype/mp_lite/app.py`: Statuszeile nennt die
  Pancancer-Datei, der „genes"-Slider morpht entlang der globalen tSNE, Punkte sind
  nach Krebsart gefärbt (mehrere Kohorten), Marker-Slider (CA9/SAA1) aktiv, wenn die
  Gene in `var` sind.
- Fallback: ohne `pancancer.h5ad` startet MP-Lite weiter über BRCA-Fixture/Graph/
  Synthetik (Aufgabe 9 unverändert). Bestehende Tests bleiben grün
  (`pytest wissensnetz/tests -q`); ein kleiner Test für die neue Pfad-Priorität in
  `h5ad_source` (Pancancer-Datei existiert → wird bevorzugt) ist wünschenswert.

## Grenze / Hinweise
- Nur HTTP zum Mediator; kein Edit an `mediator/`/`wrappers/`. Das `.h5ad` wird nur
  gelesen/heruntergeladen.
- `size`-Obergrenze 200 ist eine Endpoint-Grenze; eine echte „ganze Kohorten"-Karte
  (tausende Proben) bräuchte einen serverseitigen Pancancer-/Streaming-Modus — das
  wäre ein separater Mediator-Hand-off an Pablo, NICHT Teil dieser Aufgabe.
- Große RNA-Seq-Downloads dauern; `--size` klein halten und beim Testen zuerst
  `--size 20`.
