"""Gemeinsame pytest-Fixtures.

Alle Store-Tests laufen gegen ein **laufendes Fuseki**. Ist keins erreichbar
(z. B. in CI ohne ``docker compose up graph-db``), werden sie übersprungen
statt zu scheitern — so bleibt die Suite auch ohne Infrastruktur grün.

English: Shared pytest fixtures.

All store tests run against a **running Fuseki**. If none is reachable
(e.g. in CI without ``docker compose up graph-db``), they are skipped
instead of failing — this keeps the suite green even without infrastructure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wissensnetz import GraphStore
from wissensnetz.init import initialize

SAMPLE_TTL = Path(__file__).resolve().parents[1] / "data" / "sample" / "cases_brca_sample.ttl"


@pytest.fixture(scope="session")
def store() -> GraphStore:
    """Erreichbarer, initialisierter Store — sonst Skip der gesamten Suite.

    English: Reachable, initialized store — otherwise skip the whole suite.
    """
    gs = GraphStore()
    if not gs.is_reachable():
        pytest.skip(
            f"Fuseki nicht erreichbar unter {gs.settings.base_url} — "
            "'docker compose up graph-db' und ggf. GRAPH_DB_URL setzen."
        )
    # Dataset + TBox sicherstellen (idempotent), damit Tests unabhängig laufen.
    # EN: Ensure the dataset + TBox (idempotent), so tests run independently.
    initialize(gs)
    return gs


@pytest.fixture(scope="session")
def loaded_store(store: GraphStore) -> GraphStore:
    """Store mit geladener Beispiel-ABox (idempotent, Tripel-Mengensemantik).

    English: Store with the sample ABox loaded (idempotent, triple-set semantics).
    """
    store.load_turtle(SAMPLE_TTL)
    return store
