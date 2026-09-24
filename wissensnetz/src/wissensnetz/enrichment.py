"""SPARQL-Anreicherung (Aufgabe 3): reine **Lese**-Funktionen über den Store.

Alle Funktionen nehmen einen :class:`~wissensnetz.graphstore.GraphStore` als
erstes Argument und geben strukturierte Python-Daten zurück (Listen/Dicts),
damit sie später auch der Mediator oder eine API konsumieren kann
(Abhängigkeitsrichtung Mediator→Wissensnetz). Es wird **nicht** geschrieben.

Robustheit gegen einen persistenten Store: Abfragen binden konkrete IRIs bzw.
`submitterId` oder grenzen auf ein Projekt ein — keine ungebundenen
`SELECT * WHERE { ?s ?p ?o }`.

Daten-Realität (siehe TASKS): Die Alignment-Tabelle ist derzeit leer, daher ist
`aligned_concept` (NCIt-Link via `db:primaryDiagnosis`) ein **optionales** Feld,
das aktuell leer bleibt. Die Klassenhierarchie ist generisch über
`rdfs:subClassOf*` umgesetzt und funktioniert für beliebige Klassen, sobald eine
Hierarchie (z. B. geladenes NCIt) im Store liegt.

English: SPARQL enrichment (task 3): pure **read** functions over the store.

All functions take a :class:`~wissensnetz.graphstore.GraphStore` as their
first argument and return structured Python data (lists/dicts), so the
mediator or an API can later consume them too (dependency direction
mediator→wissensnetz). **No** writing is done.

Robustness against a persistent store: queries bind concrete IRIs or
`submitterId` or scope to a project — no unbound `SELECT * WHERE { ?s ?p
?o }`.

Data reality (see TASKS): the alignment table is currently empty, so
`aligned_concept` (NCIt link via `db:primaryDiagnosis`) is an **optional**
field that currently stays empty. The class hierarchy is implemented
generically via `rdfs:subClassOf*` and works for arbitrary classes once a
hierarchy (e.g. loaded NCIt) is present in the store.
"""

from __future__ import annotations

from typing import Any

from .config import INSTANCE, PREFIXES
from .graphstore import GraphStore
from .selection import graph_iri_for_selection


# --------------------------------------------------------------------------
# Referenz-Auflösung (CURIE / volle IRI / Bezeichner)
# EN: Reference resolution (CURIE / full IRI / identifier)
# --------------------------------------------------------------------------
# Präfixe, die in PREFIXES deklariert sind — nur diese gelten als CURIE-Präfix,
# alles andere mit Schema (http:, https:, urn:, …) ist eine volle IRI.
# EN: Prefixes declared in PREFIXES — only these count as a CURIE prefix,
# everything else with a scheme (http:, https:, urn:, …) is a full IRI.
_KNOWN_PREFIXES = frozenset({"db", "ncit", "prov", "oa", "owl", "rdf", "rdfs", "xsd"})


def _scheme(ref: str) -> str:
    return ref.split(":", 1)[0] if ":" in ref else ""


def _is_iri(ref: str) -> bool:
    """True, wenn ``ref`` eine (volle) IRI ist — nicht eine CURIE oder ein
    schlichter Bezeichner (z. B. ``submitterId``).

    English: True if ``ref`` is a (full) IRI — not a CURIE or a plain
    identifier (e.g. ``submitterId``).
    """
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return True
    scheme = _scheme(r)
    return bool(scheme) and scheme not in _KNOWN_PREFIXES


def _term(ref: str) -> str:
    """SPARQL-Term für eine Klassen-/Instanz-Referenz.

    Akzeptiert eine volle IRI (`http://…`, `urn:…` oder `<…>`) oder eine CURIE
    mit bekanntem Präfix (`db:Case`). CURIEs werden unverändert übernommen — die
    Standard-`PREFIXES` lösen sie in der Abfrage auf; volle IRIs werden in
    spitze Klammern gesetzt.

    English: SPARQL term for a class/instance reference.

    Accepts a full IRI (`http://…`, `urn:…` or `<…>`) or a CURIE with a
    known prefix (`db:Case`). CURIEs are passed through unchanged — the
    standard `PREFIXES` resolve them in the query; full IRIs are wrapped in
    angle brackets.
    """
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return r
    if _scheme(r) in _KNOWN_PREFIXES:
        return r  # CURIE, z. B. db:Case / EN: CURIE, e.g. db:Case
    if ":" in r:
        return f"<{r}>"  # volle IRI (http:, https:, urn:, …) / EN: full IRI (http:, https:, urn:, …)
    return r  # schlichter Bezeichner (für Klassen unüblich) / EN: plain identifier (unusual for classes)


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# --------------------------------------------------------------------------
# (a) Klassen-/Krankheitshierarchie via rdfs:subClassOf*
# EN: (a) Class/disease hierarchy via rdfs:subClassOf*
# --------------------------------------------------------------------------
# rdfs:subClassOf* ist transitiv-reflexiv. Damit sowohl die TBox (Default-Graph)
# als auch isoliert geladene Hierarchien (Named Graphs, z. B. in Tests oder ein
# separat importiertes NCIt) gefunden werden, wird über Default- UND Named-Graph
# vereinigt — TDB2 bezieht Named Graphs sonst nicht in Default-Abfragen ein.
# EN: rdfs:subClassOf* is transitive-reflexive. So both the TBox (default
# graph) and isolated loaded hierarchies (named graphs, e.g. in tests or a
# separately imported NCIt) are found, the default AND named graph are
# unioned — TDB2 otherwise does not include named graphs in default queries.
def _hierarchy(store: GraphStore, term: str, *, up: bool, include_self: bool) -> list[str]:
    var = "?super" if up else "?sub"
    if up:
        pattern = f"{term} rdfs:subClassOf* {var} ."
    else:
        pattern = f"{var} rdfs:subClassOf* {term} ."
    # Nur benannte Klassen (IRIs): anonyme owl:Restriction-Blank-Nodes aus der
    # TBox (z. B. minCardinality-Restriktion an db:Diagnosis) gehören nicht in
    # eine Klassenhierarchie.
    # EN: Only named classes (IRIs): anonymous owl:Restriction blank nodes
    # from the TBox (e.g. a minCardinality restriction on db:Diagnosis) do
    # not belong in a class hierarchy.
    filters = [f"  FILTER(isIRI({var}))\n"]
    if not include_self:
        filters.append(f"  FILTER({var} != {term})\n")
    sparql = (
        PREFIXES
        + f"SELECT DISTINCT {var} WHERE {{\n"
        f"  {{ {pattern} }}\n"
        f"  UNION\n"
        f"  {{ GRAPH ?g {{ {pattern} }} }}\n"
        f"{''.join(filters)}"
        f"}} ORDER BY {var}"
    )
    key = var[1:]  # ohne '?' / EN: without '?'
    return [r[key] for r in store.query(sparql) if r.get(key)]


def subclasses(store: GraphStore, class_ref: str, *, include_self: bool = True) -> list[str]:
    """Alle Unterklassen von ``class_ref`` (transitiv, via ``rdfs:subClassOf*``).

    ``class_ref`` ist eine CURIE (``db:Case``) oder volle IRI. Mit
    ``include_self=False`` wird die Klasse selbst ausgeschlossen.

    English: All subclasses of ``class_ref`` (transitive, via
    ``rdfs:subClassOf*``).

    ``class_ref`` is a CURIE (``db:Case``) or full IRI. With
    ``include_self=False`` the class itself is excluded.
    """
    return _hierarchy(store, _term(class_ref), up=False, include_self=include_self)


def superclasses(store: GraphStore, class_ref: str, *, include_self: bool = True) -> list[str]:
    """Alle Oberklassen von ``class_ref`` (transitiv, via ``rdfs:subClassOf*``).

    English: All superclasses of ``class_ref`` (transitive, via ``rdfs:subClassOf*``).
    """
    return _hierarchy(store, _term(class_ref), up=True, include_self=include_self)


# --------------------------------------------------------------------------
# (b) Fall-/Diagnose-Kontext
# EN: (b) Case/diagnosis context
# --------------------------------------------------------------------------
def case_context(store: GraphStore, case_ref: str) -> dict[str, Any]:
    """Kontext zu einem Fall. ``case_ref`` = Case-IRI **oder** ``submitterId``.

    Liefert ``{}``, wenn kein Case gefunden wird, sonst ein Dict mit
    ``case_iri``, ``submitter_id``, ``project_id``, ``sex_at_birth``, ``race``,
    ``ethnicity``, ``vital_status`` (Top-Ebene, aus dem Demographic) und
    ``diagnoses`` (Liste von ``{iri, label, age_at_diagnosis, aligned_concept,
    tumor_stage, morphology, site_of_resection_or_biopsy, has_metastasis}``).

    Alle Felder sind **tolerant**: fehlt ein Wert im Graphen, steht ``None``
    (keine Exception). ``aligned_concept`` bleibt ``None``, solange kein
    NCIt-Alignment vorliegt; die neuen Demographic-/Diagnose-Felder (race,
    ethnicity, vital_status, tumor_stage, morphology,
    site_of_resection_or_biopsy, has_metastasis) bleiben ``None``, bis
    Mediator/Wrapper sie liefern (siehe HANDOFF.md). ``sample_type`` (erster
    Sample-Wert, analog ``sex_at_birth``) bleibt ``None``, bis der Mediator
    ``samples.sample_type`` auf ``db:sampleType`` mappt (HANDOFF.md, Teil 2).

    English: Context of a case. ``case_ref`` = case IRI **or**
    ``submitterId``.

    Returns ``{}`` if no case is found, otherwise a dict with ``case_iri``,
    ``submitter_id``, ``project_id``, ``sex_at_birth``, ``race``,
    ``ethnicity``, ``vital_status`` (top level, from the demographic) and
    ``diagnoses`` (list of ``{iri, label, age_at_diagnosis, aligned_concept,
    tumor_stage, morphology, site_of_resection_or_biopsy, has_metastasis}``).

    All fields are **tolerant**: if a value is missing in the graph, it is
    ``None`` (no exception). ``aligned_concept`` stays ``None`` as long as
    there is no NCIt alignment; the new demographic/diagnosis fields (race,
    ethnicity, vital_status, tumor_stage, morphology,
    site_of_resection_or_biopsy, has_metastasis) stay ``None`` until the
    mediator/wrapper deliver them (see HANDOFF.md). ``sample_type`` (first
    sample value, analogous to ``sex_at_birth``) stays ``None`` until the
    mediator maps ``samples.sample_type`` onto ``db:sampleType``
    (HANDOFF.md, part 2).
    """
    ref = case_ref.strip()
    if _is_iri(ref):
        binder = f"VALUES ?c {{ {_term(ref)} }}"
    else:
        binder = f'?c db:submitterId "{_escape_literal(ref)}" .'

    sparql = PREFIXES + f"""
    SELECT ?c ?sid ?projectId ?sexAtBirth ?race ?ethnicity ?vitalStatus ?sampleType
           ?diag ?label ?age ?aligned
           ?tumorStage ?morphology ?siteBiopsy ?metastasis WHERE {{
      {binder}
      ?c a db:Case .
      OPTIONAL {{ ?c db:submitterId ?sid }}
      OPTIONAL {{ ?c db:belongsToProject ?proj . ?proj db:projectId ?projectId }}
      OPTIONAL {{
        ?c db:hasDemographic ?demo .
        OPTIONAL {{ ?demo db:sexAtBirth ?sexNeu }}
        OPTIONAL {{ ?demo db:gender ?sexAlt }}
        BIND(COALESCE(?sexNeu, ?sexAlt) AS ?sexAtBirth)
        OPTIONAL {{ ?demo db:race ?race }}
        OPTIONAL {{ ?demo db:ethnicity ?ethnicity }}
        OPTIONAL {{ ?demo db:vitalStatus ?vitalStatus }}
      }}
      OPTIONAL {{ ?c db:hasSample ?sample . ?sample db:sampleType ?sampleType }}
      OPTIONAL {{
        ?c db:hasDiagnosis ?diag .
        OPTIONAL {{ ?diag db:primaryDiagnosisLabel ?label }}
        OPTIONAL {{ ?diag db:ageAtDiagnosis ?age }}
        OPTIONAL {{ ?diag db:primaryDiagnosis ?aligned }}
        OPTIONAL {{ ?diag db:tumorStage ?tumorStage }}
        OPTIONAL {{ ?diag db:morphology ?morphology }}
        OPTIONAL {{ ?diag db:siteOfResectionOrBiopsy ?siteBiopsy }}
        OPTIONAL {{ ?diag db:metastasisAtDiagnosis ?metastasis }}
      }}
    }}
    """
    rows = store.query(sparql)
    if not rows:
        return {}

    result: dict[str, Any] = {
        "case_iri": rows[0].get("c"),
        "submitter_id": _first(rows, "sid"),
        "project_id": _first(rows, "projectId"),
        "sex_at_birth": _first(rows, "sexAtBirth"),
        "race": _first(rows, "race"),
        "ethnicity": _first(rows, "ethnicity"),
        "vital_status": _first(rows, "vitalStatus"),
        "sample_type": _first(rows, "sampleType"),
        "diagnoses": [],
    }
    seen: set[str] = set()
    for r in rows:
        diag = r.get("diag")
        if not diag or diag in seen:
            continue
        seen.add(diag)
        result["diagnoses"].append(_diagnosis_row(r, iri=diag))
    return result


# --------------------------------------------------------------------------
# Gemeinsame Bausteine für die Sammel-Leseabfragen (all_cases /
# cases_for_selection): beide liefern dieselbe Form, sie unterscheiden sich nur
# darin, WELCHE Fälle sie einsammeln — deshalb ein OPTIONAL-Block und eine
# Verdichtungsfunktion für beide.
#
# EN: Shared building blocks for the bulk read queries (all_cases /
# cases_for_selection): both return the same shape, they only differ in
# WHICH cases they collect — hence one OPTIONAL block and one folding
# function for both.
# --------------------------------------------------------------------------
_CASE_VARS = (
    "?c ?sid ?projectId ?sexAtBirth ?race ?ethnicity ?vitalStatus ?sampleType "
    "?label ?tumorStage ?morphology ?siteBiopsy ?metastasis"
)

# ?sampleBlock wird je Aufrufer eingesetzt: alle Proben des Falls (all_cases)
# bzw. nur die Proben, die zur Auswahl gehören (cases_for_selection).
# EN: ?sampleBlock is inserted per caller: all samples of the case
# (all_cases) or only the samples that belong to the selection
# (cases_for_selection).
_CASE_OPTIONALS = """      OPTIONAL {{ ?c db:submitterId ?sid }}
      OPTIONAL {{ ?c db:belongsToProject ?proj . ?proj db:projectId ?projectId }}
      OPTIONAL {{
        ?c db:hasDemographic ?demo .
        OPTIONAL {{ ?demo db:sexAtBirth ?sexNeu }}
        OPTIONAL {{ ?demo db:gender ?sexAlt }}
        BIND(COALESCE(?sexNeu, ?sexAlt) AS ?sexAtBirth)
        OPTIONAL {{ ?demo db:race ?race }}
        OPTIONAL {{ ?demo db:ethnicity ?ethnicity }}
        OPTIONAL {{ ?demo db:vitalStatus ?vitalStatus }}
      }}
      {sample_block}
      OPTIONAL {{
        ?c db:hasDiagnosis ?diag .
        OPTIONAL {{ ?diag db:primaryDiagnosisLabel ?label }}
        OPTIONAL {{ ?diag db:tumorStage ?tumorStage }}
        OPTIONAL {{ ?diag db:morphology ?morphology }}
        OPTIONAL {{ ?diag db:siteOfResectionOrBiopsy ?siteBiopsy }}
        OPTIONAL {{ ?diag db:metastasisAtDiagnosis ?metastasis }}
      }}"""

# Ausgabe-Schlüssel -> SPARQL-Variable. Diese Form erwartet ``build_obs`` im
# Mediator (``_OBS_CASE_FIELDS``) — sie ist Teil der Naht und ändert sich nicht
# einseitig.
#
# ``sex_at_birth``: GDC hat das Feld von ``gender`` umbenannt, die TBox führt
# es als ``db:sexAtBirth`` (``db:gender`` bleibt deprecated lesbar).
#
# EN: Output key -> SPARQL variable. `build_obs` in the mediator
# (`_OBS_CASE_FIELDS`) expects this shape — it is part of the seam and does
# not change unilaterally.
#
# ``sex_at_birth``: GDC renamed the field from ``gender``, the TBox carries
# it as ``db:sexAtBirth`` (``db:gender`` remains readable as deprecated).
_CASE_KEYS = (
    ("submitter_id", "sid"), ("project_id", "projectId"),
    ("sex_at_birth", "sexAtBirth"),
    ("race", "race"), ("ethnicity", "ethnicity"), ("vital_status", "vitalStatus"),
    ("sample_type", "sampleType"),
    ("primary_diagnosis", "label"), ("tumor_stage", "tumorStage"),
    ("morphology", "morphology"), ("site_of_resection_or_biopsy", "siteBiopsy"),
    ("has_metastasis", "metastasis"),
)


def _fold_case_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mehrere Zeilen je Fall (Diagnosen/Proben) auf einen Eintrag verdichten.

    Erste Diagnose / erster Nicht-Null-Wert gewinnt; die Reihenfolge der Fälle
    aus der Abfrage bleibt erhalten.

    English: Folds multiple rows per case (diagnoses/samples) into one
    entry.

    First diagnosis / first non-null value wins; the order of cases from the
    query is preserved.
    """
    by_case: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rows:
        c = r.get("c")
        if not c:
            continue
        if c not in by_case:
            entry: dict[str, Any] = {"case_iri": c}
            for out_key, var in _CASE_KEYS:
                entry[out_key] = r.get(var)
            by_case[c] = entry
            order.append(c)
        else:
            entry = by_case[c]
            for out_key, var in _CASE_KEYS:
                if entry[out_key] is None and r.get(var) is not None:
                    entry[out_key] = r.get(var)
    return [by_case[c] for c in order]


def all_cases(store: GraphStore, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Sammel-Leseabfrage über **alle** Fälle im Store (für MP-lite Aufgabe 7).

    Genau **eine** SPARQL-SELECT über ``?c a db:Case`` (nicht pro Fall ein
    :func:`case_context`), die je Fall ein Dict liefert mit ``case_iri``,
    ``submitter_id``, ``project_id`` (über ``db:belongsToProject``/``db:projectId``),
    ``sex_at_birth``, ``race``, ``ethnicity``, ``vital_status``, ``sample_type`` (erster
    Sample-Wert) sowie — aus der ersten Diagnose — ``primary_diagnosis`` (Label),
    ``tumor_stage``, ``morphology``, ``site_of_resection_or_biopsy`` und
    ``has_metastasis``.

    Fehlende Werte sind ``None`` (tolerant, wie die übrigen enrichment-Funktionen);
    ``sample_type`` bleibt ``None``, bis der Mediator ``samples.sample_type`` auf
    ``db:sampleType`` mappt (siehe HANDOFF.md, Teil 2). Mit ``limit`` wird die
    **Fall**-Anzahl begrenzt (deterministisch via ``ORDER BY ?c``), ohne dass
    mehrere Diagnose-Zeilen einen Fall zerschneiden.

    English: Bulk read query over **all** cases in the store (for MP-lite
    task 7).

    Exactly **one** SPARQL SELECT over ``?c a db:Case`` (not one
    :func:`case_context` per case), returning a dict per case with
    ``case_iri``, ``submitter_id``, ``project_id`` (via
    ``db:belongsToProject``/``db:projectId``), ``sex_at_birth``, ``race``,
    ``ethnicity``, ``vital_status``, ``sample_type`` (first sample value) as
    well as — from the first diagnosis — ``primary_diagnosis`` (label),
    ``tumor_stage``, ``morphology``, ``site_of_resection_or_biopsy`` and
    ``has_metastasis``.

    Missing values are ``None`` (tolerant, like the other enrichment
    functions); ``sample_type`` stays ``None`` until the mediator maps
    ``samples.sample_type`` onto ``db:sampleType`` (see HANDOFF.md, part 2).
    With ``limit`` the **case** count is capped (deterministic via ``ORDER
    BY ?c``), without multiple diagnosis rows splitting a case.
    """
    inner = "{ SELECT ?c WHERE { ?c a db:Case } ORDER BY ?c"
    if limit is not None:
        inner += f" LIMIT {int(limit)}"
    inner += " }"

    sample_block = (
        "OPTIONAL { ?c db:hasSample ?sample . ?sample db:sampleType ?sampleType }"
    )
    sparql = PREFIXES + f"""
    SELECT {_CASE_VARS} WHERE {{
      {inner}
      ?c a db:Case .
{_CASE_OPTIONALS.format(sample_block=sample_block)}
    }} ORDER BY ?c
    """
    return _fold_case_rows(store.query(sparql))


def cases_for_selection(store: GraphStore, selection_id: str) -> list[dict[str, Any]]:
    """Wie :func:`all_cases`, aber **begrenzt auf die Mitglieder einer Auswahl**.

    Gegenstück zu ``all_cases(store)`` in ``_build_anndata_from_hits`` und der
    Grund, warum die ``obs`` nicht mehr den ganzen Store sieht (Aufgabe 13,
    ``HANDOFF_pablo_store_waechst.md``, P3). Die Rückgabeform ist identisch,
    ``build_obs`` bleibt also unverändert.

    Die Abfrage joint über die Grenze zwischen den beiden Ebenen hinweg: das
    **Manifest** liegt im Named Graph der Auswahl, der **Wissensbestand** im
    Default-Graph. ``sample_type`` wird dabei nur aus Proben gelesen, die auch
    Mitglied der Auswahl sind — nicht aus allen Proben des Falls.

    Tolerant wie :func:`case_context`: fehlt ein Wert, steht ``None``. Fälle,
    die das Manifest nennt, die aber (noch) nicht im Wissensbestand liegen,
    erscheinen nicht — das Manifest allein macht keinen Fall.

    English: Like :func:`all_cases`, but **limited to the members of a
    selection**.

    Counterpart to ``all_cases(store)`` in ``_build_anndata_from_hits`` and
    the reason why ``obs`` no longer sees the whole store (task 13,
    ``HANDOFF_pablo_store_waechst.md``, P3). The return shape is identical,
    so ``build_obs`` stays unchanged.

    The query joins across the boundary between the two levels: the
    **manifest** lives in the selection's named graph, the **knowledge
    base** in the default graph. ``sample_type`` is only read from samples
    that are also members of the selection — not from all samples of the
    case.

    Tolerant like :func:`case_context`: if a value is missing, it is
    ``None``. Cases that the manifest names but that are not (yet) in the
    knowledge base do not appear — the manifest alone does not make a case.
    """
    graph = graph_iri_for_selection(selection_id)
    sample_block = (
        f"OPTIONAL {{ GRAPH <{graph}> {{ ?sel db:hasMember ?sample }}\n"
        f"        ?c db:hasSample ?sample . ?sample db:sampleType ?sampleType }}"
    )
    sparql = PREFIXES + f"""
    SELECT {_CASE_VARS} WHERE {{
      GRAPH <{graph}> {{ ?sel a db:Selection ; db:selectionCase ?c }}
      ?c a db:Case .
{_CASE_OPTIONALS.format(sample_block=sample_block)}
    }} ORDER BY ?c
    """
    return _fold_case_rows(store.query(sparql))


def diagnosis_context(store: GraphStore, diagnosis_ref: str) -> dict[str, Any]:
    """Kontext zu einer Diagnose. ``diagnosis_ref`` = Diagnose-IRI **oder** die
    Kennung im IRI (z. B. ``d-11111111`` → ``…/instance/diagnosis/d-11111111``).

    Liefert ``{}``, wenn keine Diagnose gefunden wird, sonst ein Dict mit
    ``diagnosis_iri``, ``case_iri``, ``submitter_id``, ``label``,
    ``age_at_diagnosis`` und ``aligned_concept``.

    English: Context of a diagnosis. ``diagnosis_ref`` = diagnosis IRI
    **or** the identifier within the IRI (e.g. ``d-11111111`` →
    ``…/instance/diagnosis/d-11111111``).

    Returns ``{}`` if no diagnosis is found, otherwise a dict with
    ``diagnosis_iri``, ``case_iri``, ``submitter_id``, ``label``,
    ``age_at_diagnosis`` and ``aligned_concept``.
    """
    ref = diagnosis_ref.strip()
    term = _term(ref) if _is_iri(ref) else f"<{INSTANCE}diagnosis/{ref}>"

    sparql = PREFIXES + f"""
    SELECT ?diag ?c ?sid ?label ?age ?aligned WHERE {{
      VALUES ?diag {{ {term} }}
      ?diag a db:Diagnosis .
      OPTIONAL {{ ?diag db:describesCase ?c . OPTIONAL {{ ?c db:submitterId ?sid }} }}
      OPTIONAL {{ ?diag db:primaryDiagnosisLabel ?label }}
      OPTIONAL {{ ?diag db:ageAtDiagnosis ?age }}
      OPTIONAL {{ ?diag db:primaryDiagnosis ?aligned }}
    }}
    """
    rows = store.query(sparql)
    if not rows:
        return {}
    r = rows[0]
    ctx = _diagnosis_row(r, iri=r.get("diag"))
    ctx["diagnosis_iri"] = ctx.pop("iri")
    ctx["case_iri"] = r.get("c")
    ctx["submitter_id"] = r.get("sid")
    return ctx


# --------------------------------------------------------------------------
# Hilfen
# EN: Helpers
# --------------------------------------------------------------------------
def _first(rows: list[dict[str, Any]], key: str) -> Any:
    for r in rows:
        if r.get(key) is not None:
            return r[key]
    return None


def _diagnosis_row(r: dict[str, Any], *, iri: str | None) -> dict[str, Any]:
    age = r.get("age")
    return {
        "iri": iri,
        "label": r.get("label"),
        "age_at_diagnosis": int(age) if age is not None else None,
        "aligned_concept": r.get("aligned"),
        # Neue Oviedo-MP-Felder (tolerant: None, bis Mediator/Wrapper sie liefern).
        # EN: New Oviedo-MP fields (tolerant: None until mediator/wrapper deliver them).
        "tumor_stage": r.get("tumorStage"),
        "morphology": r.get("morphology"),
        "site_of_resection_or_biopsy": r.get("siteBiopsy"),
        "has_metastasis": r.get("metastasis"),
    }
