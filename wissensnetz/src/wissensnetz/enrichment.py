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
"""

from __future__ import annotations

from typing import Any

from .config import INSTANCE, PREFIXES
from .graphstore import GraphStore


# --------------------------------------------------------------------------
# Referenz-Auflösung (CURIE / volle IRI / Bezeichner)
# --------------------------------------------------------------------------
# Präfixe, die in PREFIXES deklariert sind — nur diese gelten als CURIE-Präfix,
# alles andere mit Schema (http:, https:, urn:, …) ist eine volle IRI.
_KNOWN_PREFIXES = frozenset({"db", "ncit", "prov", "oa", "owl", "rdf", "rdfs", "xsd"})


def _scheme(ref: str) -> str:
    return ref.split(":", 1)[0] if ":" in ref else ""


def _is_iri(ref: str) -> bool:
    """True, wenn ``ref`` eine (volle) IRI ist — nicht eine CURIE oder ein
    schlichter Bezeichner (z. B. ``submitterId``)."""
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
    """
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return r
    if _scheme(r) in _KNOWN_PREFIXES:
        return r  # CURIE, z. B. db:Case
    if ":" in r:
        return f"<{r}>"  # volle IRI (http:, https:, urn:, …)
    return r  # schlichter Bezeichner (für Klassen unüblich)


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# --------------------------------------------------------------------------
# (a) Klassen-/Krankheitshierarchie via rdfs:subClassOf*
# --------------------------------------------------------------------------
# rdfs:subClassOf* ist transitiv-reflexiv. Damit sowohl die TBox (Default-Graph)
# als auch isoliert geladene Hierarchien (Named Graphs, z. B. in Tests oder ein
# separat importiertes NCIt) gefunden werden, wird über Default- UND Named-Graph
# vereinigt — TDB2 bezieht Named Graphs sonst nicht in Default-Abfragen ein.
def _hierarchy(store: GraphStore, term: str, *, up: bool, include_self: bool) -> list[str]:
    var = "?super" if up else "?sub"
    if up:
        pattern = f"{term} rdfs:subClassOf* {var} ."
    else:
        pattern = f"{var} rdfs:subClassOf* {term} ."
    # Nur benannte Klassen (IRIs): anonyme owl:Restriction-Blank-Nodes aus der
    # TBox (z. B. minCardinality-Restriktion an db:Diagnosis) gehören nicht in
    # eine Klassenhierarchie.
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
    key = var[1:]  # ohne '?'
    return [r[key] for r in store.query(sparql) if r.get(key)]


def subclasses(store: GraphStore, class_ref: str, *, include_self: bool = True) -> list[str]:
    """Alle Unterklassen von ``class_ref`` (transitiv, via ``rdfs:subClassOf*``).

    ``class_ref`` ist eine CURIE (``db:Case``) oder volle IRI. Mit
    ``include_self=False`` wird die Klasse selbst ausgeschlossen.
    """
    return _hierarchy(store, _term(class_ref), up=False, include_self=include_self)


def superclasses(store: GraphStore, class_ref: str, *, include_self: bool = True) -> list[str]:
    """Alle Oberklassen von ``class_ref`` (transitiv, via ``rdfs:subClassOf*``)."""
    return _hierarchy(store, _term(class_ref), up=True, include_self=include_self)


# --------------------------------------------------------------------------
# (b) Fall-/Diagnose-Kontext
# --------------------------------------------------------------------------
def case_context(store: GraphStore, case_ref: str) -> dict[str, Any]:
    """Kontext zu einem Fall. ``case_ref`` = Case-IRI **oder** ``submitterId``.

    Liefert ``{}``, wenn kein Case gefunden wird, sonst ein Dict mit
    ``case_iri``, ``submitter_id``, ``project_id``, ``gender`` und ``diagnoses``
    (Liste von ``{iri, label, age_at_diagnosis, aligned_concept}``; letzteres
    aktuell ``None``, solange kein NCIt-Alignment vorliegt).
    """
    ref = case_ref.strip()
    if _is_iri(ref):
        binder = f"VALUES ?c {{ {_term(ref)} }}"
    else:
        binder = f'?c db:submitterId "{_escape_literal(ref)}" .'

    sparql = PREFIXES + f"""
    SELECT ?c ?sid ?projectId ?gender ?diag ?label ?age ?aligned WHERE {{
      {binder}
      ?c a db:Case .
      OPTIONAL {{ ?c db:submitterId ?sid }}
      OPTIONAL {{ ?c db:belongsToProject ?proj . ?proj db:projectId ?projectId }}
      OPTIONAL {{ ?c db:hasDemographic ?demo . ?demo db:gender ?gender }}
      OPTIONAL {{
        ?c db:hasDiagnosis ?diag .
        OPTIONAL {{ ?diag db:primaryDiagnosisLabel ?label }}
        OPTIONAL {{ ?diag db:ageAtDiagnosis ?age }}
        OPTIONAL {{ ?diag db:primaryDiagnosis ?aligned }}
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
        "gender": _first(rows, "gender"),
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


def diagnosis_context(store: GraphStore, diagnosis_ref: str) -> dict[str, Any]:
    """Kontext zu einer Diagnose. ``diagnosis_ref`` = Diagnose-IRI **oder** die
    Kennung im IRI (z. B. ``d-11111111`` → ``…/instance/diagnosis/d-11111111``).

    Liefert ``{}``, wenn keine Diagnose gefunden wird, sonst ein Dict mit
    ``diagnosis_iri``, ``case_iri``, ``submitter_id``, ``label``,
    ``age_at_diagnosis`` und ``aligned_concept``.
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
    }
