"""Die Morphing-Projektion: Encodings und Positionen — **ohne jeden Qt-Import**.

Dasselbe Muster wie ``store_reader.py`` neben ``netz_view.py``: die Rechnung und
das Lesen der Datei stehen getrennt von der Ansicht und sind damit ohne
Bildschirm testbar.

Die Mathematik ist nicht neu erfunden. ``encodings.py`` und ``h5ad_source.py``
aus ``wissensnetz/prototype/mp_lite/`` sind bereits Qt-frei und werden hier
**wiederverwendet**. Geladen werden sie ueber ihren Dateipfad, nicht per
``import``: ``wissensnetz/prototype/`` ist kein Paket, und ``import encodings``
traefe Pythons stdlib-Paket ``encodings`` (Codecs). ``mp_lite/app.py`` macht es
aus demselben Grund genauso und begruendet es dort ausfuehrlich.

Das Morphing selbst ist eine Zeile numpy::

    pos = Σ aᵢ · E[i]     mit  a = softmax(SENS · schieberegler)

Gerechnet wird hier im GUI-Thread — bei 5000 Punkten und 15 Encodings ist das
ein Bruchteil einer Millisekunde. In MP-Lite laeuft dieselbe Gewichtung
clientseitig als CustomJS, weil dort ein Browser dazwischensteht.

**Nur lesen.** Weder ``mediator/`` noch ``wrappers/`` noch ``mp_lite/`` werden
angefasst; die beiden Hilfsmodule werden gelesen, nicht veraendert.

English: The morphing projection: encodings and positions — **without any Qt
import**.

The same pattern as ``store_reader.py`` next to ``netz_view.py``: the
computation and the file reading are kept separate from the view and are
therefore testable without a screen.

The mathematics is not reinvented. ``encodings.py`` and ``h5ad_source.py``
from ``wissensnetz/prototype/mp_lite/`` are already Qt-free and are
**reused** here. They are loaded via their file path, not via ``import``:
``wissensnetz/prototype/`` is not a package, and ``import encodings`` would
hit Python's stdlib package ``encodings`` (codecs). ``mp_lite/app.py`` does
the same for the same reason and explains it there in detail.

The morphing itself is one line of numpy::

    pos = Σ aᵢ · E[i]     with  a = softmax(SENS · slider)

Computed here in the GUI thread — with 5000 points and 15 encodings that is a
fraction of a millisecond. In MP-Lite the same weighting runs client-side as
CustomJS, because there a browser sits in between.

**Read-only.** Neither ``mediator/`` nor ``wrappers/`` nor ``mp_lite/`` are
touched; the two helper modules are read, not modified.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from wissensnetz.cohorts import cancer_code

# --- Konstanten des Originals (mp_lite/app.py) -------------------------------
# EN: Constants from the original (mp_lite/app.py)
SENS = 10.0          # Sensibilitaets-Koeffizient der softmax / EN: sensitivity coefficient of the softmax
CIRCLE_SCALE = 5.0   # Radius der Kreis-Encodings / EN: radius of the circle encodings
BASE_WEIGHT = 0.5    # Startgewicht der Basis-View (wie z[0]=0.5 im Original) / EN: initial weight of the base view (like z[0]=0.5 in the original)

# Die beiden 2D-Layouts, die der Mediator schreibt. Keine anderen Schluessel
# erfinden: so schreibt er sie, so prueft ``scripts/check_h5ad.py`` sie, so liest
# MP-Lite sie.
# EN: The two 2D layouts that the mediator writes. Do not invent other keys:
# this is how it writes them, how ``scripts/check_h5ad.py`` checks them, and
# how MP-Lite reads them.
KEY_GENES = "X_tsne_genes"
KEY_MIRNA = "X_tsne_mirna"

# Gruende, warum ein Regler nicht nutzbar ist — woertlich diese drei.
# EN: Reasons why a slider is not usable — literally these three.
GRUND_SPALTE = "Spalte fehlt in obs"
GRUND_EINWERTIG = "nur ein Wert vorhanden"
GRUND_MARKER = "Marker nicht in var"

# Was die Flaeche sagt, wenn gar kein Layout da ist (Deliverable 7). Der Explorer
# faellt hier **nicht** wie MP-Lite auf synthetische Punkte zurueck: er ist das
# Werkzeug, mit dem geforscht wird, und eine erfundene Punktwolke waere dort eine
# Luege.
# EN: What the canvas says when there is no layout at all (deliverable 7). The
# explorer does **not** fall back to synthetic points here as MP-Lite does: it
# is the tool used for research, and a fabricated point cloud would be a lie
# there.
TEXT_OHNE_LAYOUT = (
    f"Die Datei enthaelt kein 2D-Layout (obsm '{KEY_GENES}').\n"
    "Erzeuge sie mit compute_tsne=true, etwa ueber\n"
    "`start_all.ps1 -DemoGenerate` oder `scripts/fetch_pancancer_h5ad.py`."
)

# Unterhalb dieser Probenzahl liefert ``expression.compute_tsne`` im Mediator
# ``None``: tSNE braucht perplexity < n_samples, und darunter ist das nicht
# sinnvoll zu rechnen. Die Datei hat dann kein ``obsm``, **obwohl**
# ``compute_tsne=true`` gesetzt war — ohne diesen Hinweis sucht man den Fehler
# an der falschen Stelle.
# EN: Below this sample count, ``expression.compute_tsne`` in the mediator
# returns ``None``: tSNE needs perplexity < n_samples, and below that it makes
# no sense to compute. The file then has no ``obsm``, **even though**
# ``compute_tsne=true`` was set — without this hint one looks for the bug in
# the wrong place.
TSNE_MIN_PROBEN = 4


def text_ohne_layout(anzahl: int = 0) -> str:
    """Die Meldung fuer eine Datei ohne 2D-Layout.

    Bei sehr wenigen Proben steht der tatsaechliche Grund davor: dann liegt es
    nicht am fehlenden Schalter, sondern an der Probenzahl.

    English: The message for a file without a 2D layout.

    With very few samples the actual reason is prepended: then the cause is
    not the missing flag but the sample count.
    """
    if 0 < anzahl < TSNE_MIN_PROBEN:
        probe = "Probe" if anzahl == 1 else "Proben"
        return (f"Diese Datei enthaelt nur {anzahl} {probe}. Unter "
                f"{TSNE_MIN_PROBEN} Proben rechnet der Mediator keine tSNE,\n"
                "auch mit compute_tsne=true — mehr Proben abrufen.\n\n"
                + TEXT_OHNE_LAYOUT)
    return TEXT_OHNE_LAYOUT


# --- mp_lite-Hilfsmodule per Dateipfad laden (siehe Modul-Docstring) ---------
# EN: Load mp_lite helper modules by file path (see module docstring)
_MP_LITE = (Path(__file__).resolve().parent.parent
            / "wissensnetz" / "prototype" / "mp_lite")


def _lade_modul(name: str, datei: str):
    spec = importlib.util.spec_from_file_location(name, _MP_LITE / datei)
    if spec is None or spec.loader is None:      # pragma: no cover - Datei fehlt / EN: file missing
        raise ImportError(f"{datei} nicht gefunden unter {_MP_LITE}")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


_enc = _lade_modul("mp_lite_encodings", "encodings.py")
_h5 = _lade_modul("mp_lite_h5ad_source", "h5ad_source.py")

circular_encoding = _enc.circular_encoding
linear_encoding = _enc.linear_encoding
is_encodable = _enc.is_encodable

load_h5ad = _h5.load_h5ad
resolve_h5ad_path = _h5.resolve_h5ad_path
points_from_obs = _h5.points_from_obs
marker_column = _h5.marker_column
layout = _h5.layout


# --- Rechnung ----------------------------------------------------------------
# EN: Computation
def softmax(z: np.ndarray) -> np.ndarray:
    """Numerisch stabile softmax (Maximum abgezogen), Summe 1.

    English: Numerically stable softmax (maximum subtracted), sums to 1.
    """
    e = np.exp(np.asarray(z, dtype=float) - np.max(z))
    return e / e.sum()


def skaliere_layout(arr: np.ndarray, ziel: float = CIRCLE_SCALE) -> np.ndarray:
    """tSNE-Layout zentrieren und auf ``max |Koordinate| ≈ ziel`` skalieren.

    Kopiert aus ``mp_lite/app.py::_scale_layout`` — Konstanten und Verhalten
    identisch. Kopiert, weil ``app.py`` Bokeh im Modulkopf importiert und
    deshalb nicht importierbar ist; der saubere Platz waere
    ``wissensnetz/src/wissensnetz/``, das Verschieben beruehrt aber ``app.py``
    und ist eine eigene Entscheidung.

    Ohne diese Skalierung springt das Bild beim Morphen zwischen tSNE und
    Kreis-Encoding, weil die Wertebereiche auseinanderliegen.

    English: Center a tSNE layout and scale it to
    ``max |coordinate| ≈ target``.

    Copied from ``mp_lite/app.py::_scale_layout`` — constants and behavior
    identical. Copied because ``app.py`` imports Bokeh at module level and is
    therefore not importable; the clean location would be
    ``wissensnetz/src/wissensnetz/``, but moving it touches ``app.py`` and is
    a separate decision.

    Without this scaling the image jumps when morphing between tSNE and
    circle encoding, because the value ranges differ.
    """
    arr = np.asarray(arr, dtype=float)
    if arr.size == 0:
        return arr
    zentriert = arr - arr.mean(axis=0)
    spitze = float(np.max(np.abs(zentriert)))
    return zentriert if spitze == 0.0 else zentriert / spitze * ziel


@dataclass
class Eintrag:
    """Ein Regler: Name, Startwert und das Encoding — oder der Grund, warum es
    keines gibt.

    English: A slider: name, initial value and the encoding — or the reason
    why there is none.
    """

    name: str
    start: float = 0.0
    encoding: np.ndarray | None = None
    grund: str = ""

    @property
    def nutzbar(self) -> bool:
        return self.encoding is not None


@dataclass
class Morphmodell:
    """Alles, was die Ansicht zum Zeichnen braucht — und nichts von Qt.

    English: Everything the view needs to draw — and nothing from Qt.
    """

    eintraege: list[Eintrag] = field(default_factory=list)
    punkte: list[dict] = field(default_factory=list)      # eine Zeile je Probe / EN: one row per sample
    kohorten: list[str | None] = field(default_factory=list)
    # obs-Spalten, die mindestens einen Wert tragen — Grundlage dafuer, aus einer
    # fertigen Datei wieder den Auftrag zu lesen (siehe auftrag_aus_modell).
    obs_spalten: list[str] = field(default_factory=list)
    # Der vom Mediator mitgeschriebene Auftrag aus ``uns`` (P3), falls die Datei
    # ihn fuehrt — dann ist die Auswahl **gelesen** und nicht abgeleitet.
    gemeldete_auswahl: dict[str, Any] | None = None
    dateiname: str = ""
    hat_basis: bool = False

    @property
    def anzahl(self) -> int:
        return len(self.punkte)

    @property
    def startwerte(self) -> list[float]:
        return [e.start for e in self.eintraege]

    def stapel(self) -> np.ndarray:
        """Die nutzbaren Encodings als ``(N, k, 2)`` — einmal gestapelt, damit
        jede Reglerbewegung nur noch eine Summe ist.

        English: The usable encodings as ``(N, k, 2)`` — stacked once so that
        every slider movement is just a sum.
        """
        nutzbar = [e.encoding for e in self.eintraege if e.nutzbar]
        if not nutzbar:
            return np.zeros((self.anzahl, 0, 2))
        return np.stack(nutzbar, axis=1)


def positionen(modell: Morphmodell, gewichte: list[float] | np.ndarray) -> np.ndarray:
    """Die Punktpositionen zu einer Reglerstellung: ``Σ aᵢ · E[i]``.

    ``gewichte`` steht in der Reihenfolge **aller** Eintraege; nicht nutzbare
    zaehlen nicht mit, genau wie in MP-Lite, wo nur die aktiven Regler die
    Engine treiben.

    Gerechnet wird ueber ein gestapeltes ``(N, k, 2)``-Array und ``einsum``,
    nicht ueber eine Python-Schleife je Punkt.

    English: The point positions for a slider setting: ``Σ aᵢ · E[i]``.

    ``gewichte`` is in the order of **all** entries; entries that are not
    usable do not count, exactly as in MP-Lite, where only the active sliders
    drive the engine.

    Computed via a stacked ``(N, k, 2)`` array and ``einsum``, not via a
    Python loop per point.
    """
    aktive = [w for e, w in zip(modell.eintraege, gewichte) if e.nutzbar]
    stapel = modell.stapel()
    if not aktive or stapel.shape[1] == 0:
        return np.zeros((modell.anzahl, 2))
    a = softmax(SENS * np.asarray(aktive, dtype=float))
    return np.einsum("k,nkj->nj", a, stapel)


# --- Modell aus einer .h5ad bauen -------------------------------------------
# EN: Build the model from a .h5ad
def _spalte(punkte: list[dict], name: str) -> list[Any] | None:
    """Eine ``obs``-Spalte als Liste — ``None``, wenn sie in der Datei fehlt.

    ``points_from_obs`` fuellt fehlende Spalten mit ``None`` auf; eine Spalte
    gilt deshalb als fehlend, wenn sie ueberall leer ist.

    English: An ``obs`` column as a list — ``None`` if it is missing from the
    file.

    ``points_from_obs`` fills missing columns with ``None``; a column is
    therefore considered missing if it is empty everywhere.
    """
    if not punkte or name not in punkte[0]:
        return None
    werte = [p.get(name) for p in punkte]
    return None if all(w in (None, "") for w in werte) else werte


def _kreis(punkte: list[dict], name: str, titel: str, *,
           werte: list[Any] | None = None) -> Eintrag:
    """Kreis-Encoding einer kategorialen Spalte.

    English: Circle encoding of a categorical column.
    """
    vals = werte if werte is not None else _spalte(punkte, name)
    if vals is None:
        return Eintrag(titel, grund=GRUND_SPALTE)
    if not is_encodable(vals):
        return Eintrag(titel, grund=GRUND_EINWERTIG)
    return Eintrag(titel, encoding=CIRCLE_SCALE * circular_encoding(vals))


def _ordinal(werte: list[Any]) -> list[float | None]:
    """Kategorie -> ganzzahliger Ordinal-Code (0..k-1, sortiert), fehlend ->
    ``None``. Entspricht Oviedos ``cancer#``/``tumor_stage#``.

    English: Category -> integer ordinal code (0..k-1, sorted), missing ->
    ``None``. Corresponds to Oviedo's ``cancer#``/``tumor_stage#``.
    """
    def fehlt(v: object) -> bool:
        return v is None or str(v).strip() in ("", "--")

    klassen = sorted({str(v).strip() for v in werte if not fehlt(v)})
    index = {c: i for i, c in enumerate(klassen)}
    return [None if fehlt(v) else float(index[str(v).strip()]) for v in werte]


def _linear_ordinal(punkte: list[dict], name: str, titel: str, richtung: str, *,
                    werte: list[Any] | None = None) -> Eintrag:
    """Lineares Encoding einer Kategorie ueber ihren Ordinal-Code.

    English: Linear encoding of a category via its ordinal code.
    """
    vals = werte if werte is not None else _spalte(punkte, name)
    if vals is None:
        return Eintrag(titel, grund=GRUND_SPALTE)
    if not is_encodable(vals):
        return Eintrag(titel, grund=GRUND_EINWERTIG)
    return Eintrag(titel,
                   encoding=CIRCLE_SCALE * linear_encoding(_ordinal(vals), dir=richtung))


def _marker(adata: Any, symbol: str, titel: str, richtung: str) -> Eintrag:
    """Lineares Encoding einer Expressionsspalte aus ``X``.

    English: Linear encoding of an expression column from ``X``.
    """
    spalte = marker_column(adata, symbol)
    if spalte is None:
        return Eintrag(titel, grund=GRUND_MARKER)
    if not is_encodable(spalte):
        return Eintrag(titel, grund=GRUND_EINWERTIG)
    return Eintrag(titel,
                   encoding=CIRCLE_SCALE * linear_encoding(spalte, dir=richtung))


def _basis(adata: Any, key: str, titel: str, anzahl: int, start: float) -> Eintrag:
    """Eine Basis-View aus ``obsm`` — skaliert, damit sie mit den Kreisen
    vergleichbar ist.

    English: A base view from ``obsm`` — scaled so that it is comparable to
    the circles.
    """
    arr = layout(adata, key)
    if arr is None or arr.shape[0] != anzahl:
        return Eintrag(titel, start=start, grund=f"obsm '{key}' fehlt")
    return Eintrag(titel, start=start, encoding=skaliere_layout(arr))


# Schluessel, unter dem der Mediator den Auftrag in die Datei schreibt (P3,
# umgesetzt am 26.09.). Der Wert ist ein JSON-**String**, nicht ein dict —
# h5ad speichert in ``uns`` keine verschachtelten Objekte mit gemischten Typen.
UNS_AUSWAHL = "databridge_selection"


def gemeldete_auswahl(adata: Any) -> dict[str, Any] | None:
    """Den mitgeschriebenen Auftrag aus ``uns`` lesen, falls vorhanden.

    Aeltere Dateien fuehren ihn nicht (``uns`` leer) — dann ``None``, und der
    Aufrufer leitet die Auswahl weiter aus den Daten ab. Unlesbares wird
    genauso behandelt: eine kaputte Angabe ist schlechter als keine.

    English: Read the recorded request from ``uns``, if present.
    """
    roh = getattr(adata, "uns", None)
    if not roh:
        return None
    wert = roh.get(UNS_AUSWAHL) if hasattr(roh, "get") else None
    if wert is None:
        return None
    if isinstance(wert, (bytes, bytearray)):
        wert = wert.decode("utf-8", "replace")
    if isinstance(wert, str):
        try:
            wert = json.loads(wert)
        except ValueError:
            return None
    return dict(wert) if isinstance(wert, dict) else None


def baue_encodings(adata: Any, dateiname: str = "") -> Morphmodell:
    """Aus einer geladenen ``AnnData`` das Morphmodell bauen.

    Die fuenfzehn Eintraege stehen in Oviedos fester Reihenfolge und
    Benennung, **auch wenn einzelne nicht nutzbar sind** — ein deaktivierter
    Regler bleibt sichtbar und an seinem Platz, dieselbe Regel wie bei ENA und
    GEO im Auswahlpanel: ehrliche Luecke statt unsichtbarer Grenze.

    Eine bewusste Abweichung vom Original: Oviedos ``gender`` heisst hier
    ``sex_at_birth`` — GDC hat das Feld umbenannt, und fachlich ist es nicht
    dasselbe.

    English: Build the morph model from a loaded ``AnnData``.

    The fifteen entries are in Oviedo's fixed order and naming, **even when
    individual ones are not usable** — a disabled slider stays visible and in
    its place, the same rule as for ENA and GEO in the selection panel:
    honest gap instead of an invisible boundary.

    A deliberate deviation from the original: Oviedo's ``gender`` is called
    ``sex_at_birth`` here — GDC renamed the field, and professionally it is
    not the same thing.
    """
    punkte = points_from_obs(adata) if adata is not None else []
    anzahl = len(punkte)

    # Kohorten-Code je Probe: aus project_id, ersatzweise aus der Spalte cancer.
    # EN: Cohort code per sample: from project_id, falling back to the cancer
    # column.
    kohorten = [cancer_code(p.get("project_id")) or p.get("cancer") for p in punkte]
    kohorten_werte = [k for k in kohorten]

    eintraege = [
        _basis(adata, KEY_GENES, "genes", anzahl, BASE_WEIGHT),
        _basis(adata, KEY_MIRNA, "mirna", anzahl, 0.0),
        _kreis(punkte, "cancer", "cancer", werte=kohorten_werte),
        _kreis(punkte, "sample_type", "type"),
        _kreis(punkte, "race", "race"),
        _kreis(punkte, "sex_at_birth", "sex_at_birth"),
        _kreis(punkte, "ethnicity", "ethnicity"),
        _kreis(punkte, "primary_diagnosis", "primary_diagnosis"),
        _kreis(punkte, "has_metastasis", "has_metastasis"),
        _kreis(punkte, "vital_status", "vital_status"),
        _linear_ordinal(punkte, "cancer", "cancer (ver)", "ver", werte=kohorten_werte),
        _linear_ordinal(punkte, "tumor_stage", "tumor_stage (ver)", "ver"),
        _marker(adata, "miRNA-210-3p", "miRNA-210-3p (hor)", "hor"),
        _marker(adata, "CA9", "CA9 (ver)", "ver"),
        _marker(adata, "SAA1", "SAA1 (hor)", "hor"),
    ]

    # Ohne Basis-View keine Karte (Deliverable 7). Die uebrigen Encodings
    # bleiben stehen, damit man sieht, was da waere — gezeichnet wird trotzdem
    # nichts.
    # EN: Without a base view there is no map (deliverable 7). The remaining
    # encodings stay in place so one can see what would be there — nothing is
    # drawn nonetheless.
    hat_basis = any(e.nutzbar for e in eintraege[:2])
    return Morphmodell(eintraege=eintraege, punkte=punkte, kohorten=kohorten,
                       obs_spalten=belegte_spalten(adata),
                       gemeldete_auswahl=gemeldete_auswahl(adata),
                       dateiname=dateiname, hat_basis=hat_basis)


def lade_modell(pfad: str | Path | None = None) -> tuple[Morphmodell | None, str]:
    """Eine ``.h5ad`` laden und das Modell bauen. Gibt ``(modell, fehler)``.

    Laeuft im Worker-Thread (siehe ``worker.H5adWorker``): ``pancancer.h5ad``
    ist 44 MB, im GUI-Thread friert das Fenster mehrere Sekunden ein.

    English: Load a ``.h5ad`` and build the model. Returns
    ``(model, error)``.

    Runs in the worker thread (see ``worker.H5adWorker``): ``pancancer.h5ad``
    is 44 MB; in the GUI thread the window would freeze for several seconds.
    """
    ziel = resolve_h5ad_path(pfad)
    adata = load_h5ad(ziel)
    if adata is None:
        return None, (f"{ziel.name} konnte nicht gelesen werden. "
                      "Fehlt anndata, oder ist die Datei keine gueltige .h5ad?")
    try:
        return baue_encodings(adata, dateiname=ziel.name), ""
    except Exception as fehler:      # noqa: BLE001 - jede Stoerung gleich melden / EN: report every disruption alike
        return None, f"{ziel.name} liess sich nicht auswerten: {fehler}"


# --- Hover: die Werte einer Probe --------------------------------------------
# Oviedos Hover-Felder in genau dieser Reihenfolge (``mp_lite/app.py::_FIELDS``,
# dort aus ``demo.py`` uebernommen). Eine bewusste Abweichung: Oviedos
# ``gender`` heisst hier ``sex_at_birth`` — GDC hat das Feld umbenannt, und
# fachlich ist es nicht dasselbe.
HOVER_FELDER = (
    "cancer", "sample_type", "race", "sex_at_birth", "ethnicity", "tumor_stage",
    "morphology", "site_of_resection_or_biopsy", "primary_diagnosis",
    "has_metastasis", "vital_status",
)

# Was im Hover steht, wenn ein Feld leer ist — wie im Oviedo-Tool.
FEHLT = "--"


def hover_text(zeile: dict[str, Any]) -> str:
    """Die Werte einer Probe als Hover-Text, Feld je Zeile.

    Fehlende Werte stehen als ``--`` da und werden **nicht** weggelassen: eine
    Luecke ist eine Aussage ueber die Daten, eine fehlende Zeile sieht aus wie
    ein Feld, das es nicht gibt.
    """
    def wert(feld: str) -> str:
        v = zeile.get(feld)
        return FEHLT if v is None or str(v).strip() in ("", FEHLT) else str(v)

    probe = zeile.get("tumor") or zeile.get("sample_id") or FEHLT
    zeilen = [f"Sample: {probe}"]
    zeilen += [f"{feld}: {wert(feld)}" for feld in HOVER_FELDER]
    return "\n".join(zeilen)


# --- Aus einer fertigen Datei wieder den Auftrag lesen -----------------------
# Der alte Name des Feldes: GDC hat ``gender`` in ``sex_at_birth`` umbenannt,
# aeltere .h5ad tragen noch die alte Spalte.
LEGACY_SPALTEN = {"gender": "sex_at_birth"}


def belegte_spalten(adata: Any) -> list[str]:
    """Die ``obs``-Spalten, die mindestens einen Wert tragen.

    Der Mediator legt **immer** dieselben Spalten an; nur die angefragten sind
    gefuellt. Eine belegte Spalte ist damit der einzige Hinweis darauf, welche
    Attribute im Auftrag standen — die Datei selbst fuehrt ihn nicht mit
    (``uns`` ist leer).
    """
    if adata is None:
        return []
    spalten = []
    for name in getattr(adata.obs, "columns", []):
        werte = adata.obs[name]
        try:
            gefuellt = any(
                v is not None and str(v).strip() not in ("", "nan", "None", FEHLT)
                for v in werte
            )
        except TypeError:      # pragma: no cover - exotische Spaltentypen
            gefuellt = False
        if gefuellt:
            spalten.append(str(name))
    return spalten


def _auftrag_aus_uns(auswahl: dict[str, Any], modell: Morphmodell,
                     panel_namen: list[str]) -> dict[str, Any]:
    """Den mitgeschriebenen Auftrag in die Felder des Panels uebersetzen.

    Die Reihenfolge der Attribute kommt aus dem **Panel**, nicht aus der Datei:
    der Mediator normalisiert sie, und das Panel hat eine feste Ordnung, die
    sich nicht nach der Datei richten soll. Welche Attribute drin sind, sagt
    aber die Datei — und nur sie weiss es sicher.

    English: Translate the recorded request into the panel's fields.
    """
    kohorten = [str(k) for k in (auswahl.get("cohorts") or [])]
    gelesen = {str(a) for a in (auswahl.get("attributes") or [])}
    gelesen |= {neu for alt, neu in LEGACY_SPALTEN.items() if alt in gelesen}
    quelle = auswahl.get("source")
    groesse = auswahl.get("per_cohort_size") or auswahl.get("size") or 0
    return {
        "cohorts": sorted(kohorten),
        "attributes": [name for name in panel_namen if name in gelesen],
        "sources": [str(quelle)] if quelle else [],
        "size": int(groesse) if groesse else 0,
        "proben": len(modell.punkte),
        "gelesen": True,
    }


def auftrag_aus_modell(modell: Morphmodell,
                       panel_namen: list[str]) -> dict[str, Any]:
    """Aus einer geladenen ``.h5ad`` die Auswahl holen, die zu ihr fuehrte.

    Seit dem Mediator-Stand vom 26.09. schreibt die Datei den Auftrag selbst mit
    (``uns["databridge_selection"]``, P3) — dann wird er **gelesen**, samt
    Datenquelle, und ``gelesen`` ist ``True``.

    Aeltere Dateien fuehren ihn nicht. Dann bleibt es bei einer
    **Rekonstruktion aus den Daten** (``gelesen`` ist ``False``):

    - **Kohorten** aus ``obs["project_id"]`` — verlaesslich.
    - **Attribute** aus den belegten ``obs``-Spalten. Ein Attribut, das
      angefragt wurde, aber fuer *jede* Probe leer blieb, ist dabei nicht von
      einem nie angefragten zu unterscheiden; solche Faelle fehlen in der
      Rekonstruktion.
    - **Proben** aus der groessten Fallzahl je Kohorte — der Mediator holt
      ``size`` Proben je Kohorte.

    Die **Datenquelle** steht in solchen Dateien nicht und bleibt unangetastet.
    """
    if modell.gemeldete_auswahl:
        return _auftrag_aus_uns(modell.gemeldete_auswahl, modell, panel_namen)

    kohorten: list[str] = []
    je_kohorte: dict[str, int] = {}
    for punkt in modell.punkte:
        projekt = punkt.get("project_id")
        if not projekt:
            continue
        projekt = str(projekt)
        if projekt not in je_kohorte:
            kohorten.append(projekt)
        je_kohorte[projekt] = je_kohorte.get(projekt, 0) + 1

    belegt = set(modell.obs_spalten)
    belegt |= {neu for alt, neu in LEGACY_SPALTEN.items() if alt in belegt}
    attribute = [name for name in panel_namen if name in belegt]

    return {
        "cohorts": sorted(kohorten),
        "attributes": attribute,
        "sources": [],
        "size": max(je_kohorte.values(), default=0),
        "proben": len(modell.punkte),
        "gelesen": False,
    }
