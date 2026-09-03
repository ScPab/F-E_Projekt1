# Aufgabe 11 (nur): MP-Lite-Layout exakt an Oviedo angleichen

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um,
**ausschließlich in `wissensnetz/prototype/mp_lite/`** (v. a. `app.py`). NICHT
`mediator/`/`wrappers/`. Die eingebettete Oviedo-`demo.py` NICHT importieren — nur
als **Layout-Vorlage lesen**:
`morphing-projections-demo-and-dataset-preparation-master/.../demo.py`.
Kleine Commits.

## Ziel
Das **Hauptlayout** von MP-Lite soll exakt wie Oviedos Original aussehen
(Screenshot/`demo.py`): links der Scatter mit Titel „Cancer map" und Toolbar oben,
die **Kohorten-Legende als Bokeh-Legende rechts im Plot** (farbige Punkte + Labels),
und rechts daneben die **Slider als schlanke vertikale Spalte** in Oviedos
Reihenfolge/Benennung. **Entscheidung des Teams: Kontext (②) und Rückkanal (③)
bleiben erhalten** — kompakt UNTER dem Plot, nicht mehr als große rechte Sidebar.

## Vorlage aus demo.py (nur lesen)
```python
plot = figure(..., title="Cancer map",
              tools="crosshair,pan,reset,save,wheel_zoom,box_select,lasso_select", ...)
plt = plot.circle('pos_x','pos_y', source=source, color='color', legend='cancer',
                  size=6, alpha=0.6, nonselection_alpha=0.3, line_color='#000000')
# Slider je Variable, Titel = encoding_name; sliders[0].value = 0.5
layout = gridplot([plot, widgetbox(sliders)], ncols=2)
```

## Deliverables (alles in `prototype/mp_lite/app.py`)

### 1) Plot wie Oviedo
- `figure(title="Cancer map", toolbar_location="above", tools="pan,box_select,
  lasso_select,tap,wheel_zoom,reset,save", output_backend="webgl", ...)`.
  Der bisherige lange Titel und die seitliche Toolbar entfallen.
- Punkt-Stil an Oviedo angleichen (size ~7–8, alpha ~0.6, `line_color="#333"` /
  schwarz, `nonselection_alpha` niedrig) — nah am Original.

### 2) Kohorten-Legende IN den Plot (rechts), Sidebar-Legende entfernen
- Die Legende als **Bokeh-Legende** am Punkt-Glyph erzeugen (moderne Bokeh-API:
  `legend_field="cancer"` bzw. manuell `LegendItem`s je vorkommender Kohorte in
  **OVIEDO_COHORTS-Reihenfolge** mit `COHORT_COLORS`).
- Legende nach rechts aus dem Plot legen: `plot.add_layout(plot.legend[0], "right")`.
  Kompakt konfigurieren (kleine `label_text_font_size`, `spacing=0`,
  `glyph_height/width` klein), damit viele Kohorten (bis 32) untereinander passen —
  wie im Oviedo-Screenshot (lange Punkt-Liste rechts).
- Das bisherige Sidebar-`legend_div` (Farb-Chips) **entfernen**.

### 3) Slider-Spalte rechts — exakt Oviedos Set, Reihenfolge und Benennung
Genau diese 15 Slider, in dieser Reihenfolge und mit diesen Titeln (Titel = reiner
Name, KEIN "marker:"-Präfix, KEIN "Morphing-Slider (Σ …)"-Header):
```
genes, mirna, cancer, type, race, gender, ethnicity, primary_diagnosis,
has_metastasis, vital_status, cancer (ver), tumor_stage (ver),
miRNA-210-3p (hor), CA9 (ver), SAA1 (hor)
```
- `genes` startet bei 0.5 (Basis-View, wie Oviedo `sliders[0].value=0.5`), alle
  anderen bei 0. Slider kompakt (`width≈200`), Titel oben.
- **Datengetrieben aktivieren** (bestehendes Muster beibehalten): ein Slider ist nur
  aktiv, wenn seine Encoding-Daten vorliegen; sonst `disabled=True` mit Titel-Zusatz
  „(keine Daten)". Aus dem aktuellen `.h5ad` (nur `X_tsne_genes` + Klinik + Gene):
  - aktiv: `genes` (obsm), die klinischen Circular-Slider (cancer/type/race/gender/
    ethnicity/primary_diagnosis/has_metastasis/vital_status, sofern ≥2 Werte),
    `CA9 (ver)`/`SAA1 (hor)` (lineare Encodings aus `X`, Marker umbenennen von
    „marker:CA9"/„marker:SAA1"), sowie `cancer (ver)`/`tumor_stage (ver)` als lineare
    Encodings aus `obs` (falls encodierbar).
  - deaktiviert (mangels Daten): `mirna` (kein `X_tsne_mirna`), `miRNA-210-3p (hor)`
    (keine miRNA-Spalten im genes-`.h5ad`). Als deaktivierte Slider anzeigen, damit
    das Set optisch dem Original entspricht.
- `type` = `sample_type`-Encoding (nur Label „type"). `morphology`/`site_biopsy`
  sind bei Oviedo **keine** Slider (nur Hover) → aus der Slider-Spalte NEHMEN
  (im Hover bleiben sie).
- Die Morph-Mechanik (Σ aᵢ·E[i], softmax, CustomJS) bleibt unverändert; nur die
  angezeigte Reihenfolge/Benennung der Slider wird an Oviedo angepasst.

### 4) ②/③ + Status kompakt behalten (unter dem Plot)
- Status/„Daten: N Proben"-Zeile, Kontext-Panel ② (Selektion → case_context) und
  Rückkanal ③ (Nutzer/Hypothese/Notiz/Konfidenz + „Erkenntnis speichern" +
  Erkenntnis-Liste) bleiben **funktional unverändert**, wandern aber in einen
  schmalen Bereich UNTER den Plot (z. B. `column` unter dem `row(plot, slider)`),
  optisch dezent — nicht mehr die dominierende rechte Sidebar.

### 5) Gesamtlayout
Wie Oviedo: `row(plot, column(*sliders))` als Hauptbereich; darunter der ②/③-Block.
Hover (Aufgabe 5) unverändert.

## Verifikation
- `bokeh serve --show wissensnetz/prototype/mp_lite/app.py` (mit vorhandener
  `pancancer.h5ad`): Titel „Cancer map", Toolbar oben, farbige Kohorten-Legende
  rechts IM Plot, Slider-Spalte rechts in obiger Reihenfolge/Benennung; `genes`
  bewegt die Punkte, deaktivierte Slider (mirna, miRNA-210-3p) klar erkennbar; ②/③
  darunter weiter nutzbar (Auswahl zeigt Kontext, Speichern funktioniert).
- Optischer Abgleich mit dem Oviedo-Screenshot bzw.
  `morphing-projections-demo-and-dataset-preparation-master/.../demo.html`.
- Fallback ohne `.h5ad` (BRCA-Fixture/Graph/Synthetik) startet weiterhin fehlerfrei.
- Bestehende Tests grün: `pytest wissensnetz/tests -q`.

## Grenze
Nur `wissensnetz/prototype/mp_lite/`. Keine Mediator-/Wrapper-Änderung; `demo.py`
nur als Vorlage lesen, nicht importieren/kopieren (eigener, sauberer Code).
