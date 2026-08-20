"""Semantische Schicht des Mediators: GDC-JSON -> RDF/OWL (siehe wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL)."""

from .mapping import cases_to_graph, load_alignment_table, serialize_with_provenance

__all__ = ["cases_to_graph", "load_alignment_table", "serialize_with_provenance"]
