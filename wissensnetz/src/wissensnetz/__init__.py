"""Wissensnetz — RDF-Store, SPARQL und Rückkanal des DataBridge-Projekts.

Öffentliche API (Aufgabe 1 + 2):

    from wissensnetz import GraphStore, Settings, initialize
"""

from __future__ import annotations

from .config import Settings
from .graphstore import GraphStore, GraphStoreError
from .init import initialize

__all__ = ["GraphStore", "GraphStoreError", "Settings", "initialize"]
__version__ = "0.1.0"
