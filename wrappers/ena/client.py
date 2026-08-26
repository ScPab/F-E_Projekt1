"""
Wrapper für die ENA (European Nucleotide Archive) API — EBI Portal API.

Im Sinne des Mediator-Wrapper-Musters kapselt dieses Modul den gesamten
Zugriff auf eine konkrete Datenquelle (hier: ENA über die EBI Portal API,
https://www.ebi.ac.uk/ena/portal/api/) und liefert Daten in einer vom
Mediator erwarteten, normalisierten Zwischenform. Die Transformation nach
anndata/.h5ad ist bewusst NICHT Teil dieses Wrappers — das ist ein
separater, späterer Schritt auf Mediator-Seite (siehe `wrappers/gdc/client.py`
für dasselbe Prinzip beim ersten Wrapper).

Zwei-Tier-Zugriffsmuster, analog zum GDC-Wrapper:
  - Metadaten-Tier (`query`, `search`, `get_schema`): ein einzelner
    JSON-Endpunkt (`/search`), sehr ähnlich zu GDC — Suchquery + Feldliste +
    `limit`/`offset`-Pagination. Feldnamen/Schema-Introspektion über
    `/returnFields` (statt `_mapping` bei GDC).
  - Bulk-Tier (`get_download_links`, `download_fastq_files`): ENA hat keinen
    separaten Manifest-Endpunkt und kein externes Tool wie `gdc-client` —
    `/search` liefert für einen Read-Run bereits die fertigen FASTQ-Download-
    URLs im Feld `fastq_ftp` (mehrere Dateien Semikolon-getrennt) mit,
    erreichbar direkt per HTTPS (live verifiziert).

WICHTIGER UNTERSCHIED ZU GDC/GEO: Die ENA-`/search`-Antwort enthält KEINE
Gesamttrefferzahl (kein "total" wie bei GDC, kein "count" wie bei GEOs
`esearch`). `pagination.has_more` in `query()` ist daher nur eine Heuristik
(Seite komplett voll -> vermutlich weitere Treffer), kein verlässlicher Beweis
— bei Bedarf einer echten Gesamtzahl müsste zusätzlich gegen einen anderen
ENA-Endpunkt (z. B. `/api/beta/search` mit anderer Semantik) geprüft werden,
was hier bewusst nicht gemacht wurde (kein verifizierter Bedarf im Prototyp).

ONTOLOGIE-/MAPPING-SCHICHT (spätere Ausbaustufe, analog zum GDC-Wrapper):
`get_schema()` liefert die Roh-Feldnamen (`columnId`) der ENA-API. Diese
Liste ist die Grundlage, gegen die künftige Feld-Mappings (ENA-Feld ->
internes DataBridge-Schema/Ontologie-Begriff) definiert werden. `query`/
`search` geben Ergebnisse aktuell noch mit den ENA-Originalfeldnamen zurück
(`results`) — die Übersetzung in ein einheitliches internes Schema ist die
Stelle, an der eine Mapping-Tabelle oder Ontologie-Anbindung andocken würde.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional, Union

import requests

from .cache import WrapperCache

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/ena/portal/api"
DEFAULT_TIMEOUT = 30

# Ergebnistypen ("result") laut ENA Portal API (`GET /results`) — Auswahl der
# für den Testfall relevanten (Rohdaten/Studien-Metadaten), nicht die
# vollständige Liste (u. a. fehlen "assembly", "coding"/"noncoding" etc.).
RESULT_TYPES = ("read_run", "read_experiment", "read_study", "study", "sample", "analysis")

StrOrList = Union[str, Iterable[str]]


def build_query(
    *,
    study_accession: Optional[StrOrList] = None,
    library_strategy: Optional[StrOrList] = None,
    instrument_platform: Optional[StrOrList] = None,
    extra: Optional[list[str]] = None,
) -> Optional[str]:
    """Baut einen ENA-Suchquery-String (`query`-Parameter von `/search`) aus
    vereinfachten Suchparametern.

    Deckt bewusst nur die für den Prototyp benötigten Felder ab (volle Liste
    über `ENAWrapper.get_schema()` bzw. `/returnFields`):
      - study_accession    – z. B. "PRJEB1234"
      - library_strategy   – z. B. "RNA-Seq"
      - instrument_platform – z. B. "ILLUMINA"
    Weitere Bedingungen lassen sich über `extra` (Liste roher
    Query-Fragmente) ergänzen, ohne diese Funktion zu ändern — analog zu
    `extra` bei `build_filters()` im GDC-Wrapper.

    Beispiel: build_query(study_accession="PRJEB1234", library_strategy="RNA-Seq")
        -> 'study_accession="PRJEB1234" AND library_strategy="RNA-Seq"'
    """
    parts: list[str] = []

    def _eq(field: str, value: StrOrList) -> None:
        values = [value] if isinstance(value, str) else list(value)
        if len(values) == 1:
            parts.append(f'{field}="{values[0]}"')
        else:
            parts.append("(" + " OR ".join(f'{field}="{v}"' for v in values) + ")")

    if study_accession:
        _eq("study_accession", study_accession)
    if library_strategy:
        _eq("library_strategy", library_strategy)
    if instrument_platform:
        _eq("instrument_platform", instrument_platform)
    if extra:
        parts.extend(extra)

    if not parts:
        return None
    return " AND ".join(parts)


class ENAWrapper:
    """Kapselt den Zugriff auf ENA (European Nucleotide Archive) für den Mediator.

    Basis-URL laut ENA-Portal-API-Dokumentation:
    https://www.ebi.ac.uk/ena/portal/api (konfigurierbar über den
    Konstruktor-Parameter `base_url` — analog zum GDC-Wrapper wäre eine
    Umgebungsvariable `ENA_API_BASE_URL` der nächste Schritt, sobald der
    Mediator diesen Wrapper anbindet, siehe README.md).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        cache: Optional[WrapperCache] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.cache = cache or WrapperCache()

    # ------------------------------------------------------------------
    # Metadaten-Tier
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        result: str = "read_run",
        query: Optional[str] = None,
        fields: Optional[list[str]] = None,
        size: int = 20,
        from_: int = 0,
        sort: Optional[str] = None,
    ) -> dict:
        """Führt eine paginierte Suche gegen einen ENA-Ergebnistyp aus.

        `result`: einer von `RESULT_TYPES` (Standard `read_run` — einzelne
        Sequenzierläufe, analog zu GDCs Standard-Endpunkt `files`).
        Pagination über `limit`/`offset` (hier als `size`/`from_` benannt,
        analog zum GDC-Wrapper).

        Die Query-Spezifikation selbst wird als Tier-1-Cache-Eintrag
        ("Recipe") abgelegt, wie im GDC-Wrapper.
        """
        if result not in RESULT_TYPES:
            raise ValueError(f"Unbekannter ENA-Ergebnistyp: {result!r} (erwartet: {RESULT_TYPES})")

        recipe = {"result": result, "query": query, "fields": fields, "size": size, "from": from_, "sort": sort}
        recipe_key = self.cache.recipes.key_for(recipe)
        self.cache.recipes.set(recipe_key, recipe)

        params: dict[str, Any] = {"result": result, "format": "json", "limit": size, "offset": from_}
        if query:
            params["query"] = query
        if fields:
            params["fields"] = ",".join(fields)
        if sort:
            params["sortFields"] = sort

        response = self.session.get(f"{self.base_url}/search", params=params, timeout=self.timeout)
        response.raise_for_status()
        results = response.json()

        return {
            "source": "ena",
            "result": result,
            "recipe_key": recipe_key,
            # ENA liefert keine Gesamttrefferzahl (siehe Modul-Docstring) —
            # "has_more" ist nur eine Heuristik (Seite voll -> vermutlich
            # weitere Treffer vorhanden), kein verlässlicher Beweis.
            "pagination": {"limit": size, "offset": from_, "retrieved": len(results), "has_more": len(results) == size},
            # ENA-Originalfeldnamen unverändert — Übersetzung ins interne
            # Schema ist Aufgabe der späteren Ontologie-/Mapping-Schicht,
            # analog zum GDC-Wrapper (siehe Modul-Docstring).
            "results": results,
        }

    def search(
        self,
        *,
        result: str = "read_run",
        study_accession: Optional[StrOrList] = None,
        library_strategy: Optional[StrOrList] = None,
        instrument_platform: Optional[StrOrList] = None,
        fields: Optional[list[str]] = None,
        size: int = 20,
        from_: int = 0,
    ) -> dict:
        """Komfort-Funktion analog zu `GDCWrapper.search()`: baut einen
        Suchquery aus vereinfachten Parametern (Studien-Accession,
        Library-Strategie, Sequenzier-Plattform) und ruft `query()` auf.

        Beispiel: search(study_accession="PRJEB1234", library_strategy="RNA-Seq")
        """
        query = build_query(
            study_accession=study_accession,
            library_strategy=library_strategy,
            instrument_platform=instrument_platform,
        )
        return self.query(result=result, query=query, fields=fields, size=size, from_=from_)

    def get_schema(self, result: str = "read_run") -> list[str]:
        """Ruft `returnFields` für einen ENA-Ergebnistyp ab und liefert die
        verfügbaren Feldnamen (`columnId`) sortiert als Liste.

        Analog zu `GDCWrapper.get_schema()` (dort `_mapping`): Diese
        Feldliste ist die Grundlage, gegen die künftige Feld-Mappings
        (ENA-Feldname -> internes DataBridge-Schema/Ontologie-Begriff)
        definiert werden.
        """
        if result not in RESULT_TYPES:
            raise ValueError(f"Unbekannter ENA-Ergebnistyp: {result!r} (erwartet: {RESULT_TYPES})")

        params = {"result": result, "format": "json"}
        response = self.session.get(f"{self.base_url}/returnFields", params=params, timeout=self.timeout)
        response.raise_for_status()
        fields = response.json()
        return sorted(field["columnId"] for field in fields if "columnId" in field)

    # ------------------------------------------------------------------
    # Bulk-Tier
    # ------------------------------------------------------------------

    def get_download_links(self, run_accession: str) -> dict:
        """Liefert die FASTQ-Download-URLs (+ Dateigrößen) für einen
        Read-Run, aus den Feldern `fastq_ftp`/`fastq_bytes` einer
        `read_run`-Suche.

        ENA hat keinen eigenständigen Manifest-Endpunkt wie GDC
        (`/files?return_type=manifest`); die Download-Adressen kommen direkt
        aus der Metadaten-Suche mit. `fastq_ftp` liefert Host-relative
        Pfade ohne Schema (z. B. "ftp.sra.ebi.ac.uk/vol1/..."), die live
        verifiziert auch per HTTPS abrufbar sind — ohne Auth-Token, da nur
        offen zugängliche Read-Runs ein `fastq_ftp`-Feld liefern (kontrollierte
        Daten liefern hier einen leeren Wert).
        """
        result = self.query(
            result="read_run",
            query=f'run_accession="{run_accession}"',
            fields=["run_accession", "fastq_ftp", "fastq_bytes"],
            size=1,
        )
        hits = result["results"]
        if not hits:
            return {"run_accession": run_accession, "files": []}

        raw_urls = [u for u in hits[0].get("fastq_ftp", "").split(";") if u]
        raw_sizes = [s for s in hits[0].get("fastq_bytes", "").split(";") if s]

        files = []
        for i, url in enumerate(raw_urls):
            full_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
            files.append({"url": full_url, "bytes": int(raw_sizes[i]) if i < len(raw_sizes) else None})

        return {"run_accession": run_accession, "files": files}

    def download_fastq_files(self, run_accession: str, output_dir: str) -> dict:
        """Lädt die FASTQ-Dateien eines Read-Runs direkt per HTTP herunter.

        Anders als beim GDC-Wrapper (`download_via_gdc_client`, externes
        Tool `gdc-client` per Subprocess) gibt es für ENA kein
        vergleichbares externes Bulk-Download-Tool — die von der Suche
        gelieferten Adressen sind vollständige, direkt abrufbare
        Datei-URLs (kein Verzeichnis-Listing wie beim GEO-Wrapper nötig).

        Rohdaten gehören konzeptionell in den Tier-3-Cache (`self.cache.raw`,
        siehe cache.py) und sollten nach Verarbeitung via `purge()` wieder
        entfernt werden — wie im GDC-Wrapper nur als Hinweis, der eigentliche
        Zielpfad wird vom Aufrufer vorgegeben.
        """
        links = self.get_download_links(run_accession)
        if not links["files"]:
            return {"status": "not_found", "run_accession": run_accession, "files": []}

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[str] = []
        for entry in links["files"]:
            url = entry["url"]
            name = url.rsplit("/", 1)[-1]
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()
            with open(out_dir / name, "wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    fh.write(chunk)
            downloaded.append(name)

        return {"status": "completed", "run_accession": run_accession, "files": downloaded}

    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine ENA-Antwort in das Zielformat anndata/.h5ad.

        Bewusst nicht Teil dieses Wrappers (siehe Modul-Docstring) — der
        Wrapper liefert strukturierte Metadaten/Rohdaten-Referenzen, die
        Transformation nach anndata ist ein separater Mediator-seitiger
        Schritt.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
