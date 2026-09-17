"""Wissensnetz — RDF-Store, SPARQL und Rückkanal des DataBridge-Projekts.

Öffentliche API (Aufgabe 1 + 2):

    from wissensnetz import GraphStore, Settings, initialize

Naht zum Mediator (Aufgabe 13, HANDOFF_pablo_store_waechst.md):

    from wissensnetz import write_selection, cases_for_selection
"""

from __future__ import annotations

from .config import Settings
from .enrichment import (
    all_cases,
    case_context,
    cases_for_selection,
    diagnosis_context,
    subclasses,
    superclasses,
)
from .feedback import (
    Hypothesis,
    SelectionEvent,
    list_findings,
    reclassifications,
    selection_to_sparql,
    write_feedback,
)
from .graphstore import GraphStore, GraphStoreError
from .init import initialize
from .selection import (
    SELECTION_GRAPH_BASE,
    drop_selection,
    graph_iri_for_selection,
    list_selections,
    selection_manifest,
    write_selection,
)

__all__ = [
    "GraphStore",
    "GraphStoreError",
    "Settings",
    "initialize",
    "subclasses",
    "superclasses",
    "case_context",
    "diagnosis_context",
    "all_cases",
    "cases_for_selection",
    "SelectionEvent",
    "Hypothesis",
    "selection_to_sparql",
    "write_feedback",
    "list_findings",
    "reclassifications",
    "SELECTION_GRAPH_BASE",
    "graph_iri_for_selection",
    "selection_manifest",
    "write_selection",
    "drop_selection",
    "list_selections",
]
__version__ = "0.1.0"
