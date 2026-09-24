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

English: Wrapper for the ENA (European Nucleotide Archive) API — EBI Portal
API.

In the spirit of the mediator-wrapper pattern, this module encapsulates all
access to one concrete data source (here: ENA via the EBI Portal API,
https://www.ebi.ac.uk/ena/portal/api/) and delivers data in a normalized
intermediate form expected by the mediator. The transformation to
anndata/.h5ad is deliberately NOT part of this wrapper — that is a separate,
later step on the mediator side (see `wrappers/gdc/client.py` for the same
principle in the first wrapper).

Two-tier access pattern, analogous to the GDC wrapper:
  - Metadata tier (`query`, `search`, `get_schema`): a single JSON endpoint
    (`/search`), very similar to GDC — search query + field list +
    `limit`/`offset` pagination. Field-name/schema introspection via
    `/returnFields` (instead of `_mapping` for GDC).
  - Bulk tier (`get_download_links`, `download_fastq_files`): ENA has no
    separate manifest endpoint and no external tool like `gdc-client` —
    `/search` already delivers the finished FASTQ download URLs for a read
    run in the `fastq_ftp` field (multiple files semicolon-separated),
    reachable directly via HTTPS (verified live).

IMPORTANT DIFFERENCE FROM GDC/GEO: the ENA `/search` response contains NO
total hit count (no "total" as with GDC, no "count" as with GEO's
`esearch`). `pagination.has_more` in `query()` is therefore only a heuristic
(page completely full -> presumably more hits), not reliable proof — if a
real total count is needed, a different ENA endpoint would additionally
have to be checked (e.g. `/api/beta/search` with different semantics),
which was deliberately not done here (no verified need in the prototype).

ONTOLOGY/MAPPING LAYER (later expansion stage, analogous to the GDC
wrapper): `get_schema()` supplies the raw field names (`columnId`) of the
ENA API. This list is the basis against which future field mappings (ENA
field -> internal DataBridge schema/ontology term) are defined. `query`/
`search` currently still return results with the original ENA field names
(`results`) — the translation into a unified internal schema is the place
where a mapping table or ontology connection would dock in.
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
# EN: Result types ("result") per the ENA Portal API (`GET /results`) — a
# selection of the ones relevant for the test case (raw data/study
# metadata), not the full list (e.g. "assembly", "coding"/"noncoding" etc.
# are missing).
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

    English: Builds an ENA search query string (`query` parameter of
    `/search`) from simplified search parameters.

    Deliberately covers only the fields needed for the prototype (full list
    via `ENAWrapper.get_schema()` or `/returnFields`):
      - study_accession    – e.g. "PRJEB1234"
      - library_strategy   – e.g. "RNA-Seq"
      - instrument_platform – e.g. "ILLUMINA"
    Further conditions can be added via `extra` (a list of raw query
    fragments) without changing this function — analogous to `extra` in
    `build_filters()` in the GDC wrapper.

    Example: build_query(study_accession="PRJEB1234", library_strategy="RNA-Seq")
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

    English: Encapsulates access to ENA (European Nucleotide Archive) for
    the mediator.

    Base URL per the ENA Portal API documentation:
    https://www.ebi.ac.uk/ena/portal/api (configurable via the constructor
    parameter `base_url` — analogous to the GDC wrapper, an environment
    variable `ENA_API_BASE_URL` would be the next step once the mediator
    connects this wrapper, see README.md).
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

        English: Runs a paginated search against an ENA result type.

        `result`: one of `RESULT_TYPES` (default `read_run` — individual
        sequencing runs, analogous to GDC's default endpoint `files`).
        Pagination via `limit`/`offset` (named `size`/`from_` here,
        analogous to the GDC wrapper).

        The query specification itself is stored as a tier-1 cache entry
        ("recipe"), as in the GDC wrapper.
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
            # EN: ENA delivers no total hit count (see module docstring) —
            # "has_more" is only a heuristic (page full -> presumably more
            # hits), not reliable proof.
            "pagination": {"limit": size, "offset": from_, "retrieved": len(results), "has_more": len(results) == size},
            # ENA-Originalfeldnamen unverändert — Übersetzung ins interne
            # Schema ist Aufgabe der späteren Ontologie-/Mapping-Schicht,
            # analog zum GDC-Wrapper (siehe Modul-Docstring).
            # EN: Original ENA field names unchanged — translation into the
            # internal schema is the job of the later ontology/mapping
            # layer, analogous to the GDC wrapper (see module docstring).
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

        English: Convenience function analogous to `GDCWrapper.search()`:
        builds a search query from simplified parameters (study accession,
        library strategy, sequencing platform) and calls `query()`.

        Example: search(study_accession="PRJEB1234", library_strategy="RNA-Seq")
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

        English: Fetches `returnFields` for an ENA result type and returns
        the available field names (`columnId`) sorted as a list.

        Analogous to `GDCWrapper.get_schema()` (`_mapping` there): this
        field list is the basis against which future field mappings (ENA
        field name -> internal DataBridge schema/ontology term) are defined.
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

        English: Returns the FASTQ download URLs (+ file sizes) for a read
        run, from the `fastq_ftp`/`fastq_bytes` fields of a `read_run`
        search.

        ENA has no standalone manifest endpoint like GDC
        (`/files?return_type=manifest`); the download addresses come
        directly along with the metadata search. `fastq_ftp` delivers
        host-relative paths without a scheme (e.g.
        "ftp.sra.ebi.ac.uk/vol1/..."), which are verified live to also be
        fetchable via HTTPS — without an auth token, since only openly
        accessible read runs deliver a `fastq_ftp` field (controlled data
        delivers an empty value here).
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

        English: Downloads the FASTQ files of a read run directly via HTTP.

        Unlike the GDC wrapper (`download_via_gdc_client`, external
        `gdc-client` tool via subprocess), there is no comparable external
        bulk-download tool for ENA — the addresses delivered by the search
        are complete, directly fetchable file URLs (no directory listing
        needed as with the GEO wrapper).

        Raw data conceptually belongs in the tier-3 cache (`self.cache.raw`,
        see cache.py) and should be removed again after processing via
        `purge()` — as in the GDC wrapper, only a hint here, the actual
        target path is supplied by the caller.
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

        English: Converts an ENA response into the target format anndata/.h5ad.

        Deliberately not part of this wrapper (see module docstring) — the
        wrapper delivers structured metadata/raw-data references, the
        transformation to anndata is a separate mediator-side step.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
