"""MP-lite — Prototyp: Morphing-Projections-artige Visualisierung, direkt an das
Wissensnetz gekoppelt (Bokeh-Server, in-process).

Zweck: den geschlossenen Loop MP ↔ Wissensnetz vorführen, ohne die (2020er)
Original-``demo.py`` von Oviedo wiederbeleben zu müssen. Faithful zum MP-Konzept
im Kleinen: ein Scatter mit Box-/Lasso-Select und ein Morph-Slider, der die
Punkte konvex zwischen zwei Layouts (hier „Gene" ↔ „miRNA") überblendet.

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
from bokeh.models import Button, ColumnDataSource, Div, HoverTool, Slider, TextInput
from bokeh.plotting import curdoc, figure

from wissensnetz import (
    GraphStore,
    Hypothesis,
    SelectionEvent,
    case_context,
    initialize,
    list_findings,
    write_feedback,
)

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
# Beispiel-Daten (self-contained). Die vier ersten Barcodes stammen aus der
# Fixture cases_brca_sample.ttl und HABEN Kontext im Graphen; die übrigen sind
# synthetisch (zeigen den „kein Kontext"-Fall). Zwei 2D-Layouts (Gene/miRNA)
# zum Morphen, deterministisch erzeugt.
# --------------------------------------------------------------------------
IN_GRAPH = ["TCGA-A1-A0SB", "TCGA-A1-A0SD", "TCGA-A1-A0SE", "TCGA-A1-A0SH"]
SYNTHETIC = [f"SYN-{i:04d}" for i in range(1, 21)]
TUMORS = IN_GRAPH + SYNTHETIC
N = len(TUMORS)

rng = np.random.default_rng(42)
# Layout 0 („Gene"): Fixture-Proben clustern links, synthetische streuen.
L0 = rng.normal(0, 1.0, size=(N, 2))
L0[: len(IN_GRAPH)] += np.array([-4.0, 2.0])
# Layout 1 („miRNA"): andere Anordnung.
L1 = rng.normal(0, 1.0, size=(N, 2))
L1[: len(IN_GRAPH)] += np.array([3.5, -2.5])

cancer = ["BRCA"] * len(IN_GRAPH) + ["synthetic"] * len(SYNTHETIC)
in_graph = ["ja"] * len(IN_GRAPH) + ["nein"] * len(SYNTHETIC)
color = ["#2E7D32"] * len(IN_GRAPH) + ["#9E9E9E"] * len(SYNTHETIC)


def _blend(t: float) -> tuple[list[float], list[float]]:
    pos = (1.0 - t) * L0 + t * L1
    return pos[:, 0].tolist(), pos[:, 1].tolist()


x0, y0 = _blend(0.0)
source = ColumnDataSource(dict(
    tumor=TUMORS, cancer=cancer, in_graph=in_graph, color=color,
    pos_x=x0, pos_y=y0,
))

# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------
plot = figure(
    width=760, height=620, title="MP-lite — Cancer Map (Gene ↔ miRNA morph)",
    tools="pan,box_select,lasso_select,tap,wheel_zoom,reset,save",
    x_range=(-8, 8), y_range=(-8, 8), output_backend="webgl",
)
plot.scatter("pos_x", "pos_y", source=source, size=11, color="color",
             alpha=0.75, nonselection_alpha=0.2, line_color="#333333")
plot.add_tools(HoverTool(tooltips=[("Sample", "@tumor"), ("Cancer", "@cancer"),
                                   ("im Graph", "@in_graph")]))

# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------
morph = Slider(start=0.0, end=1.0, value=0.0, step=0.01, width=300,
               title="Morph  t   (0 = Gene, 1 = miRNA)")
conf = Slider(start=0.0, end=1.0, value=0.7, step=0.05, width=300, title="Konfidenz")
user_in = TextInput(title="Nutzer", value="marcel", width=300)
from_in = TextInput(title="Hypothese: von (CURIE/IRI)", value="ncit:PAAD", width=300)
to_in = TextInput(title="Hypothese: nach (CURIE/IRI)", value="ncit:PanNET", width=300)
note_in = TextInput(title="Notiz", value="Common fate: driften gemeinsam", width=300)
save_btn = Button(label="③  Selektion als Erkenntnis speichern", button_type="primary", width=300)
refresh_btn = Button(label="Erkenntnisse aktualisieren", button_type="default", width=300)

boot_div = Div(text=f"<b>Status:</b> {_boot_msg}", width=320)
ctx_div = Div(text="<i>Punkt(e) auswählen (Tap/Box-Select) für Kontext ②</i>", width=320)
status_div = Div(text="", width=320)
findings_div = Div(text="", width=320)


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
# Morph-Slider (server-seitig, einfacher konvexer Blend)
# --------------------------------------------------------------------------
def on_morph(attr, old, new):
    xs, ys = _blend(float(new))
    source.data["pos_x"] = xs
    source.data["pos_y"] = ys


morph.on_change("value", on_morph)


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
        view="MP-lite: gene <-> miRNA",
        morph_param=float(morph.value),
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
    boot_div, morph,
    Div(text="<hr><b>② Kontext</b>", width=320), ctx_div,
    Div(text="<hr><b>③ Erkenntnis speichern</b>", width=320),
    user_in, from_in, to_in, note_in, conf, save_btn, status_div,
    Div(text="<hr>", width=320), refresh_btn, findings_div,
    width=340,
)
curdoc().add_root(row(plot, sidebar))
curdoc().title = "MP-lite × Wissensnetz (Prototyp)"
