"""MP-lite — Prototyp: Morphing-Projections-artige Visualisierung, direkt an das
Wissensnetz gekoppelt (Bokeh-Server, in-process).

Zweck: den geschlossenen Loop MP ↔ Wissensnetz vorführen, ohne die (2020er)
Original-``demo.py`` von Oviedo wiederbeleben zu müssen. Faithful zum MP-Konzept
im Kleinen: ein Scatter mit Box-/Lasso-Select und — wie im Original — **ein
Slider pro Variable**. Die finale Position ist die softmax-gewichtete Summe der
Encodings (Σ a_i·E[i], a = softmax(10·slider)); der Callback läuft clientseitig
(CustomJS). Basis-Views „genes"/„miRNA" plus, sofern encodierbar, Kreis-Encodings
der klinischen Variablen (Aufgabe 5). Variablen ohne Daten erscheinen als
deaktivierte Slider (ehrliche Datenlücke, siehe HANDOFF_morphing_daten.md).

Kopplung an das Wissensnetz (Paket ``wissensnetz``, in-process — kein REST nötig):
  ② Anreicherung:  Auswahl/Selektion einer Probe → ``enrichment.case_context()``
                   → Kontext (Projekt, Diagnose, …) im Seitenpanel.
  ③ Rückkanal:     Selektion + Hypothese → ``feedback.write_feedback()``
                   → Named Graph pro Nutzer; ``list_findings()`` zeigt sie an.

Voraussetzungen & Start: siehe ../README.md
  docker compose up -d graph-db
  pip install -e ./wissensnetz  &&  pip install bokeh
  wissensnetz init  &&  wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl
  bokeh serve --show wissensnetz/prototype/mp_lite/app.py

SPÄTER (Zielweg): dieselben Hooks gegen die echte MP-Web-Version. Diese App ist
bewusst getrennt gehalten; sie importiert nur ``wissensnetz`` und fasst weder
``mediator/``/``wrappers/`` noch die eingebettete Oviedo-``demo.py`` an.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from bokeh.layouts import column, row
from bokeh.models import (
    Button, ColumnDataSource, CustomJS, Div, HoverTool, Slider, TextInput,
)
from bokeh.plotting import curdoc, figure

from wissensnetz import (
    GraphStore,
    Hypothesis,
    SelectionEvent,
    all_cases,
    case_context,
    initialize,
    list_findings,
    write_feedback,
)
from wissensnetz.cohorts import OVIEDO_COHORTS, cancer_code

# encodings.py liegt neben dieser Datei und wird per Dateipfad geladen — NICHT
# via ``import encodings``, das mit Pythons stdlib-Paket ``encodings`` (Codecs)
# kollidieren würde. So bleibt der stdlib-Import unangetastet.
import importlib.util as _ilu

_enc_spec = _ilu.spec_from_file_location(
    "mp_lite_encodings", Path(__file__).resolve().parent / "encodings.py"
)
_enc = _ilu.module_from_spec(_enc_spec)
_enc_spec.loader.exec_module(_enc)
circular_encoding = _enc.circular_encoding
is_encodable = _enc.is_encodable

# --------------------------------------------------------------------------
# Store bereitstellen (Fuseki). Idempotentes init + Beispiel-ABox laden, damit
# die Anreicherung (②) für die enthaltenen Proben Kontext liefert.
# --------------------------------------------------------------------------
FIXTURE = Path(__file__).resolve().parents[2] / "data" / "sample" / "cases_brca_sample.ttl"

store = GraphStore()
STORE_OK = store.is_reachable()
_boot_msg = ""
if STORE_OK:
    try:
        initialize(store)
        if FIXTURE.exists():
            store.load_turtle(FIXTURE)
        _boot_msg = f"Fuseki erreichbar · Dataset '{store.settings.dataset}' · Beispieldaten geladen."
    except Exception as exc:  # noqa: BLE001 (Prototyp: Startfehler nur anzeigen)
        STORE_OK = False
        _boot_msg = f"Fuseki erreichbar, aber Init/Load fehlgeschlagen: {exc}"
else:
    _boot_msg = (f"Fuseki NICHT erreichbar unter {store.settings.base_url} — "
                 "'docker compose up -d graph-db' starten und App neu laden.")

# --------------------------------------------------------------------------
# Kohorten-Farben (Aufgabe 7): stabile Farbe je Krebsart über die Position in
# OVIEDO_COHORTS. matplotlib-``nipy_spectral`` wie im Original, mit HSV-Fallback,
# falls matplotlib fehlt. Unbekannte/fehlende Kohorte -> neutrales Grau.
# --------------------------------------------------------------------------
GRAY = "#9E9E9E"


def _build_cohort_colors() -> dict[str, str]:
    codes = list(OVIEDO_COHORTS)
    n = len(codes)
    try:
        from matplotlib import colormaps
        from matplotlib.colors import to_hex
        cmap = colormaps["nipy_spectral"]
        return {c: to_hex(cmap((i + 0.5) / n)) for i, c in enumerate(codes)}
    except Exception:  # noqa: BLE001 (kein matplotlib -> HSV-Fallback)
        import colorsys
        out: dict[str, str] = {}
        for i, c in enumerate(codes):
            r, g, b = colorsys.hsv_to_rgb(i / n, 0.65, 0.9)
            out[c] = "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))
        return out


COHORT_COLORS = _build_cohort_colors()


def _cohort_color(code: str | None) -> str:
    return COHORT_COLORS.get(code, GRAY) if code else GRAY


def _dash(v: object) -> str:
    """``str(v)`` wenn ``v`` einen Wert hat, sonst ``"--"`` (wie im Oviedo-Tool)."""
    return str(v) if v not in (None, "") else "--"


# Oviedo-Hover-Spalten in exakter Reihenfolge; Default überall "--".
_FIELDS = ("cancer", "sample_type", "race", "gender", "ethnicity", "tumor_stage",
           "morphology", "site_biopsy", "primary_diagnosis", "has_metastasis",
           "vital_status")


def _fill_fields(fields: dict[str, list[str]], i: int, *, code: str | None,
                 race, gender, ethnicity, vital, tumor_stage, morphology,
                 site, dx, metastasis) -> None:
    """Eine Zeile der Hover-Spalten setzen (``sample_type`` bleibt "--" — GDC-
    'sample' ist noch nicht modelliert, siehe HANDOFF_oviedo_felder.md)."""
    fields["cancer"][i] = _dash(code)
    fields["race"][i] = _dash(race)
    fields["gender"][i] = _dash(gender)
    fields["ethnicity"][i] = _dash(ethnicity)
    fields["vital_status"][i] = _dash(vital)
    fields["tumor_stage"][i] = _dash(tumor_stage)
    fields["morphology"][i] = _dash(morphology)
    fields["site_biopsy"][i] = _dash(site)
    fields["primary_diagnosis"][i] = _dash(dx)
    fields["has_metastasis"][i] = _dash(metastasis)


# --------------------------------------------------------------------------
# Fälle beschaffen (Aufgabe 7): bevorzugt ECHTE Fälle aus dem Graphen
# (all_cases). Ist der Store leer/nicht erreichbar, Fallback auf die bisherige
# Beispiel-/Synthetik-Logik, damit die App standalone lauffähig bleibt.
# --------------------------------------------------------------------------
real_cases: list[dict] = []
if STORE_OK:
    try:
        real_cases = all_cases(store)
    except Exception:  # noqa: BLE001 (Prototyp: robust -> Fallback)
        real_cases = []

point_codes: list[str | None]
if real_cases:
    DATA_SOURCE = f"{len(real_cases)} echte Fälle aus dem Graphen"
    TUMORS = [
        (c.get("submitter_id") or c.get("case_iri") or f"case-{i}")
        for i, c in enumerate(real_cases)
    ]
    N = len(TUMORS)
    fields = {f: ["--"] * N for f in _FIELDS}
    point_codes = [None] * N
    for i, c in enumerate(real_cases):
        code = cancer_code(c.get("project_id"))
        point_codes[i] = code
        _fill_fields(
            fields, i, code=code, race=c.get("race"), gender=c.get("gender"),
            ethnicity=c.get("ethnicity"), vital=c.get("vital_status"),
            tumor_stage=c.get("tumor_stage"), morphology=c.get("morphology"),
            site=c.get("site_of_resection_or_biopsy"),
            dx=c.get("primary_diagnosis"), metastasis=c.get("has_metastasis"),
        )
else:
    # Fallback: 4 Fixture-Barcodes + 20 synthetische Punkte (wie bisher).
    DATA_SOURCE = "Fallback: 4 Beispiel-Fälle + 20 synthetische Punkte (leerer Store)"
    IN_GRAPH = ["TCGA-A1-A0SB", "TCGA-A1-A0SD", "TCGA-A1-A0SE", "TCGA-A1-A0SH"]
    SYNTHETIC = [f"SYN-{i:04d}" for i in range(1, 21)]
    TUMORS = IN_GRAPH + SYNTHETIC
    N = len(TUMORS)
    fields = {f: ["--"] * N for f in _FIELDS}
    point_codes = [None] * N
    if STORE_OK:
        for i, barcode in enumerate(IN_GRAPH):
            try:
                ctx = case_context(store, barcode)
            except Exception:  # noqa: BLE001 (Prototyp: robust bleiben -> "--")
                ctx = {}
            if not ctx:
                continue
            code = cancer_code(ctx.get("project_id"))
            point_codes[i] = code
            diags = ctx.get("diagnoses") or []
            d0 = diags[0] if diags else {}
            _fill_fields(
                fields, i, code=code, race=ctx.get("race"), gender=ctx.get("gender"),
                ethnicity=ctx.get("ethnicity"), vital=ctx.get("vital_status"),
                tumor_stage=d0.get("tumor_stage"), morphology=d0.get("morphology"),
                site=d0.get("site_of_resection_or_biopsy"), dx=d0.get("label"),
                metastasis=d0.get("has_metastasis"),
            )

# Farbe je Fall nach Krebsart; vorkommende Kohorten in OVIEDO_COHORTS-Reihenfolge.
color = [_cohort_color(code) for code in point_codes]
_present = {code for code in point_codes if code}
present_cohorts = [c for c in OVIEDO_COHORTS if c in _present]
has_uncolored = any(code is None for code in point_codes)

# Basis-Views „genes"/„miRNA" bleiben synthetische Platzhalter (bis Expressions-
# daten integriert sind, siehe HANDOFF_morphing_daten.md) — Punktzahl an die
# echte Fallzahl N angepasst, deterministisch erzeugt.
rng = np.random.default_rng(42)
L0 = rng.normal(0.0, 2.5, size=(N, 2))
L1 = rng.normal(0.0, 2.5, size=(N, 2))


# --------------------------------------------------------------------------
# Multi-Variablen-Morph-Engine (Aufgabe 6) — mechanisch wie das Oviedo-Original:
#   finale Position = Σ  a_i · E[i]     mit  a = softmax(SENS · slider_werte)
# Jedes E[i] ist eine (N, 2)-Anordnung; alle werden zu (N, 2·k) gestapelt und
# clientseitig (CustomJS) gewichtet. Basis-Views „genes"/„miRNA" (L0/L1) bleiben
# erhalten; klinische Variablen kommen — sofern encodierbar — als Kreis-Encoding
# hinzu. Nicht encodierbare Variablen (zu wenig Daten) werden als deaktivierte
# Slider gezeigt (ehrliche Datenlücke, siehe Div unten + HANDOFF).
# --------------------------------------------------------------------------
SENS = 10.0          # Sensibilitäts-Koeffizient der softmax (wie Original)
CIRCLE_SCALE = 5.0   # Radius der Kreis-Encodings (vergleichbar mit L0/L1-Spanne)
BASE_WEIGHT = 0.5    # Startgewicht der Basis-View E[0] (wie z[0]=0.5 im Original)


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - np.max(z))
    return e / e.sum()


# E[0] = „genes" (Basis, Startgewicht 0.5), E[1] = „miRNA" (zweite Basis-View).
encoding_names: list[str] = ["genes", "miRNA"]
E_arrays: list[np.ndarray] = [L0.copy(), L1.copy()]
slider_init: list[float] = [BASE_WEIGHT, 0.0]

# Klinische Variablen in Oviedo-Reihenfolge; Slider-Titel = Feldname wie im Hover.
_CLINICAL_ORDER = ("cancer", "sample_type", "race", "gender", "ethnicity",
                   "tumor_stage", "morphology", "site_biopsy",
                   "primary_diagnosis", "has_metastasis", "vital_status")
disabled_vars: list[str] = []
for _var in _CLINICAL_ORDER:
    _vals = fields[_var]
    if is_encodable(_vals):
        encoding_names.append(_var)
        E_arrays.append(CIRCLE_SCALE * circular_encoding(_vals))
        slider_init.append(0.0)
    else:
        disabled_vars.append(_var)

# E_stack: (N, 2·k) — je Zeile [E0x,E0y, E1x,E1y, …]; als Liste in die CDS,
# damit der CustomJS-Callback clientseitig darauf zugreift.
E_stack = np.concatenate(E_arrays, axis=1)

# Startpositionen serverseitig mit den Default-Slider-Werten berechnen, damit der
# erste Render zum CustomJS passt (der erst bei Slider-Änderung feuert).
_a0 = _softmax(SENS * np.asarray(slider_init))
_Epos0 = np.zeros((N, 2))
for _i, _arr in enumerate(E_arrays):
    _Epos0 += _a0[_i] * _arr

source = ColumnDataSource(dict(
    tumor=TUMORS, color=color,
    pos_x=_Epos0[:, 0].tolist(), pos_y=_Epos0[:, 1].tolist(),
    E=E_stack.tolist(), **fields,
))

# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------
plot = figure(
    width=760, height=620, title="MP-lite — Cancer Map (Multi-Variablen-Morph)",
    tools="pan,box_select,lasso_select,tap,wheel_zoom,reset,save",
    x_range=(-9, 9), y_range=(-9, 9), output_backend="webgl",
)
plot.scatter("pos_x", "pos_y", source=source, size=11, color="color",
             alpha=0.75, nonselection_alpha=0.2, line_color="#333333")
# Hover = volle Oviedo-MP-Feldliste in exakter Reihenfolge (fehlend -> "--").
plot.add_tools(HoverTool(tooltips=[
    ("Sample", "@tumor"), ("cancer", "@cancer"), ("type", "@sample_type"),
    ("race", "@race"), ("gender", "@gender"), ("ethnicity", "@ethnicity"),
    ("tumor_stage", "@tumor_stage"), ("morphology", "@morphology"),
    ("site_of_resection_or_biopsy", "@site_biopsy"),
    ("primary_diagnosis", "@primary_diagnosis"),
    ("has_metastasis", "@has_metastasis"), ("vital_status", "@vital_status"),
]))

# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------
# Ein Slider je aufgenommener Encoding-Variable (Basis + encodierbare Klinik),
# in E-Reihenfolge — der CustomJS-Callback erwartet exakt diese Reihenfolge.
morph_sliders = [
    Slider(start=0.0, end=1.0, value=slider_init[i], step=0.01, width=300,
           title=name)
    for i, name in enumerate(encoding_names)
]
genes_slider = morph_sliders[0]  # Basis-View „genes" (Startgewicht 0.5)
# Deaktivierte Slider für Variablen ohne (ausreichende) Daten — sichtbare Lücke.
disabled_sliders = [
    Slider(start=0.0, end=1.0, value=0.0, step=0.01, width=300, disabled=True,
           title=f"{var}  (keine Daten)")
    for var in disabled_vars
]
conf = Slider(start=0.0, end=1.0, value=0.7, step=0.05, width=300, title="Konfidenz")
user_in = TextInput(title="Nutzer", value="marcel", width=300)
from_in = TextInput(title="Hypothese: von (CURIE/IRI)", value="ncit:PAAD", width=300)
to_in = TextInput(title="Hypothese: nach (CURIE/IRI)", value="ncit:PanNET", width=300)
note_in = TextInput(title="Notiz", value="Common fate: driften gemeinsam", width=300)
save_btn = Button(label="③  Selektion als Erkenntnis speichern", button_type="primary", width=300)
refresh_btn = Button(label="Erkenntnisse aktualisieren", button_type="default", width=300)

boot_div = Div(text=f"<b>Status:</b> {_boot_msg}", width=320)
data_div = Div(text=f"<b>Daten:</b> {DATA_SOURCE}", width=320)


def _legend_html() -> str:
    """Kompakte Farb-Legende je Krebsart in OVIEDO_COHORTS-Reihenfolge."""
    if not present_cohorts and not has_uncolored:
        return "<i>keine Kohorten im Datensatz.</i>"

    def _chip(hexcol: str, label: str) -> str:
        return (
            "<div style='display:flex;align-items:center;margin:1px 0'>"
            f"<span style='display:inline-block;width:12px;height:12px;flex:0 0 auto;"
            f"border:1px solid #333;background:{hexcol};margin-right:6px'></span>"
            f"<span>{label}</span></div>"
        )

    rows = [_chip(COHORT_COLORS.get(c, GRAY), c) for c in present_cohorts]
    if has_uncolored:
        rows.append(_chip(GRAY, "<i>ohne Kohorte</i>"))
    return (
        f"<b>Krebsart ({len(present_cohorts)} Kohorte(n)):</b>"
        "<div style='max-height:220px;overflow:auto;font-size:12px'>"
        + "".join(rows) + "</div>"
    )


legend_div = Div(text=_legend_html(), width=320)
ctx_div = Div(text="<i>Punkt(e) auswählen (Tap/Box-Select) für Kontext ②</i>", width=320)
status_div = Div(text="", width=320)
findings_div = Div(text="", width=320)

# ③-fremd, aber Kern von Aufgabe 6: welche Variablen mangels Daten deaktiviert
# sind — macht die Datenlücke im UI ehrlich sichtbar.
if disabled_vars:
    _missing_text = (
        "<b>Ohne Daten deaktiviert:</b> " + ", ".join(disabled_vars)
        + " — noch keine Werte im Graphen. Sobald Mediator/Wrapper sie liefern, "
        "werden die Slider automatisch aktiv (siehe HANDOFF_morphing_daten.md)."
    )
else:
    _missing_text = "<i>Alle Variablen encodierbar.</i>"
missing_div = Div(text=_missing_text, width=320)


# --------------------------------------------------------------------------
# ② Anreicherung: Selektion → case_context
# --------------------------------------------------------------------------
def _render_context(barcode: str) -> str:
    if not STORE_OK:
        return "<span style='color:#b00'>Store nicht verfügbar.</span>"
    ctx = case_context(store, barcode)
    if not ctx:
        return f"<b>{barcode}</b><br><i>kein Kontext im Wissensnetz.</i>"
    diags = "".join(
        f"<li>{d.get('label') or '—'}"
        + (f" · Alter {d['age_at_diagnosis']}" if d.get("age_at_diagnosis") is not None else "")
        + (f" · <span style='color:#2E74B5'>{d['aligned_concept']}</span>" if d.get("aligned_concept") else "")
        + "</li>"
        for d in ctx.get("diagnoses", [])
    ) or "<li>—</li>"
    return (
        f"<b>{barcode}</b><br>"
        f"Projekt: {ctx.get('project_id') or '—'} · Geschlecht: {ctx.get('gender') or '—'}<br>"
        f"Diagnosen:<ul>{diags}</ul>"
    )


def on_select(attr, old, new):
    if not new:
        ctx_div.text = "<i>Punkt(e) auswählen für Kontext ②</i>"
        return
    barcodes = [TUMORS[i] for i in new]
    head = f"<b>{len(barcodes)} Probe(n) selektiert.</b> Kontext der ersten:<br>"
    ctx_div.text = head + _render_context(barcodes[0])


source.selected.on_change("indices", on_select)


# --------------------------------------------------------------------------
# Morph-Callback (client-seitig via CustomJS, für flüssige Interaktion):
#   a = softmax(SENS · slider_werte);  pos[j] = Σ_i a_i · E[j][2i .. 2i+1]
# Läuft im Browser, kein Server-Roundtrip pro Slider-Tick.
# --------------------------------------------------------------------------
morph_cb = CustomJS(args=dict(source=source, s=morph_sliders, sens=SENS), code="""
  // Slider-Werte -> softmax-Gewichte a (Sensibilität sens)
  const z = s.map(w => w.value * sens);
  const ez = z.map(v => Math.exp(v));
  const sum_ez = ez.reduce((acc, v) => acc + v, 0);
  const a = ez.map(v => v / sum_ez);

  // gewichtete Summe der Encodings E (je Zeile [E0x,E0y, E1x,E1y, …])
  const E = source.data['E'];
  const n = E.length;
  const px = new Array(n);
  const py = new Array(n);
  for (let j = 0; j < n; j++) {
    let x = 0.0, y = 0.0;
    for (let i = 0; i < a.length; i++) {
      x += a[i] * E[j][2 * i];
      y += a[i] * E[j][2 * i + 1];
    }
    px[j] = x;
    py[j] = y;
  }
  source.data['pos_x'] = px;
  source.data['pos_y'] = py;
  source.change.emit();
""")
for _slider in morph_sliders:
    _slider.js_on_change("value", morph_cb)


# --------------------------------------------------------------------------
# ③ Rückkanal: Selektion + Hypothese → write_feedback
# --------------------------------------------------------------------------
def on_save():
    if not STORE_OK:
        status_div.text = "<span style='color:#b00'>Store nicht verfügbar — nicht gespeichert.</span>"
        return
    idx = source.selected.indices
    if not idx:
        status_div.text = "<span style='color:#b00'>Keine Probe selektiert.</span>"
        return
    barcodes = [TUMORS[i] for i in idx]
    event = SelectionEvent(
        user=user_in.value.strip() or "anonymous",
        samples=barcodes,
        hypothesis=Hypothesis(
            from_=from_in.value.strip() or "db:Unspecified",
            to=to_in.value.strip() or "db:Unspecified",
            note=note_in.value.strip() or None,
            tag="mp-lite",
        ),
        view="MP-lite: multi-variable morph",
        morph_param=float(genes_slider.value),
        confidence=float(conf.value),
    )
    graph_iri = write_feedback(store, event)
    status_div.text = (
        f"<span style='color:#2E7D32'>Gespeichert:</span> {len(barcodes)} Probe(n) "
        f"→ <code>{graph_iri}</code>"
    )
    _refresh_findings()


def _refresh_findings():
    if not STORE_OK:
        return
    items = list_findings(store)
    if not items:
        findings_div.text = "<i>(noch keine Erkenntnisse)</i>"
        return
    rows = "".join(
        f"<li>{f.get('user') or '—'}: {(f['hypothesis'].get('from') or '—')} → "
        f"{(f['hypothesis'].get('to') or '—')} · {len(f.get('targets') or [])} Probe(n)</li>"
        for f in items
    )
    findings_div.text = f"<b>Erkenntnisse ({len(items)}):</b><ul>{rows}</ul>"


save_btn.on_click(on_save)
refresh_btn.on_click(_refresh_findings)
_refresh_findings()

# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
sidebar = column(
    boot_div, data_div,
    Div(text="<hr><b>Legende — Krebsart</b>", width=320), legend_div,
    Div(text="<hr><b>Morphing-Slider</b> (Σ softmax, sens=10)", width=320),
    *morph_sliders, *disabled_sliders, missing_div,
    Div(text="<hr><b>② Kontext</b>", width=320), ctx_div,
    Div(text="<hr><b>③ Erkenntnis speichern</b>", width=320),
    user_in, from_in, to_in, note_in, conf, save_btn, status_div,
    Div(text="<hr>", width=320), refresh_btn, findings_div,
    width=340,
)
curdoc().add_root(row(plot, sidebar))
curdoc().title = "MP-lite × Wissensnetz (Prototyp)"
