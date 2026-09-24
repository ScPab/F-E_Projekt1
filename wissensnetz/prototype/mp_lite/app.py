"""MP-lite — Prototyp: Morphing-Projections-artige Visualisierung, direkt an das
Wissensnetz gekoppelt (Bokeh-Server, in-process).

Zweck: den geschlossenen Loop MP ↔ Wissensnetz vorführen, ohne die (2020er)
Original-``demo.py`` von Oviedo wiederbeleben zu müssen. Faithful zum MP-Konzept
im Kleinen: ein Scatter mit Box-/Lasso-Select und — wie im Original — **ein
Slider pro Variable**. Die finale Position ist die softmax-gewichtete Summe der
Encodings (Σ a_i·E[i], a = softmax(10·slider)); der Callback läuft clientseitig
(CustomJS). Basis-Views „genes"/„miRNA", Einzelmarker-Slider (z. B. CA9/SAA1) und,
sofern encodierbar, Kreis-Encodings der klinischen Variablen (Aufgabe 5). Liegt ein
Expressions-``.h5ad`` vor (Aufgabe 9), speisen sich „genes" aus der echten tSNE
(``obsm``) und die Marker linear aus ``X``; sonst bleiben die Basis-Views
synthetisch. Variablen ohne Daten erscheinen als deaktivierte Slider (ehrliche
Datenlücke, siehe HANDOFF.md).

Layout exakt an Oviedos ``demo.py`` angeglichen (Aufgabe 11): links der Plot mit
Titel „Cancer map", Toolbar oben und der Kohorten-Legende rechts IM Plot; rechts
daneben Oviedos 15 Slider (feste Reihenfolge/Benennung), datengetrieben aktiv/
deaktiviert; Status, Kontext ② und Rückkanal ③ kompakt UNTER dem Plot.

Kopplung an das Wissensnetz (Paket ``wissensnetz``, in-process — kein REST nötig):
  ② Anreicherung:  Auswahl/Selektion einer Probe → ``enrichment.case_context()``
                   → Kontext (Projekt, Diagnose, …) im Seitenpanel.
  ③ Rückkanal:     Selektion + Hypothese → ``feedback.write_feedback()``
                   → Named Graph pro Nutzer; ``list_findings()`` zeigt sie an.

Voraussetzungen & Start: siehe ../README.md
  docker compose up -d graph-db
  pip install -e "./wissensnetz[prototype]"   # bokeh, numpy, anndata
  wissensnetz init  &&  wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl
  bokeh serve --show wissensnetz/prototype/mp_lite/app.py
  # Datenquelle konfigurierbar: ENV DATABRIDGE_H5AD (Pfad), DATABRIDGE_MARKERS (CA9,SAA1)

SPÄTER (Zielweg): dieselben Hooks gegen die echte MP-Web-Version. Diese App ist
bewusst getrennt gehalten; sie importiert nur ``wissensnetz`` und fasst weder
``mediator/``/``wrappers/`` noch die eingebettete Oviedo-``demo.py`` an.

English: MP-lite — prototype: a Morphing-Projections-like visualization,
coupled directly to the wissensnetz (Bokeh server, in-process).

Purpose: to demonstrate the closed loop MP ↔ wissensnetz without having to
revive Oviedo's (2020s) original ``demo.py``. Faithful to the MP concept in
miniature: a scatter plot with box/lasso select and — as in the original —
**one slider per variable**. The final position is the softmax-weighted sum
of the encodings (Σ a_i·E[i], a = softmax(10·slider)); the callback runs
client-side (CustomJS). Base views "genes"/"miRNA", single-marker sliders
(e.g. CA9/SAA1) and, where encodable, circular encodings of the clinical
variables (task 5). If an expression ``.h5ad`` is present (task 9),
"genes" is fed from the real tSNE (``obsm``) and the markers linearly from
``X``; otherwise the base views stay synthetic. Variables without data
appear as disabled sliders (an honest data gap, see HANDOFF.md).

Layout matched exactly to Oviedo's ``demo.py`` (task 11): the plot on the
left with title "Cancer map", toolbar on top and the cohort legend on the
right INSIDE the plot; next to it on the right, Oviedo's 15 sliders (fixed
order/naming), data-driven active/disabled; status, context ② and feedback
channel ③ compactly BELOW the plot.

Coupling to the wissensnetz (package ``wissensnetz``, in-process — no REST
needed):
  ② Enrichment:      selecting a sample → ``enrichment.case_context()``
                     → context (project, diagnosis, …) in the side panel.
  ③ Feedback channel: selection + hypothesis → ``feedback.write_feedback()``
                     → named graph per user; ``list_findings()`` displays them.

Prerequisites & start: see ../README.md
  docker compose up -d graph-db
  pip install -e "./wissensnetz[prototype]"   # bokeh, numpy, anndata
  wissensnetz init  &&  wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl
  bokeh serve --show wissensnetz/prototype/mp_lite/app.py
  # Data source configurable: ENV DATABRIDGE_H5AD (path), DATABRIDGE_MARKERS (CA9,SAA1)

LATER (target path): the same hooks against the real MP web version. This
app is deliberately kept separate; it only imports ``wissensnetz`` and
touches neither ``mediator/``/``wrappers/`` nor the embedded Oviedo
``demo.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from bokeh.layouts import column, row
from bokeh.models import (
    Button, ColumnDataSource, CustomJS, Div, HoverTool, Slider, TextInput,
)
from bokeh.events import DocumentReady
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
# EN: encodings.py lives next to this file and is loaded by file path — NOT
# via ``import encodings``, which would collide with Python's stdlib
# ``encodings`` package (codecs). This leaves the stdlib import untouched.
import importlib.util as _ilu

_enc_spec = _ilu.spec_from_file_location(
    "mp_lite_encodings", Path(__file__).resolve().parent / "encodings.py"
)
_enc = _ilu.module_from_spec(_enc_spec)
_enc_spec.loader.exec_module(_enc)
circular_encoding = _enc.circular_encoding
linear_encoding = _enc.linear_encoding
is_encodable = _enc.is_encodable

# h5ad_source.py (Aufgabe 9) ebenfalls per Dateipfad laden — konsistent mit dem
# Bokeh-Server-Kontext, in dem der mp_lite-Ordner nicht zwingend auf sys.path liegt.
# EN: Also load h5ad_source.py (task 9) by file path — consistent with the
# Bokeh server context, where the mp_lite folder is not necessarily on sys.path.
_h5_spec = _ilu.spec_from_file_location(
    "mp_lite_h5ad_source", Path(__file__).resolve().parent / "h5ad_source.py"
)
_h5 = _ilu.module_from_spec(_h5_spec)
_h5_spec.loader.exec_module(_h5)
load_h5ad = _h5.load_h5ad
resolve_h5ad_path = _h5.resolve_h5ad_path
points_from_obs = _h5.points_from_obs
marker_column = _h5.marker_column
layout = _h5.layout

# --------------------------------------------------------------------------
# Store bereitstellen (Fuseki). Idempotentes init + Beispiel-ABox laden, damit
# die Anreicherung (②) für die enthaltenen Proben Kontext liefert.
#
# EN: Provision the store (Fuseki). Idempotent init + load the sample ABox,
# so enrichment (②) supplies context for the contained samples.
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
    except Exception as exc:  # noqa: BLE001 (Prototyp: Startfehler nur anzeigen) / EN: noqa: BLE001 (prototype: just display startup errors)
        STORE_OK = False
        _boot_msg = f"Fuseki erreichbar, aber Init/Load fehlgeschlagen: {exc}"
else:
    _boot_msg = (f"Fuseki NICHT erreichbar unter {store.settings.base_url} — "
                 "'docker compose up -d graph-db' starten und App neu laden.")

# --------------------------------------------------------------------------
# Kohorten-Farben (Aufgabe 7): stabile Farbe je Krebsart über die Position in
# OVIEDO_COHORTS. matplotlib-``nipy_spectral`` wie im Original, mit HSV-Fallback,
# falls matplotlib fehlt. Unbekannte/fehlende Kohorte -> neutrales Grau.
#
# EN: Cohort colors (task 7): a stable color per cancer type via its
# position in OVIEDO_COHORTS. matplotlib's ``nipy_spectral`` as in the
# original, with an HSV fallback if matplotlib is missing. Unknown/missing
# cohort -> neutral gray.
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
    except Exception:  # noqa: BLE001 (kein matplotlib -> HSV-Fallback) / EN: noqa: BLE001 (no matplotlib -> HSV fallback)
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
    """``str(v)`` wenn ``v`` einen Wert hat, sonst ``"--"`` (wie im Oviedo-Tool).

    English: ``str(v)`` if ``v`` has a value, otherwise ``"--"`` (as in the Oviedo tool).
    """
    return str(v) if v not in (None, "") else "--"


# Oviedo-Hover-Spalten in exakter Reihenfolge; Default überall "--".
# EN: Oviedo hover columns in exact order; default "--" everywhere.
_FIELDS = ("cancer", "sample_type", "race", "sex_at_birth", "ethnicity", "tumor_stage",
           "morphology", "site_biopsy", "primary_diagnosis", "has_metastasis",
           "vital_status")


def _fill_fields(fields: dict[str, list[str]], i: int, *, code: str | None,
                 race, sex_at_birth, ethnicity, vital, sample_type, tumor_stage,
                 morphology, site, dx, metastasis) -> None:
    """Eine Zeile der Hover-Spalten setzen. ``sample_type`` (Oviedo-Spalte 'type')
    kommt aus ``db:Sample``/``db:sampleType`` (Aufgabe 8) und bleibt "--", bis der
    Mediator ``samples.sample_type`` mappt (HANDOFF.md, Teil 2).

    English: Sets one row of the hover columns. ``sample_type`` (Oviedo
    column 'type') comes from ``db:Sample``/``db:sampleType`` (task 8) and
    stays "--" until the mediator maps ``samples.sample_type`` (HANDOFF.md,
    part 2).
    """
    fields["cancer"][i] = _dash(code)
    fields["sample_type"][i] = _dash(sample_type)
    fields["race"][i] = _dash(race)
    fields["sex_at_birth"][i] = _dash(sex_at_birth)
    fields["ethnicity"][i] = _dash(ethnicity)
    fields["vital_status"][i] = _dash(vital)
    fields["tumor_stage"][i] = _dash(tumor_stage)
    fields["morphology"][i] = _dash(morphology)
    fields["site_biopsy"][i] = _dash(site)
    fields["primary_diagnosis"][i] = _dash(dx)
    fields["has_metastasis"][i] = _dash(metastasis)


# --------------------------------------------------------------------------
# Datenquellen-Priorität (Aufgabe 9):
#   1. Expressions-``.h5ad`` (Mediator-Artefakt) — Punkte/Hover aus ``obs``,
#      Encodings aus ``X``/``obsm`` (echtes Morphen der Expressions-Slider).
#   2. sonst der Graph (``all_cases``, Aufgabe 7) — wie bisher, Expressions-Slider
#      deaktiviert.
#   3. sonst Synthetik-Fallback, damit die App standalone lauffähig bleibt.
# ``.h5ad`` wird NUR gelesen; fehlt ``anndata``/die Datei, fällt es sauber (ohne
# Crash) auf den Graph-/Synthetik-Pfad zurück.
#
# EN: Data-source priority (task 9):
#   1. Expression ``.h5ad`` (mediator artifact) — points/hover from
#      ``obs``, encodings from ``X``/``obsm`` (real morphing of the
#      expression sliders).
#   2. otherwise the graph (``all_cases``, task 7) — as before, expression
#      sliders disabled.
#   3. otherwise a synthetic fallback, so the app stays runnable standalone.
# ``.h5ad`` is ONLY read; if ``anndata``/the file is missing, it falls
# cleanly (without a crash) back to the graph/synthetic path.
# --------------------------------------------------------------------------
adata = load_h5ad()
h5ad_points: list[dict] = []
h5ad_name = ""
if adata is not None:
    try:
        h5ad_points = points_from_obs(adata)
        h5ad_name = resolve_h5ad_path().name
    except Exception:  # noqa: BLE001 (Prototyp: robust -> nächster Pfad)
        # EN: noqa: BLE001 (prototype: stay robust -> next path)
        h5ad_points = []
H5AD_OK = bool(h5ad_points)

# Graph nur befragen, wenn kein ``.h5ad`` vorliegt (Priorität 2).
# EN: Only query the graph if no ``.h5ad`` is present (priority 2).
real_cases: list[dict] = []
if not H5AD_OK and STORE_OK:
    try:
        real_cases = all_cases(store)
    except Exception:  # noqa: BLE001 (Prototyp: robust -> Fallback)
        # EN: noqa: BLE001 (prototype: stay robust -> fallback)
        real_cases = []

point_codes: list[str | None]
if H5AD_OK:
    DATA_SOURCE = f"{len(h5ad_points)} Proben aus {h5ad_name}"
    TUMORS = [p["tumor"] for p in h5ad_points]
    N = len(TUMORS)
    fields = {f: ["--"] * N for f in _FIELDS}
    point_codes = [None] * N
    for i, p in enumerate(h5ad_points):
        # ``cancer`` (Kohorten-Code) steht direkt in ``obs``; zur Sicherheit aus
        # ``project_id`` ableiten, falls die Spalte mal fehlt.
        # EN: ``cancer`` (cohort code) sits directly in ``obs``; derived
        # from ``project_id`` as a safety net in case the column is ever missing.
        code = cancer_code(p.get("project_id")) or p.get("cancer")
        point_codes[i] = code
        _fill_fields(
            fields, i, code=code, race=p.get("race"),
            sex_at_birth=p.get("sex_at_birth") or p.get("gender"),
            ethnicity=p.get("ethnicity"), vital=p.get("vital_status"),
            sample_type=p.get("sample_type"),
            tumor_stage=p.get("tumor_stage"), morphology=p.get("morphology"),
            site=p.get("site_of_resection_or_biopsy"),
            dx=p.get("primary_diagnosis"), metastasis=p.get("has_metastasis"),
        )
elif real_cases:
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
            fields, i, code=code, race=c.get("race"),
            sex_at_birth=c.get("sex_at_birth") or c.get("gender"),
            ethnicity=c.get("ethnicity"), vital=c.get("vital_status"),
            sample_type=c.get("sample_type"),
            tumor_stage=c.get("tumor_stage"), morphology=c.get("morphology"),
            site=c.get("site_of_resection_or_biopsy"),
            dx=c.get("primary_diagnosis"), metastasis=c.get("has_metastasis"),
        )
else:
    # Fallback: 4 Fixture-Barcodes + 20 synthetische Punkte (wie bisher).
    # EN: Fallback: 4 fixture barcodes + 20 synthetic points (as before).
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
            except Exception:  # noqa: BLE001 (Prototyp: robust bleiben -> "--") / EN: noqa: BLE001 (prototype: stay robust -> "--")
                ctx = {}
            if not ctx:
                continue
            code = cancer_code(ctx.get("project_id"))
            point_codes[i] = code
            diags = ctx.get("diagnoses") or []
            d0 = diags[0] if diags else {}
            _fill_fields(
                fields, i, code=code, race=ctx.get("race"),
                sex_at_birth=ctx.get("sex_at_birth") or ctx.get("gender"),
                ethnicity=ctx.get("ethnicity"), vital=ctx.get("vital_status"),
                sample_type=ctx.get("sample_type"),
                tumor_stage=d0.get("tumor_stage"), morphology=d0.get("morphology"),
                site=d0.get("site_of_resection_or_biopsy"), dx=d0.get("label"),
                metastasis=d0.get("has_metastasis"),
            )

# Farbe je Fall nach Krebsart; vorkommende Kohorten in OVIEDO_COHORTS-Reihenfolge.
# EN: Color per case by cancer type; cohorts present, in OVIEDO_COHORTS order.
color = [_cohort_color(code) for code in point_codes]
_present = {code for code in point_codes if code}
present_cohorts = [c for c in OVIEDO_COHORTS if c in _present]
has_uncolored = any(code is None for code in point_codes)

# Basis-Views „genes"/„miRNA": im ``.h5ad``-Pfad die echten tSNE-Layouts aus
# ``obsm`` (Aufgabe 9), sonst synthetische Platzhalter — deterministisch, Punktzahl
# an die echte Fallzahl N angepasst. Die eigentliche Konstruktion erfolgt weiter
# unten (nach den Skalierungs-Konstanten CIRCLE_SCALE/BASE_WEIGHT).
# EN: Base views "genes"/"miRNA": on the ``.h5ad`` path, the real tSNE
# layouts from ``obsm`` (task 9), otherwise synthetic placeholders —
# deterministic, point count matched to the real case count N. The actual
# construction happens further below (after the scaling constants
# CIRCLE_SCALE/BASE_WEIGHT).
rng = np.random.default_rng(42)


# --------------------------------------------------------------------------
# Multi-Variablen-Morph-Engine (Aufgabe 6) — mechanisch wie das Oviedo-Original:
#   finale Position = Σ  a_i · E[i]     mit  a = softmax(SENS · slider_werte)
# Jedes E[i] ist eine (N, 2)-Anordnung; alle werden zu (N, 2·k) gestapelt und
# clientseitig (CustomJS) gewichtet. Basis-Views „genes"/„miRNA" (L0/L1) bleiben
# erhalten; klinische Variablen kommen — sofern encodierbar — als Kreis-Encoding
# hinzu. Nicht encodierbare Variablen (zu wenig Daten) werden als deaktivierte
# Slider gezeigt (ehrliche Datenlücke, siehe Div unten + HANDOFF).
#
# EN: Multi-variable morph engine (task 6) — mechanically like the Oviedo
# original:
#   final position = Σ  a_i · E[i]     with  a = softmax(SENS · slider values)
# Each E[i] is an (N, 2) array; all are stacked into (N, 2·k) and weighted
# client-side (CustomJS). Base views "genes"/"miRNA" (L0/L1) are kept;
# clinical variables are added — where encodable — as a circular encoding.
# Variables that can't be encoded (too little data) are shown as disabled
# sliders (an honest data gap, see the Div below + HANDOFF).
# --------------------------------------------------------------------------
SENS = 10.0          # Sensibilitäts-Koeffizient der softmax (wie Original) / EN: sensitivity coefficient of the softmax (as in the original)
CIRCLE_SCALE = 5.0   # Radius der Kreis-Encodings (vergleichbar mit L0/L1-Spanne) / EN: radius of the circular encodings (comparable to the L0/L1 range)
BASE_WEIGHT = 0.5    # Startgewicht der Basis-View E[0] (wie z[0]=0.5 im Original) / EN: initial weight of the base view E[0] (like z[0]=0.5 in the original)


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - np.max(z))
    return e / e.sum()


def _scale_layout(arr: np.ndarray, target: float = CIRCLE_SCALE) -> np.ndarray:
    """tSNE-/Roh-Layout zentrieren und auf einen mit den Kreis-/Linear-Encodings
    vergleichbaren Wertebereich skalieren (max. |Koordinate| ≈ ``target``). Nötig,
    weil tSNE-Koordinaten in ganz anderen Skalen liegen als die circular/linear
    Encodings — sonst würde das Morphen zwischen den Views optisch „springen".

    English: Centers a tSNE/raw layout and scales it to a value range
    comparable to the circular/linear encodings (max. |coordinate| ≈
    ``target``). Needed because tSNE coordinates live on entirely different
    scales than the circular/linear encodings — otherwise morphing between
    the views would visually "jump".
    """
    arr = np.asarray(arr, dtype=float)
    centered = arr - arr.mean(axis=0)
    peak = float(np.max(np.abs(centered))) if centered.size else 0.0
    return centered if peak == 0.0 else centered / peak * target


# --------------------------------------------------------------------------
# Encodings + Slider-Set exakt wie Oviedo (Aufgabe 11)
# --------------------------------------------------------------------------
# Genau Oviedos 15 Slider, in dieser Reihenfolge und Benennung (demo.py):
#   genes, mirna, cancer, type, race, gender, ethnicity, primary_diagnosis,
#   has_metastasis, vital_status, cancer (ver), tumor_stage (ver),
#   miRNA-210-3p (hor), CA9 (ver), SAA1 (hor)
# EINE bewusste Abweichung: Oviedos "gender" heisst bei uns "sex_at_birth" —
# GDC hat das Feld umbenannt, und fachlich ist es nicht dasselbe (siehe
# db:sexAtBirth in ontology/databridge-core.ttl).
# Ein Slider ist nur aktiv, wenn seine Encoding-Daten vorliegen; sonst wird er
# deaktiviert angezeigt (Titel-Zusatz „(keine Daten)"), damit das Set optisch dem
# Original entspricht. Nur die aktiven Slider (mit E-Array) treiben die Morph-Engine
# — in genau ihrer Reihenfolge (der CustomJS erwartet E in Slider-Reihenfolge).
# morphology/site_biopsy sind bei Oviedo KEINE Slider (nur Hover) und fehlen hier.
#
# EN: Encodings + slider set exactly like Oviedo (task 11)
# --------------------------------------------------------------------------
# Exactly Oviedo's 15 sliders, in this order and naming (demo.py):
#   genes, mirna, cancer, type, race, gender, ethnicity, primary_diagnosis,
#   has_metastasis, vital_status, cancer (ver), tumor_stage (ver),
#   miRNA-210-3p (hor), CA9 (ver), SAA1 (hor)
# ONE deliberate deviation: Oviedo's "gender" is called "sex_at_birth" here
# — GDC renamed the field, and it is not the same thing domain-wise (see
# db:sexAtBirth in ontology/databridge-core.ttl).
# A slider is only active if its encoding data is present; otherwise it is
# shown disabled (title suffix "(no data)"), so the set visually matches
# the original. Only the active sliders (with an E array) drive the morph
# engine — in exactly their order (the CustomJS expects E in slider order).
# morphology/site_biopsy are NOT sliders in Oviedo (hover only) and are
# missing here.

# Basis-Views: im .h5ad-Pfad echte tSNE aus obsm, sonst synthetisch (Fallback).
# EN: Base views: on the .h5ad path, real tSNE from obsm, otherwise synthetic (fallback).
if H5AD_OK:
    _g = layout(adata, "X_tsne_genes")
    _genes_E = _scale_layout(_g) if (_g is not None and _g.shape[0] == N) else None
    _m = layout(adata, "X_tsne_mirna")
    _mirna_E = _scale_layout(_m) if (_m is not None and _m.shape[0] == N) else None
else:
    _genes_E = rng.normal(0.0, 2.5, size=(N, 2))
    _mirna_E = rng.normal(0.0, 2.5, size=(N, 2))


def _missing(v: object) -> bool:
    return v is None or str(v).strip() in ("", "--")


def _circ(field_key: str):
    """Kreis-Encoding einer klinischen obs-Spalte (None, wenn nicht encodierbar).

    English: Circular encoding of a clinical obs column (None if not encodable).
    """
    vals = fields[field_key]
    return CIRCLE_SCALE * circular_encoding(vals) if is_encodable(vals) else None


def _ordinal_codes(values) -> list:
    """Kategorie -> ganzzahliger Ordinal-Code (0..k-1, sortiert); fehlend -> None.
    Entspricht Oviedos ``cancer#``/``tumor_stage#`` für die linearen (ver)-Encodings.

    English: Category -> integer ordinal code (0..k-1, sorted); missing ->
    None. Corresponds to Oviedo's ``cancer#``/``tumor_stage#`` for the
    linear (ver) encodings.
    """
    classes = sorted({str(v).strip() for v in values if not _missing(v)})
    idx = {c: i for i, c in enumerate(classes)}
    return [None if _missing(v) else float(idx[str(v).strip()]) for v in values]


def _lin_ordinal(field_key: str, direction: str):
    """Lineares Encoding einer Kategorie über ihren Ordinal-Code (Oviedos ``linearEnc``
    auf ``#``-Spalten). None, wenn nicht encodierbar.

    English: Linear encoding of a category via its ordinal code (Oviedo's
    ``linearEnc`` on ``#`` columns). None if not encodable.
    """
    vals = fields[field_key]
    if not is_encodable(vals):
        return None
    return CIRCLE_SCALE * linear_encoding(_ordinal_codes(vals), dir=direction)


def _marker_enc(symbol: str, direction: str):
    """Lineares Encoding einer Gen-/miRNA-Expressionsspalte aus ``X`` (None, wenn das
    Symbol fehlt / keine ``.h5ad`` / konstant).

    English: Linear encoding of a gene/miRNA expression column from ``X``
    (None if the symbol is missing / no ``.h5ad`` / constant).
    """
    if not H5AD_OK:
        return None
    col = marker_column(adata, symbol)
    if col is None or not is_encodable(col):
        return None
    return CIRCLE_SCALE * linear_encoding(col, dir=direction)


# (Titel, Encoding-Array-oder-None, Startwert) — exakte Oviedo-Reihenfolge.
# EN: (title, encoding-array-or-None, initial value) — exact Oviedo order.
_SLIDER_SPECS = [
    ("genes", _genes_E, BASE_WEIGHT),
    ("mirna", _mirna_E, 0.0),
    ("cancer", _circ("cancer"), 0.0),
    ("type", _circ("sample_type"), 0.0),
    ("race", _circ("race"), 0.0),
    ("sex_at_birth", _circ("sex_at_birth"), 0.0),
    ("ethnicity", _circ("ethnicity"), 0.0),
    ("primary_diagnosis", _circ("primary_diagnosis"), 0.0),
    ("has_metastasis", _circ("has_metastasis"), 0.0),
    ("vital_status", _circ("vital_status"), 0.0),
    ("cancer (ver)", _lin_ordinal("cancer", "ver"), 0.0),
    ("tumor_stage (ver)", _lin_ordinal("tumor_stage", "ver"), 0.0),
    ("miRNA-210-3p (hor)", _marker_enc("miRNA-210-3p", "hor"), 0.0),
    ("CA9 (ver)", _marker_enc("CA9", "ver"), 0.0),
    ("SAA1 (hor)", _marker_enc("SAA1", "hor"), 0.0),
]

encoding_names: list[str] = []
E_arrays: list[np.ndarray] = []
_active_init: list[float] = []
morph_sliders: list[Slider] = []    # nur aktive Slider (treiben die Morph-Engine) / EN: only the active sliders (drive the morph engine)
display_sliders: list[Slider] = []  # alle 15 in Oviedo-Reihenfolge (für die Spalte) / EN: all 15 in Oviedo order (for the column)
for _title, _E, _init in _SLIDER_SPECS:
    if _E is not None:
        sl = Slider(start=0.0, end=1.0, value=_init, step=0.01, width=200, title=_title)
        morph_sliders.append(sl)
        E_arrays.append(np.asarray(_E, dtype=float))
        encoding_names.append(_title)
        _active_init.append(_init)
    else:
        sl = Slider(start=0.0, end=1.0, value=0.0, step=0.01, width=200,
                    disabled=True, title=f"{_title}  (keine Daten)")
    display_sliders.append(sl)

# Sicherheitsnetz: bliebe (Extremfall) kein aktives Encoding übrig, braucht die
# Morph-Engine trotzdem ein E. Dann „genes" synthetisch aktivieren.
# EN: Safety net: if (in an extreme case) no active encoding were left, the
# morph engine would still need an E. In that case, activate "genes" synthetically.
if not E_arrays:
    sl = display_sliders[0]
    sl.disabled = False
    sl.title = "genes"
    sl.value = BASE_WEIGHT
    morph_sliders.append(sl)
    E_arrays.append(rng.normal(0.0, 2.5, size=(N, 2)))
    encoding_names.append("genes")
    _active_init.append(BASE_WEIGHT)

genes_slider = morph_sliders[0]  # erste aktive Encoding-Variable (i. d. R. „genes") / EN: first active encoding variable (usually "genes")

# E_stack: (N, 2·k) — je Zeile [E0x,E0y, E1x,E1y, …]; Startpositionen serverseitig
# passend zu den Default-Slider-Werten (CustomJS feuert erst bei Änderung).
# EN: E_stack: (N, 2·k) — per row [E0x,E0y, E1x,E1y, …]; initial positions
# computed server-side to match the default slider values (CustomJS only
# fires on change).
E_stack = np.concatenate(E_arrays, axis=1)
_a0 = _softmax(SENS * np.asarray(_active_init))
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
    title="Cancer map", toolbar_location="above",
    tools="pan,box_select,lasso_select,tap,wheel_zoom,reset,save",
    x_range=(-9, 9), y_range=(-9, 9), output_backend="webgl",
    # Responsiv: der Plot füllt den verfügbaren Platz (Fenster minus Slider-Spalte
    # rechts, minus ②/③-Block unten) und skaliert beim Resize mit. min_height klein
    # halten, damit der ②/③-Block darunter nicht überlappt (sonst erzwingt eine große
    # min_height den Canvas und schiebt sich über den unteren Block).
    # EN: Responsive: the plot fills the available space (window minus the
    # slider column on the right, minus the ②/③ block below) and scales on
    # resize. Keep min_height small, so the ②/③ block below does not
    # overlap (otherwise a large min_height would force the canvas and push
    # over the block below).
    sizing_mode="stretch_both", min_width=480, min_height=160,
)
plot.scatter("pos_x", "pos_y", source=source, size=8, color="color",
             alpha=0.6, nonselection_alpha=0.2, line_color="#333333")

# Kohorten-Legende IN den Plot (rechts) — wie im Oviedo-Screenshot: je vorkommender
# Kohorte (in OVIEDO_COHORTS-Reihenfolge) ein Eintrag mit COHORT_COLORS. Als Träger
# der Farb-Swatches dienen leere Dummy-Glyphen (stören das Morphen nicht; das echte
# Scatter oben trägt die Farbe schon per Punkt).
# EN: Cohort legend INSIDE the plot (right) — as in the Oviedo screenshot:
# one entry per present cohort (in OVIEDO_COHORTS order) with
# COHORT_COLORS. Empty dummy glyphs carry the color swatches (they don't
# interfere with morphing; the real scatter above already carries the
# color per point).
for _c in present_cohorts:
    plot.scatter(x=[], y=[], marker="circle", size=8, fill_alpha=0.8,
                 fill_color=COHORT_COLORS[_c], line_color="#333333", legend_label=_c)
if has_uncolored:
    plot.scatter(x=[], y=[], marker="circle", size=8, fill_alpha=0.8,
                 fill_color=GRAY, line_color="#333333", legend_label="ohne Kohorte")
if plot.legend:
    _lg = plot.legend[0]
    _lg.title = "cancer"
    _lg.label_text_font_size = "8pt"
    _lg.spacing = 0
    _lg.padding = 3
    _lg.margin = 4
    _lg.glyph_height = 13
    _lg.glyph_width = 13
    _lg.label_height = 13
    plot.add_layout(_lg, "right")   # Legende rechts aus dem Plot legen / EN: place the legend on the right, outside the plot

# Hover = volle Oviedo-MP-Feldliste in exakter Reihenfolge (fehlend -> "--").
# EN: Hover = full Oviedo MP field list in exact order (missing -> "--").
_hover_fields = [
    ("Sample", "@tumor"), ("cancer", "@cancer"), ("type", "@sample_type"),
    ("race", "@race"), ("sex_at_birth", "@sex_at_birth"), ("ethnicity", "@ethnicity"),
    ("tumor_stage", "@tumor_stage"), ("morphology", "@morphology"),
    ("site_of_resection_or_biopsy", "@site_biopsy"),
    ("primary_diagnosis", "@primary_diagnosis"),
    ("has_metastasis", "@has_metastasis"), ("vital_status", "@vital_status"),
]
_tt = "".join(f"<b>{lbl}:</b> {ref}<br>" for lbl, ref in _hover_fields)

# Aufgabe 12 — bei überdeckten Punkten nur das OBERSTE Sample im Hover zeigen.
# Bokehs HoverTool rendert je getroffenem Punkt einen Tooltip-Block; liegen mehrere
# Proben auf (fast) derselben Encoding-Position (typisch bei aktivem kategorialem
# Slider, wo alle Proben einer Klasse auf denselben Kreispunkt fallen), stapeln sie
# sich. Oviedos Trick (ein <style>-Block IM Tooltip-HTML) greift in Bokeh 3.10 NICHT:
# Bokeh entfernt <style> aus dem Tooltip-String, und der Tooltip lebt in einem eigenen
# Shadow-DOM (``div.bk-Tooltip`` direkt am <body>), das Dokument-/Plot-CSS nicht
# erreicht. Deshalb injiziert ein kleiner MutationObserver (einmalig beim Laden via
# DocumentReady installiert) das passende CSS in den Shadow-Root jedes Tooltips,
# sobald er entsteht. DOM-Struktur/-Selektor live an Bokeh 3.10 verifiziert:
# ``.bk-tooltip-content > div (Wrapper) > div (je Treffer)`` — alle außer dem ersten
# ausblenden. Einzelne Punkte zeigen weiter alle Felder.
#
# EN: Task 12 — for overlapping points, show only the TOPMOST sample in the
# hover. Bokeh's HoverTool renders one tooltip block per hit point; if
# multiple samples sit at (almost) the same encoding position (typical with
# an active categorical slider, where all samples of a class fall on the
# same circle point), they stack up. Oviedo's trick (a <style> block INSIDE
# the tooltip HTML) does NOT work in Bokeh 3.10: Bokeh strips <style> out
# of the tooltip string, and the tooltip lives in its own shadow DOM
# (``div.bk-Tooltip`` directly on <body>), which document/plot CSS cannot
# reach. That's why a small MutationObserver (installed once on load via
# DocumentReady) injects the matching CSS into every tooltip's shadow root
# as soon as it is created. DOM structure/selector verified live against
# Bokeh 3.10: ``.bk-tooltip-content > div (wrapper) > div (per hit)`` —
# hide all but the first. Individual points still show all fields.
_only_first_tooltip = CustomJS(code=r"""
  if (window.__mp_only_first_tooltip) return;
  window.__mp_only_first_tooltip = true;
  const CSS = '.bk-tooltip-content > div > div:not(:first-child){display:none;}';
  const styleTip = (host) => {
    const sr = host && host.shadowRoot;
    if (!sr || sr.querySelector('style.__mp_only_first')) return;
    const st = document.createElement('style');
    st.className = '__mp_only_first';
    st.textContent = CSS;
    sr.appendChild(st);
  };
  document.querySelectorAll('.bk-Tooltip').forEach(styleTip);
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.matches && n.matches('.bk-Tooltip')) styleTip(n);
        if (n.querySelectorAll) n.querySelectorAll('.bk-Tooltip').forEach(styleTip);
      }
    }
  });
  obs.observe(document.body, {childList: true, subtree: true});
""")
plot.add_tools(HoverTool(tooltips=_tt))
curdoc().js_on_event(DocumentReady, _only_first_tooltip)

# --------------------------------------------------------------------------
# Widgets (② Kontext + ③ Rückkanal + Status) — die Morph-Slider sind oben erzeugt.
# EN: Widgets (② context + ③ feedback channel + status) — the morph sliders
# were created above.
# --------------------------------------------------------------------------
conf = Slider(start=0.0, end=1.0, value=0.7, step=0.05, width=240, title="Konfidenz")
user_in = TextInput(title="Nutzer", value="marcel", width=240)
from_in = TextInput(title="Hypothese: von (CURIE/IRI)", value="ncit:PAAD", width=240)
to_in = TextInput(title="Hypothese: nach (CURIE/IRI)", value="ncit:PanNET", width=240)
note_in = TextInput(title="Notiz", value="Common fate: driften gemeinsam", width=240)
save_btn = Button(label="③  Selektion als Erkenntnis speichern", button_type="primary", width=240)
refresh_btn = Button(label="Erkenntnisse aktualisieren", button_type="default", width=240)

boot_div = Div(text=f"<b>Status:</b> {_boot_msg}", width=520)
data_div = Div(text=f"<b>Daten:</b> {DATA_SOURCE}", width=520)
ctx_div = Div(text="<i>Punkt(e) auswählen (Tap/Box-Select) für Kontext ②</i>", width=360)
status_div = Div(text="", width=360)
findings_div = Div(text="", width=360)


# --------------------------------------------------------------------------
# ② Anreicherung: Selektion → case_context
# EN: ② Enrichment: selection → case_context
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
        f"Projekt: {ctx.get('project_id') or '—'} · "
        f"Sex at birth: {ctx.get('sex_at_birth') or ctx.get('gender') or '—'}<br>"
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
#
# EN: Morph callback (client-side via CustomJS, for smooth interaction):
#   a = softmax(SENS · slider values);  pos[j] = Σ_i a_i · E[j][2i .. 2i+1]
# Runs in the browser, no server round-trip per slider tick.
# --------------------------------------------------------------------------
morph_cb = CustomJS(args=dict(source=source, s=morph_sliders, sens=SENS), code="""
  // Slider-Werte -> softmax-Gewichte a (Sensibilität sens)
  // EN: Slider values -> softmax weights a (sensitivity sens)
  const z = s.map(w => w.value * sens);
  const ez = z.map(v => Math.exp(v));
  const sum_ez = ez.reduce((acc, v) => acc + v, 0);
  const a = ez.map(v => v / sum_ez);

  // gewichtete Summe der Encodings E (je Zeile [E0x,E0y, E1x,E1y, …])
  // EN: weighted sum of the encodings E (per row [E0x,E0y, E1x,E1y, …])
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
# EN: ③ Feedback channel: selection + hypothesis → write_feedback
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
# Layout (Aufgabe 11): wie Oviedo — links Plot (Titel „Cancer map", Toolbar oben,
# Kohorten-Legende rechts im Plot), rechts die schlanke Slider-Spalte. Darunter
# kompakt: Status + ② Kontext + ③ Rückkanal (nicht mehr die dominante Sidebar).
#
# EN: Layout (task 11): like Oviedo — plot on the left (title "Cancer map",
# toolbar on top, cohort legend inside the plot on the right), the slim
# slider column on the right. Below, compact: status + ② context + ③
# feedback channel (no longer the dominant sidebar).
# --------------------------------------------------------------------------
# Responsives Layout: der Plot füllt das Fenster (minus Slider-Spalte rechts) und
# skaliert beim Resize; die Slider-Spalte behält ihre feste Breite ganz rechts, der
# ②/③-Block bleibt in natürlicher Höhe darunter.
# Slider-Spalte: feste Breite ganz rechts; volle Zeilenhöhe, bei vielen Sliders
# intern scrollbar (statt die Zeile in die Höhe zu zwingen).
# EN: Responsive layout: the plot fills the window (minus the slider column
# on the right) and scales on resize; the slider column keeps its fixed
# width on the far right, the ②/③ block stays at natural height below it.
# Slider column: fixed width on the far right; full row height, internally
# scrollable with many sliders (instead of forcing the row's height).
slider_col = column(*display_sliders, width=230, sizing_mode="stretch_height",
                    styles={"overflow-y": "auto"})
main_row = row(plot, slider_col, sizing_mode="stretch_both")

# ②/③ + Status KOMPAKT (horizontal, Eingaben in Zeilen), damit der Plot oben
# möglichst viel Höhe behält (der Block bestimmt sonst über seine natürliche Höhe,
# wie wenig Platz dem Plot bleibt).
# EN: ②/③ + status COMPACT (horizontal, inputs in rows), so the plot above
# keeps as much height as possible (otherwise the block's natural height
# determines how little space is left for the plot).
context_panel = column(Div(text="<b>② Kontext</b>", width=320), ctx_div, width=340)
feedback_panel = column(
    Div(text="<b>③ Erkenntnis speichern</b>", width=500),
    row(user_in, from_in, to_in),
    row(note_in, conf),
    row(save_btn, refresh_btn),
    status_div, findings_div, width=740,
)
bottom = column(
    row(boot_div, data_div),
    row(context_panel, feedback_panel),
    sizing_mode="stretch_width",
)

# Zwei Roots: der Plot+Slider-Bereich (main_row, stretch_both) füllt das gesamte
# Browserfenster (X-Achse über die volle Breite, minus Slider-Spalte); der Feedback-
# Block (②/③ + Status) liegt DARUNTER und wird beim Runterscrollen sichtbar. So ist
# das Diagramm maximal groß, ohne dass der Feedback-Block Höhe wegnimmt.
# EN: Two roots: the plot+slider area (main_row, stretch_both) fills the
# entire browser window (x-axis across the full width, minus the slider
# column); the feedback block (②/③ + status) sits BELOW it and becomes
# visible on scroll-down. This keeps the chart maximally large without the
# feedback block eating into its height.
curdoc().add_root(main_row)
curdoc().add_root(bottom)
curdoc().title = "MP-lite × Wissensnetz (Prototyp)"
