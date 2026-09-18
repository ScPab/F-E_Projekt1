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
PREVIEW_TIMEOUT = 60.0
GENERATE_TIMEOUT = 900.0

# Grenzen aus der OpenAPI (SelectionRequest.size).
SIZE_MIN = 1
SIZE_MAX = 200


def default_base_url() -> str:
    """Basis-URL aus ``MEDIATOR_URL``, sonst ``http://localhost:8000``.

    Heisst nicht ``base_url``, weil die Aufrufe einen gleichnamigen Parameter
    haben und die Funktion sonst in deren Rumpf verdeckt waere.
    """
    return os.environ.get("MEDIATOR_URL", DEFAULT_BASE_URL).rstrip("/")


@dataclass
class Result:
    """Ergebnis eines Mediator-Aufrufs.

    ``ok`` heisst: HTTP hat geklappt und die Antwort war lesbares JSON. Ob die
    *Auswahl* erfolgreich war, steht in ``data`` unter ``levels[0].status`` —
    das ist bewusst getrennt, weil eine fehlgeschlagene Ebene keine
    fehlgeschlagene Anfrage ist (siehe SelectionLevelResult).
    """

    ok: bool
    status_code: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def levels(self) -> list[dict[str, Any]]:
        """Alle Auswahl-Ebenen der Antwort (eine je gewaehlter Datenquelle)."""
        return list(self.data.get("levels") or [])

    def first_level(self) -> dict[str, Any]:
        """Die erste Auswahl-Ebene der Antwort, oder ``{}``."""
        levels = self.levels()
        return levels[0] if levels else {}


def build_selection_request(
    *,
    cohort: str,
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

    Mehrere Kohorten und geschachtelte Ebenen kann der Mediator ebenfalls, diese
    Fassung der Oberflaeche nutzt es noch nicht. ``size`` wird auf die Grenzen
    der OpenAPI geklemmt, damit ein Tippfehler im Panel keinen 422er erzeugt.
    Ohne gewaehlte Quelle entsteht eine leere Ebenenliste — der Aufrufer faengt
    das ab, bevor er sendet (der Mediator wuerde mit 422 antworten).
    """
    return {
        "levels": [
            {
                "source": source,
                "cohorts": [cohort],
                "modality": modality,
                "attributes": list(attributes),
            }
            for source in sources
        ],
        "size": max(SIZE_MIN, min(SIZE_MAX, int(size))),
    }


def preview(payload: dict[str, Any], *, base_url: str = "", timeout: float = PREVIEW_TIMEOUT) -> Result:
    """``POST /selection/preview`` — Abruf, Uebersetzung, Laden. Keine Matrix."""
    return _post("/selection/preview", payload, base_url=base_url, timeout=timeout)


def generate(payload: dict[str, Any], *, base_url: str = "", timeout: float = GENERATE_TIMEOUT) -> Result:
    """``POST /selection/generate`` — dasselbe, plus Download und ``.h5ad``."""
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
    """``detail`` aus einer FastAPI-Fehlerantwort ziehen (JSON-Dict/-String oder Text)."""
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:500] or "(kein Body)"
    if isinstance(data, dict):
        return str(data.get("detail", data))[:500]
    return str(data)[:500]
