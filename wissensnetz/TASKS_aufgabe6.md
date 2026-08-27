# Aufgabe 6 (nur): Multi-Variablen-Morphing in MP-Lite (wie Oviedo)

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich diese Aufgabe** um, **ausschließlich in `wissensnetz/`**.
Strikte Komponentengrenze: **NICHT** `mediator/` und **NICHT** `wrappers/` editieren,
Fixture `data/sample/cases_brca_sample.ttl` **NICHT** von Hand ändern. Keine
Expressions-/Klinik-Daten erfinden. Branch `Wissensnetz`, kleine Commits.
Aufgabe 5 (Oviedo-Hover) ist umgesetzt; du baust darauf auf.

## Ziel
Statt des einzelnen Blend-Sliders (L0 „Gene" ↔ L1 „miRNA") soll MP-Lite **pro
Variable einen eigenen Slider** haben und zwischen allen Anordnungen morphen —
mechanisch exakt wie das Original von Oviedo
(`morphing-projections-demo-and-dataset-preparation-master/.../demo.py`).
Morphing-Formel dort:
    finale Position = Σ  a_i · E[i]     mit  a = softmax(sens · slider_werte), sens=10
E[i] ist pro Variable eine (n_samples, 2)-Anordnung; alle E[i] werden zu einer
(n_samples, 2·num_encodings)-Matrix gestapelt und die Gewichtung läuft client-seitig
in JS (CustomJS) für flüssige Interaktion.

**Zweiphasig**, weil die meisten Daten noch fehlen (siehe unten):
- **Phase A (jetzt, reiner Prototyp-Code):** Morph-Engine + N Slider, getrieben von
  den *aktuell im Graphen vorhandenen* Variablen. Tolerant gegen fehlende Daten.
- **Phase B (Hand-off):** Notiz, welche Daten für die restlichen Slider
  (v. a. Expression: genes/miRNA/CA9/…) zuerst integriert werden müssen.

## Worauf du aufbaust (vorhandener Code, nicht neu erfinden)
- `prototype/mp_lite/app.py` — aktueller einzelner `morph`-Slider, `_blend(t)`,
  `ColumnDataSource` mit `pos_x/pos_y`, die in Aufgabe 5 ergänzten Klinik-Spalten
  (cancer, sample_type, race, gender, ethnicity, tumor_stage, morphology,
  site_biopsy, primary_diagnosis, has_metastasis, vital_status), `IN_GRAPH` (4
  echte Proben mit Graph-Kontext) + `SYNTHETIC` (20).
- Referenz-Mechanik (nur lesen, NICHT importieren — anderes Repo):
  `morphing-projections-demo-and-dataset-preparation-master/.../demo.py`
  → `circularEncoding(N, key)`, `linearEnc(df, col, dir)`, `update_source`
  (Stapeln von E, `z[0]=0.5` Basis-Gewicht), der `CodeJS`-CustomJS-Callback.
- `src/wissensnetz/enrichment.py` — `case_context` liefert die Klinik-Werte.

## Phase A — Deliverables (jetzt umsetzen)

### 1) Encoding-Helfer — neues Modul `prototype/mp_lite/encodings.py`
Portiere sinngemäß aus `demo.py` (eigene, saubere Implementierung, keine Kopie
mit fremdem Header):
- `circular_encoding(values: list[str|None]) -> np.ndarray (n,2)`:
  distinct Nicht-Null-Werte gleichmäßig auf einen Kreis; jede Probe an die
  Position ihrer Klasse. Fehlende Werte ("--"/None) → Ursprung (0,0).
- `linear_encoding(values: list[float|None], dir: str = "ver") -> np.ndarray (n,2)`:
  MinMax-Skalierung auf eine Achse (vertikal/horizontal), fehlende Werte → 0.
- `is_encodable(values) -> bool`: True nur, wenn ≥2 distinct Nicht-Null-Werte
  existieren (sonst kann die Variable nichts morphen).
Reines numpy, keine sklearn-Pflicht (MinMax selbst rechnen ist ok).

### 2) Morph-Engine in `prototype/mp_lite/app.py`
- Für jede **morphbare** Variable eine Anordnung `E[i]` bauen:
  - Basis-View behalten: das bestehende synthetische „Gene"-Layout (L0) als
    `E[0]`, Startgewicht 0.5 (wie `z[0]=0.5` im Original), damit bei allen
    Slidern = 0 ein sinnvolles Grundbild bleibt. „miRNA" (L1) als zweite
    Basis-View `E[1]`.
  - Klinische Variablen (aus den CDS-Spalten von Aufgabe 5): pro Variable
    `circular_encoding(...)` über die Werte der 24 Proben. **Nur** aufnehmen,
    wenn `is_encodable(...)` True ist — sonst Slider weglassen ODER als
    `disabled=True` mit Titel-Hinweis „(keine Daten)". Ordinale wie
    `tumor_stage` optional zusätzlich als `linear_encoding(..., "ver")`.
  - Erwartung real: mit den aktuellen Daten sind i. d. R. nur `cancer`,
    `gender`, `primary_diagnosis` encodierbar; der Rest steht auf `--` und wird
    als deaktivierter Slider gezeigt (macht die Datenlücke sichtbar).
- Alle `E[i]` zu `E_stack` (n, 2·k) stapeln und als `source.data['E']` ablegen.
- **Slider**: einen `Slider(start=0, end=1, step=0.01)` pro aufgenommener Variable,
  Titel = Variablenname; der Basis-Slider „genes" auf value=0.5.
- **Client-seitiger Morph via `CustomJS`** (kein Server-Callback): softmax mit
  sens=10 über die Slider-Werte, `Epos[j] = Σ_i a_i · E[j][2i..2i+1]`, dann
  `source.data['pos_x'/'pos_y']` setzen und `source.change.emit()`. Direkt an
  `slider.js_on_change('value', cb)` hängen. (Der alte `on_morph`-Server-Callback
  und `_blend`/`morph`-Einzelslider entfallen bzw. werden ersetzt.)
- Hover (Aufgabe 5), Kontext-Panel ② und Rückkanal ③ bleiben voll funktionsfähig.
  Coloring wie bisher.

### 3) Sichtbar machen, was fehlt
Ein kleines `Div` unter den Slidern listet die Variablen, die mangels Daten
deaktiviert sind (z. B. „race, ethnicity, tumor_stage, … — noch keine Werte im
Graphen, siehe HANDOFF"). So ist die Datenlücke im UI ehrlich sichtbar.

## Phase B — Deliverable (Hand-off, kein Fremd-Code anfassen)
### 4) `prototype/mp_lite/HANDOFF_morphing_daten.md`
Dokumentieren, welche Daten zuerst durch die Kette müssen, damit die restlichen
Slider echt morphen — getrennt nach zwei Quellen:
- **Klinische Slider** (race, ethnicity, tumor_stage, morphology,
  has_metastasis, vital_status, type): hängen an den in `HANDOFF_oviedo_felder.md`
  (Aufgabe 5) genannten Feldern — sobald Mediator/Wrapper sie liefern, werden die
  Slider automatisch aktiv (circular/linear encoding greift dann). Hier nur
  rückverweisen.
- **Expressions-Slider** (genes-tSNE, miRNA-tSNE, sowie Einzelmarker wie
  miRNA-210-3p, CA9, SAA1): **komplett fehlende Datenquelle.** Benötigt:
  (a) pro Probe Expressionsvektoren (DNA/miRNA) — der `anndata`/`.h5ad`-Teil der
  Architektur, aktuell nicht ins Wissensnetz integriert;
  (b) vorberechnete 2D-tSNE-Layouts für genes und miRNA (im Original
  `pancancer_morphing.hdf`, Spalten genes_x/y, mirna_x/y);
  (c) Einzel-Marker-Spalten (z. B. Ensembl/MIMAT-IDs) für lineare Encodings.
  Offene Architekturfrage notieren: kommen Expressionswerte über den Graphen
  (Tripel/Literals) oder über einen Seitenkanal (h5ad direkt in den Prototyp)?
  → mit Team klären (Mediator/Wrapper + Wissensnetz), nicht in dieser Aufgabe.
- Zusätzlich vermerken: aussagekräftiges Morphing braucht eine **echte Kohorte**
  statt 4 echte + 20 synthetische Proben.

## Verifikation
- `bokeh serve --show wissensnetz/prototype/mp_lite/app.py` startet fehlerfrei;
  mehrere Slider erscheinen; Ziehen eines aktiven Sliders (z. B. „cancer")
  verschiebt die Punkte flüssig; deaktivierte Slider sind klar erkennbar.
- Bestehende Tests bleiben grün: `pytest wissensnetz/tests -q`.
- Kleiner Unit-Test für `encodings.py` (neu, in `tests/`): `circular_encoding`
  liefert (n,2) mit Ursprung für None; `is_encodable` False bei 0/1 distinct
  Werten, True bei ≥2. Kein Fuseki nötig (reine numpy-Funktion).
- Robustheit: bei `STORE_OK=False` startet die App weiterhin (nur Basis-Views
  aktiv, Klinik-Slider deaktiviert).

Halte dich strikt an die Komponentengrenze. Alles, was nur mit echten Expressions-
oder Klinikdaten lösbar wäre, kommt in die Hand-off-Notiz, nicht in den Code.
