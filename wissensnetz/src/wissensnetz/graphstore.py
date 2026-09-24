"""Graphstore-Client (Aufgabe 2): HTTP-Zugriff auf den Fuseki-``graph-db``.

Drei Kern-Operationen entlang der Aufgabenstellung:

* :meth:`GraphStore.load_turtle` — Turtle in den Store laden (Graph Store
  Protocol). Der Text wird **roh** an Fuseki gesendet, nicht durch rdflib
  geparst/re-serialisiert — so bleibt auch RDF-star-Turtle
  (``<< s p o >>``-Blöcke aus dem Mediator) erhalten, das rdflib je nach
  Version nicht parst (siehe CLAUDE.md, "RDF-star-Falle"; ADR-0002:
  natives RDF-star in Fuseki).
* :meth:`GraphStore.query` — SELECT/ASK-Abfrage, Ergebnis als Liste von
  ``{variable: wert}``-Dicts (SPARQL-JSON-Results).
* :meth:`GraphStore.update` — SPARQL Update (INSERT/DELETE), z. B. für den
  Rückkanal (Aufgabe 4).

Kommunikation ausschließlich per HTTP/SPARQL gegen den ``graph-db``-Service.

English: Graphstore client (task 2): HTTP access to the Fuseki ``graph-db``.

Three core operations following the task specification:

* :meth:`GraphStore.load_turtle` — load Turtle into the store (Graph Store
  Protocol). The text is sent to Fuseki **raw**, not parsed/re-serialized by
  rdflib — this way RDF-star Turtle (``<< s p o >>`` blocks from the
  mediator) also survives, which rdflib does not parse depending on version
  (see CLAUDE.md, "RDF-star trap"; ADR-0002: native RDF-star in Fuseki).
* :meth:`GraphStore.query` — SELECT/ASK query, result as a list of
  ``{variable: value}`` dicts (SPARQL JSON results).
* :meth:`GraphStore.update` — SPARQL update (INSERT/DELETE), e.g. for the
  feedback channel (task 4).

Communication exclusively via HTTP/SPARQL against the ``graph-db`` service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .config import Settings

# Fuseki akzeptiert Turtle-star unter dem Turtle-Media-Type.
# EN: Fuseki accepts Turtle-star under the Turtle media type.
_TURTLE = "text/turtle"
_SPARQL_JSON = "application/sparql-results+json"


class GraphStoreError(RuntimeError):
    """Fehler bei der Kommunikation mit dem Fuseki-Store.

    English: Error communicating with the Fuseki store.
    """


class GraphStore:
    """Dünner Fuseki-Client über die drei SPARQL-/GSP-HTTP-Endpunkte.

    English: Thin Fuseki client over the three SPARQL/GSP HTTP endpoints.
    """

    def __init__(self, settings: Settings | None = None, *, timeout: float = 30.0) -> None:
        self.settings = settings or Settings.from_env()
        self.timeout = timeout
        self._session = requests.Session()

    # -- Verfügbarkeit -----------------------------------------------------
    # EN: -- Availability --
    def is_reachable(self) -> bool:
        """True, wenn der Fuseki-Server antwortet (für Test-Skips/CLI).

        English: True if the Fuseki server responds (for test skips/CLI).
        """
        try:
            resp = self._session.get(self.settings.ping_url, timeout=self.timeout)
            return resp.ok
        except requests.RequestException:
            return False

    # -- Lesen -------------------------------------------------------------
    # EN: -- Reading --
    def query(self, sparql: str) -> list[dict[str, Any]]:
        """Führt eine SELECT/ASK-Abfrage aus und liefert vereinfachte Zeilen.

        SELECT -> Liste von Dicts ``{var: wert}`` (Wert = Literal-/IRI-String).
        ASK    -> ``[{"boolean": True/False}]``.

        English: Runs a SELECT/ASK query and returns simplified rows.

        SELECT -> list of dicts ``{var: value}`` (value = literal/IRI string).
        ASK    -> ``[{"boolean": True/False}]``.
        """
        resp = self._session.post(
            self.settings.query_url,
            data={"query": sparql},
            headers={"Accept": _SPARQL_JSON},
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "SPARQL-Query fehlgeschlagen")
        payload = resp.json()

        if "boolean" in payload:
            return [{"boolean": payload["boolean"]}]

        rows: list[dict[str, Any]] = []
        for binding in payload.get("results", {}).get("bindings", []):
            rows.append({var: cell.get("value") for var, cell in binding.items()})
        return rows

    def ask(self, sparql: str) -> bool:
        """Bequemer Wrapper für ASK-Abfragen.

        English: Convenient wrapper for ASK queries.
        """
        result = self.query(sparql)
        return bool(result and result[0].get("boolean"))

    # -- Schreiben ---------------------------------------------------------
    # EN: -- Writing --
    def update(self, sparql: str) -> None:
        """Führt ein SPARQL Update (INSERT/DELETE/LOAD) aus.

        Schreibzugriff ist in Fuseki durch Basic-Auth geschützt
        (shiro.ini: ``/*/update/**`` = admin), daher mit Admin-Credentials.

        English: Runs a SPARQL update (INSERT/DELETE/LOAD).

        Write access in Fuseki is protected by basic auth (shiro.ini:
        ``/*/update/**`` = admin), hence with admin credentials.
        """
        resp = self._session.post(
            self.settings.update_url,
            data={"update": sparql},
            auth=self._admin_auth(),
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "SPARQL-Update fehlgeschlagen")

    def load_turtle(self, text_or_path: str | Path, graph: str | None = None) -> None:
        """Lädt Turtle in den Store (Graph Store Protocol, POST = anhängen).

        ``text_or_path`` ist entweder Turtle-Text oder ein Pfad zu einer
        ``.ttl``-Datei. ``graph`` = IRI eines Named Graph; ohne Angabe wird
        der Default-Graph beschrieben.

        Der Turtle-Text wird unverändert übertragen (kein rdflib-Roundtrip),
        damit RDF-star erhalten bleibt.

        English: Loads Turtle into the store (Graph Store Protocol, POST =
        append).

        ``text_or_path`` is either Turtle text or a path to a ``.ttl``
        file. ``graph`` = IRI of a named graph; without one, the default
        graph is written.

        The Turtle text is transferred unchanged (no rdflib round-trip), so
        RDF-star survives.
        """
        turtle = self._resolve_turtle(text_or_path)
        params = {"graph": graph} if graph else {"default": ""}
        # GSP-Schreibzugriff ist Basic-Auth-geschützt (shiro.ini: /*/data/**).
        # EN: GSP write access is protected by basic auth (shiro.ini: /*/data/**).
        resp = self._session.post(
            self.settings.gsp_url,
            params=params,
            data=turtle.encode("utf-8"),
            headers={"Content-Type": _TURTLE},
            auth=self._admin_auth(),
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "Turtle-Load (GSP) fehlgeschlagen")

    # -- Dataset-Verwaltung (Aufgabe 1, Fallback ohne FUSEKI_DATASET_*) -----
    # EN: -- Dataset management (task 1, fallback without FUSEKI_DATASET_*) --
    def dataset_exists(self) -> bool:
        """Prüft über die Fuseki-Admin-API, ob das Dataset registriert ist.

        English: Checks via the Fuseki admin API whether the dataset is registered.
        """
        resp = self._session.get(
            self.settings.admin_datasets_url,
            auth=self._admin_auth(),
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "Dataset-Liste konnte nicht gelesen werden")
        names = {ds.get("ds.name") for ds in resp.json().get("datasets", [])}
        return f"/{self.settings.dataset}" in names or self.settings.dataset in names

    def create_dataset(self, *, db_type: str = "tdb2") -> None:
        """Legt das Dataset persistent an (idempotent: 409 wird toleriert).

        English: Creates the dataset persistently (idempotent: 409 is tolerated).
        """
        resp = self._session.post(
            self.settings.admin_datasets_url,
            params={"dbName": self.settings.dataset, "dbType": db_type},
            auth=self._admin_auth(),
            timeout=self.timeout,
        )
        if resp.status_code == 409:  # existiert bereits / EN: already exists
            return
        self._raise_for_status(resp, "Dataset konnte nicht angelegt werden")

    def ensure_dataset(self, *, db_type: str = "tdb2") -> bool:
        """Stellt sicher, dass das Dataset existiert. True = neu angelegt.

        English: Ensures the dataset exists. True = newly created.
        """
        if self.dataset_exists():
            return False
        self.create_dataset(db_type=db_type)
        return True

    # -- intern ------------------------------------------------------------
    # EN: -- internal --
    def _admin_auth(self) -> tuple[str, str]:
        return (self.settings.admin_user, self.settings.admin_password)

    @staticmethod
    def _resolve_turtle(text_or_path: str | Path) -> str:
        if isinstance(text_or_path, Path):
            return text_or_path.read_text(encoding="utf-8")
        candidate = Path(text_or_path)
        # Nur als Pfad behandeln, wenn es plausibel einer ist und existiert.
        # EN: Only treat as a path if it plausibly is one and exists.
        if len(str(text_or_path)) < 260 and candidate.suffix == ".ttl" and candidate.exists():
            return candidate.read_text(encoding="utf-8")
        return str(text_or_path)

    @staticmethod
    def _raise_for_status(resp: requests.Response, context: str) -> None:
        if not resp.ok:
            raise GraphStoreError(f"{context}: HTTP {resp.status_code} — {resp.text[:500]}")
