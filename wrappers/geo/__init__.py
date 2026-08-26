"""Wrapper-Modul für die GEO (Gene Expression Omnibus) API — NCBI E-utilities."""

from .cache import WrapperCache
from .client import GEOWrapper, build_search_term

__all__ = ["GEOWrapper", "build_search_term", "WrapperCache"]
