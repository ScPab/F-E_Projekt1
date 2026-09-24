"""HTTP-Zugriff auf den Mediator — **ohne Qt**, damit ohne Fenster testbar.

Die Oberflaeche spricht ausschliesslich mit dem Mediator (ADR-0004, Punkt 3):
``POST /selection/preview`` und ``POST /selection/generate``. Nie direkt mit
einem Wrapper (ADR-0001), und in dieser Fassung auch nicht mit dem RDF-Store.

Feldnamen und Grenzen sind gegen die laufende OpenAPI des Mediators geprueft
(``http://localhost:8000/openapi.json``, Stand 2026-09-18):

* ``SelectionRequest``  required ``levels`` (minItems 1); ``size`` 1..200,
  Vorgabe 20; ``per_cohort_size`` optional; ``load`` Vorgabe true.
* ``SingleSelection``   required ``cohorts`` (minItems 1); ``source`` Vorgabe
  "gdc"; ``modality`` Vorgabe "gene_expression"; ``attributes`` Liste.

Fehler werden als :class:`Result` zurueckgegeben, nicht geworfen: der Aufrufer
ist ein Qt-Worker, und eine Exception ueber eine Thread-Grenze hinweg ist
schlechter zu behandeln als ein Rueckgabewert.

English: HTTP access to the mediator — **without Qt**, so it is testable
without a window.

The UI talks exclusively to the mediator (ADR-0004, point 3):
``POST /selection/preview`` and ``POST /selection/generate``. Never
directly to a wrapper (ADR-0001), and in this version also not to the
RDF store.

Field names and limits are checked against the mediator's running
OpenAPI (``http://localhost:8000/openapi.json``, as of 2026-09-18):

* ``SelectionRequest``  required ``levels`` (minItems 1); ``size`` 1..200,
  default 20; ``per_cohort_size`` optional; ``load`` default true.
* ``SingleSelection``   required ``cohorts`` (minItems 1); ``source``
  default "gdc"; ``modality`` default "gene_expression"; ``attributes``
  list.

Errors are returned as :class:`Result`, not raised: the caller is a Qt
worker, and an exception crossing a thread boundary is harder to handle
than a return value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "http://localhost:8000"

# Vorschau ist billig (nur Metadaten), Generieren laedt Rohdaten herunter und
# dauert Minuten — daher zwei sehr unterschiedliche Zeitlimits.
# EN: Preview is cheap (metadata only), generate downloads raw data and
# takes minutes — hence two very different timeouts.
PREVIEW_TIMEOUT = 60.0
GENERATE_TIMEOUT = 900.0

# Grenzen aus der OpenAPI (SelectionRequest.size).
# EN: Limits from the OpenAPI (SelectionRequest.size).
SIZE_MIN = 1
SIZE_MAX = 200


def default_base_url() -> str:
    """Basis-URL aus ``MEDIATOR_URL``, sonst ``http://localhost:8000``.

    Heisst nicht ``base_url``, weil die Aufrufe einen gleichnamigen Parameter
    haben und die Funktion sonst in deren Rumpf verdeckt waere.

    English: Base URL from ``MEDIATOR_URL``, otherwise
    ``http://localhost:8000``.

    Not named ``base_url`` because the calls have a parameter of the same
    name, and the function would otherwise be shadowed inside their body.
    """
    return os.environ.get("MEDIATOR_URL", DEFAULT_BASE_URL).rstrip("/")


@dataclass
class Result:
    """Ergebnis eines Mediator-Aufrufs.

    ``ok`` heisst: HTTP hat geklappt und die Antwort war lesbares JSON. Ob die
    *Auswahl* erfolgreich war, steht in ``data`` unter ``levels[0].status`` —
    das ist bewusst getrennt, weil eine fehlgeschlagene Ebene keine
    fehlgeschlagene Anfrage ist (siehe SelectionLevelResult).

    English: Result of a mediator call.

    ``ok`` means: HTTP succeeded and the response was readable JSON.
    Whether the *selection* itself succeeded is found in ``data`` under
    ``levels[0].status`` — this is deliberately separate, because a
    failed level is not a failed request (see SelectionLevelResult).
    """

    ok: bool
    status_code: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def levels(self) -> list[dict[str, Any]]:
        """Alle Auswahl-Ebenen der Antwort (eine je gewaehlter Datenquelle).

        English: All selection levels of the response (one per chosen
        data source).
        """
        return list(self.data.get("levels") or [])

    def first_level(self) -> dict[str, Any]:
        """Die erste Auswahl-Ebene der Antwort, oder ``{}``.

        English: The first selection level of the response, or ``{}``.
        """
        levels = self.levels()
        return levels[0] if levels else {}


def build_selection_request(
    *,
    cohorts: list[str],
    modality: str,
    attributes: list[str],
    sources: list[str],
    size: int,
) -> dict[str, Any]:
    """Baut den Auftrag: **eine Ebene je gewaehlter Datenquelle**.

    ``SingleSelection.source`` ist ein einzelner Wert, keine Liste — mehrere
    Quellen werden deshalb zu mehreren Ebenen. Das ist genau, wofuer ``levels``
    gedacht ist: parallele, gleichrangige Auswahlen (ADR-0003, Entscheidung
    7.2), die unabhaengig voneinander gelingen oder scheitern koennen.

    **Mehrere Kohorten stehen in DERSELBEN Ebene**, nicht in mehreren:
    ``SingleSelection.cohorts`` ist eine Liste ("mehrfach waehlbar"), und der
    Mediator holt je Kohorte ``per_cohort_size or size`` Proben
    (``main.py``: ``n_each = per_cohort_size or size``). ``size`` gilt damit pro
    Kohorte — genau das, was man beim Vergleichen will. Geschachtelte Ebenen
    kann der Mediator ebenfalls, diese Fassung nutzt es nicht.

    ``size`` wird auf die Grenzen der OpenAPI geklemmt, damit ein Tippfehler im
    Panel keinen 422er erzeugt.
    Ohne gewaehlte Quelle entsteht eine leere Ebenenliste — der Aufrufer faengt
    das ab, bevor er sendet (der Mediator wuerde mit 422 antworten).

    English: Builds the request: **one level per chosen data source**.

    ``SingleSelection.source`` is a single value, not a list — multiple
    sources therefore become multiple levels. That is exactly what
    ``levels`` is for: parallel, equal-ranked selections (ADR-0003,
    decision 7.2) that can succeed or fail independently of one another.

    **Multiple cohorts live in the SAME level**, not several:
    ``SingleSelection.cohorts`` is a list ("multi-selectable"), and the
    mediator fetches ``per_cohort_size or size`` samples per cohort
    (``main.py``: ``n_each = per_cohort_size or size``). ``size`` thus
    applies per cohort — exactly what you want when comparing. The
    mediator also supports nested levels; this version does not use that.

    ``size`` is clamped to the OpenAPI's limits so that a typo in the
    panel does not produce a 422.
    Without a chosen source an empty level list results — the caller
    catches that before sending (the mediator would respond with 422).
    """
    return {
        "levels": [
            {
                "source": source,
                "cohorts": list(cohorts),
                "modality": modality,
                "attributes": list(attributes),
            }
            for source in sources
        ],
        "size": max(SIZE_MIN, min(SIZE_MAX, int(size))),
    }


def preview(payload: dict[str, Any], *, base_url: str = "", timeout: float = PREVIEW_TIMEOUT) -> Result:
    """``POST /selection/preview`` — Abruf, Uebersetzung, Laden. Keine Matrix.

    English: ``POST /selection/preview`` — fetch, translate, load. No
    matrix.
    """
    return _post("/selection/preview", payload, base_url=base_url, timeout=timeout)


def generate(payload: dict[str, Any], *, base_url: str = "", timeout: float = GENERATE_TIMEOUT) -> Result:
    """``POST /selection/generate`` — dasselbe, plus Download und ``.h5ad``.

    English: ``POST /selection/generate`` — the same, plus download and
    ``.h5ad``.
    """
    return _post("/selection/generate", payload, base_url=base_url, timeout=timeout)


def download(download_url: str, dest_path: str, *, base_url: str = "", timeout: float = GENERATE_TIMEOUT) -> Result:
    """``GET {mediator}{download_url}`` streamen und nach ``dest_path`` schreiben.

    Das ``.h5ad`` entsteht im Mediator-**Container**
    (``app/semantic/paths.py::export_dir()``) und ist von dort aus nicht als
    Host-Pfad sichtbar — der Download-Endpunkt ist der einzige Weg auf den
    Rechner. Dieselbe Streaming-Logik wie ``_download()`` in
    ``scripts/run_selection.py``/``scripts/fetch_pancancer_h5ad.py``.

    ``Result.data`` traegt bei Erfolg ``{"path": dest_path}`` statt einer
    Mediator-Antwort — es gibt hier keine.

    English: Streams ``GET {mediator}{download_url}`` and writes it to
    ``dest_path``.

    The ``.h5ad`` is created inside the mediator **container**
    (``app/semantic/paths.py::export_dir()``) and is not visible from
    there as a host path — the download endpoint is the only way onto
    the machine. Same streaming logic as ``_download()`` in
    ``scripts/run_selection.py``/``scripts/fetch_pancancer_h5ad.py``.

    On success, ``Result.data`` carries ``{"path": dest_path}`` instead
    of a mediator response — there is none here.
    """
    url = (base_url or default_base_url()).rstrip("/") + download_url
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            if not resp.ok:
                return Result(
                    ok=False,
                    status_code=resp.status_code,
                    error=f"HTTP {resp.status_code} bei {download_url}: {_detail(resp)}",
                )
            out = Path(dest_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
    except requests.Timeout:
        return Result(ok=False, error=f"Zeitüberschreitung nach {timeout:.0f}s beim Download.")
    except requests.ConnectionError:
        return Result(ok=False, error=f"Mediator nicht erreichbar unter {url}.")
    except requests.RequestException as exc:
        return Result(ok=False, error=f"Download fehlgeschlagen: {exc}")
    except OSError as exc:
        return Result(ok=False, error=f"Datei konnte nicht geschrieben werden: {exc}")
    return Result(ok=True, status_code=200, data={"path": str(dest_path)})


def _post(path: str, payload: dict[str, Any], *, base_url: str, timeout: float) -> Result:
    url = (base_url or default_base_url()).rstrip("/") + path
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.Timeout:
        return Result(ok=False, error=f"Zeitüberschreitung nach {timeout:.0f}s bei {path}.")
    except requests.ConnectionError:
        return Result(
            ok=False,
            error=f"Mediator nicht erreichbar unter {url}.\n"
                  f"Zuerst starten:  .\\start_all.ps1   (oder: docker compose up -d mediator)",
        )
    except requests.RequestException as exc:
        return Result(ok=False, error=f"Anfrage fehlgeschlagen: {exc}")

    if not resp.ok:
        return Result(
            ok=False,
            status_code=resp.status_code,
            error=f"HTTP {resp.status_code} bei {path}: {_detail(resp)}",
        )
    try:
        data = resp.json()
    except ValueError:
        return Result(ok=False, status_code=resp.status_code,
                      error=f"Ungültige JSON-Antwort von {path}.")
    return Result(ok=True, status_code=resp.status_code, data=data)


def _detail(resp: requests.Response) -> str:
    """``detail`` aus einer FastAPI-Fehlerantwort ziehen (JSON-Dict/-String oder Text).

    English: Extracts ``detail`` from a FastAPI error response (JSON
    dict/string or plain text).
    """
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:500] or "(kein Body)"
    if isinstance(data, dict):
        return str(data.get("detail", data))[:500]
    return str(data)[:500]
