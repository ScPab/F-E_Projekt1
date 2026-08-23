"""Rückkanal (Aufgabe 4): Experten-Erkenntnisse aus MP zurück ins Wissensnetz.

Ablauf (nach ``recherche/Rueckkanal-Konzept_MP-zu-RDF``, Abschnitt 6):
ein simuliertes MP-Selektions-Event → RDF als ``oa:Annotation``/``db:ExpertFinding``
mit PROV-O-Provenienz und **RDF-star** für die Kern-Aussage, geschrieben per
**SPARQL Update** in einen **Named Graph pro Nutzer**.

Warum SPARQL-star-Update statt rdflib-Serialisierung: rdflibs Turtle-star ist
versionsabhängig; Fuseki unterstützt SPARQL-star nativ (ADR-0002; CLAUDE.md
„RDF-star-Falle"). ``selection_to_sparql`` baut daher direkt einen
``INSERT DATA { GRAPH <g> { … } }``-String inkl. ``<< s p o >>``-Aussage.

Named Graph pro Nutzer (``http://databridge.hka/graph/user/<slug>``) hält die
Kern-TBox/ABox im Default-Graph sauber getrennt; Erkenntnisse bleiben so
isoliert, versionierbar und widerrufbar.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import INSTANCE, PREFIXES
from .graphstore import GraphStore

# Named-Graph-Schema pro Nutzer und Instanz-Basen für erzeugte Ressourcen.
GRAPH_USER_BASE = "http://databridge.hka/graph/user/"
_USER_BASE = f"{INSTANCE}user/"
_SAMPLE_BASE = f"{INSTANCE}sample/"
_ANNO_BASE = f"{INSTANCE}annotation/"

# Präfixe, die in PREFIXES deklariert sind (alles andere mit ':' ist eine IRI).
_KNOWN_PREFIXES = frozenset({"db", "ncit", "prov", "oa", "owl", "rdf", "rdfs", "xsd"})


# --------------------------------------------------------------------------
# Event-Modell
# --------------------------------------------------------------------------
@dataclass
class Hypothesis:
    """Reclassification-Hypothese: Proben gehören von ``from_`` nach ``to``."""

    from_: str  # NCIt-/DB-Konzept (CURIE oder IRI)
    to: str
    note: str | None = None
    tag: str | None = None


@dataclass
class SelectionEvent:
    """Ein (simuliertes) MP-Selektions-Event, passend zu selection_event.json."""

    user: str
    samples: list[str]
    hypothesis: Hypothesis
    view: str | None = None
    morph_param: float | None = None
    confidence: float | None = None
    timestamp: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectionEvent":
        payload = {k: v for k, v in data.items() if not k.startswith("_")}
        hyp = payload.get("hypothesis") or {}
        hypothesis = Hypothesis(
            from_=hyp.get("from") or hyp.get("from_"),
            to=hyp.get("to"),
            note=hyp.get("note"),
            tag=hyp.get("tag"),
        )
        return cls(
            user=payload["user"],
            samples=list(payload.get("samples") or []),
            hypothesis=hypothesis,
            view=payload.get("view"),
            morph_param=payload.get("morph_param"),
            confidence=payload.get("confidence"),
            timestamp=payload.get("timestamp"),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "SelectionEvent":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# IRI-/Literal-Hilfen
# --------------------------------------------------------------------------
def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-") or "unbekannt"


def _term(ref: str) -> str:
    """SPARQL-Term für ein Konzept: CURIE mit bekanntem Präfix, sonst IRI."""
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return r
    scheme = r.split(":", 1)[0] if ":" in r else ""
    if scheme in _KNOWN_PREFIXES:
        return r
    if ":" in r:
        return f"<{r}>"
    return f"<{r}>"  # blanker Bezeichner -> als (relative) IRI behandeln


def _sample_term(ref: str) -> str:
    """Term für eine Probe: volle IRI/CURIE unverändert, blanke Kennung ->
    ``…/instance/sample/<slug>``."""
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return r
    scheme = r.split(":", 1)[0] if ":" in r else ""
    if scheme in _KNOWN_PREFIXES or ":" in r:
        return _term(r)
    return f"<{_SAMPLE_BASE}{_slug(r)}>"


def graph_iri_for(user: str) -> str:
    """Named-Graph-IRI für einen Nutzer."""
    return f"{GRAPH_USER_BASE}{_slug(user)}"


def _user_iri(user: str) -> str:
    return f"<{_USER_BASE}{_slug(user)}>"


def _lit(value: str) -> str:
    """SPARQL-String-Literal (escaped, in Anführungszeichen)."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _decimal(value: float) -> str:
    # xsd:decimal-Literal ohne Exponent; ganze Werte mit .0 (nicht als int).
    return f"{value:.10g}" if value != int(value) else f"{value:.1f}"


# --------------------------------------------------------------------------
# Event -> SPARQL-Update
# --------------------------------------------------------------------------
def selection_to_sparql(event: SelectionEvent) -> str:
    """Erzeugt das ``INSERT DATA``-Update für ein Selektions-Event.

    Enthält die ``oa:Annotation``/``db:ExpertFinding`` mit PROV-O-Metadaten,
    ``oa:hasTarget`` je Probe, die ``db:hypothesis`` (Reclassification from→to)
    und je Probe eine RDF-star-Kern-Aussage
    ``<< sample db:reclassifiedAs to >> prov:wasDerivedFrom anno ; db:confidence c``.
    """
    graph = graph_iri_for(event.user)
    anno = f"<{_ANNO_BASE}anno-{uuid.uuid4().hex[:12]}>"
    ts = event.timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    to_term = _term(event.hypothesis.to)
    from_term = _term(event.hypothesis.from_)
    samples = [_sample_term(s) for s in event.samples]

    # ExpertFinding-Block
    lines = [
        f"{anno} a oa:Annotation , db:ExpertFinding ;",
        f"    prov:wasAttributedTo {_user_iri(event.user)} ;",
        f'    prov:generatedAtTime "{ts}"^^xsd:dateTime ;',
    ]
    if event.view is not None:
        lines.append(f"    db:inView {_lit(event.view)} ;")
    if event.morph_param is not None:
        lines.append(f"    db:morphParam {_decimal(float(event.morph_param))} ;")
    if event.confidence is not None:
        lines.append(f"    db:confidence {_decimal(float(event.confidence))} ;")
    if event.hypothesis.tag:
        lines.append(f"    db:tag {_lit(event.hypothesis.tag)} ;")
    for s in samples:
        lines.append(f"    oa:hasTarget {s} ;")

    hyp_parts = [f"a db:Reclassification ; db:from {from_term} ; db:to {to_term}"]
    if event.hypothesis.note:
        hyp_parts.append(f"rdfs:comment {_lit(event.hypothesis.note)}")
    lines.append(f"    db:hypothesis [ {' ; '.join(hyp_parts)} ] .")

    # RDF-star-Kern-Aussagen (Provenienz/Konfidenz direkt an der Aussage)
    conf = _decimal(float(event.confidence)) if event.confidence is not None else "1.0"
    star = [
        f"    << {s} db:reclassifiedAs {to_term} >> "
        f"prov:wasDerivedFrom {anno} ; db:confidence {conf} ."
        for s in samples
    ]

    body = "\n".join("    " + ln for ln in lines)
    star_body = "\n".join(star)
    return (
        PREFIXES
        + f"INSERT DATA {{\n  GRAPH <{graph}> {{\n{body}\n{star_body}\n  }}\n}}"
    )


# --------------------------------------------------------------------------
# Schreiben / Lesen
# --------------------------------------------------------------------------
def write_feedback(store: GraphStore, event: SelectionEvent) -> str:
    """Schreibt das Event in den Nutzer-Named-Graph. Gibt das Graph-IRI zurück."""
    store.update(selection_to_sparql(event))
    return graph_iri_for(event.user)


def list_findings(store: GraphStore, user: str | None = None) -> list[dict[str, Any]]:
    """Liest gespeicherte ExpertFindings (mit Hypothese und Zielen) wieder aus.

    Ohne ``user`` über alle Nutzer-Graphen, sonst auf dessen Graph eingegrenzt.
    """
    graph_filter = f"VALUES ?g {{ <{graph_iri_for(user)}> }}" if user else ""
    sparql = PREFIXES + f"""
    SELECT ?g ?anno ?user ?time ?view ?morph ?conf ?tag ?from ?to ?note
           (GROUP_CONCAT(DISTINCT ?target; separator=" ") AS ?targets)
    WHERE {{
      {graph_filter}
      GRAPH ?g {{
        ?anno a db:ExpertFinding .
        OPTIONAL {{ ?anno prov:wasAttributedTo ?user }}
        OPTIONAL {{ ?anno prov:generatedAtTime ?time }}
        OPTIONAL {{ ?anno db:inView ?view }}
        OPTIONAL {{ ?anno db:morphParam ?morph }}
        OPTIONAL {{ ?anno db:confidence ?conf }}
        OPTIONAL {{ ?anno db:tag ?tag }}
        OPTIONAL {{ ?anno oa:hasTarget ?target }}
        OPTIONAL {{ ?anno db:hypothesis ?h .
          OPTIONAL {{ ?h db:from ?from }}
          OPTIONAL {{ ?h db:to ?to }}
          OPTIONAL {{ ?h rdfs:comment ?note }}
        }}
      }}
    }}
    GROUP BY ?g ?anno ?user ?time ?view ?morph ?conf ?tag ?from ?to ?note
    ORDER BY ?time
    """
    findings = []
    for r in store.query(sparql):
        targets = r.get("targets") or ""
        findings.append({
            "graph": r.get("g"),
            "annotation": r.get("anno"),
            "user": r.get("user"),
            "timestamp": r.get("time"),
            "view": r.get("view"),
            "morph_param": r.get("morph"),
            "confidence": r.get("conf"),
            "tag": r.get("tag"),
            "hypothesis": {"from": r.get("from"), "to": r.get("to"), "note": r.get("note")},
            "targets": targets.split() if targets else [],
        })
    return findings


def reclassifications(store: GraphStore, user: str | None = None) -> list[dict[str, Any]]:
    """Liest die RDF-star-Kern-Aussagen (Probe → Ziel, mit Konfidenz/Provenienz)."""
    graph_filter = f"VALUES ?g {{ <{graph_iri_for(user)}> }}" if user else ""
    sparql = PREFIXES + f"""
    SELECT ?g ?sample ?target ?conf ?anno WHERE {{
      {graph_filter}
      GRAPH ?g {{
        << ?sample db:reclassifiedAs ?target >> prov:wasDerivedFrom ?anno .
        OPTIONAL {{ << ?sample db:reclassifiedAs ?target >> db:confidence ?conf }}
      }}
    }} ORDER BY ?sample
    """
    return [
        {
            "graph": r.get("g"),
            "sample": r.get("sample"),
            "reclassified_as": r.get("target"),
            "confidence": r.get("conf"),
            "annotation": r.get("anno"),
        }
        for r in store.query(sparql)
    ]
