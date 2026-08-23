"""Wissensnetz — RDF-Store, SPARQL und Rückkanal des DataBridge-Projekts.

Öffentliche API (Aufgabe 1 + 2):

    from wissensnetz import GraphStore, Settings, initialize
"""

from __future__ import annotations

from .config import Settings
from .enrichment import case_context, diagnosis_context, subclasses, superclasses
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

__all__ = [
    "GraphStore",
    "GraphStoreError",
    "Settings",
    "initialize",
    "subclasses",
    "superclasses",
    "case_context",
    "diagnosis_context",
    "SelectionEvent",
    "Hypothesis",
    "selection_to_sparql",
    "write_feedback",
    "list_findings",
    "reclassifications",
]
__version__ = "0.1.0"
