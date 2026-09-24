"""
Wrapper für die GEO (Gene Expression Omnibus) API — NCBI E-utilities.

Im Sinne des Mediator-Wrapper-Musters kapselt dieses Modul den gesamten
Zugriff auf eine konkrete Datenquelle (hier: GEO über die NCBI-E-utilities,
https://www.ncbi.nlm.nih.gov/books/NBK25497/) und liefert Daten in einer vom
Mediator erwarteten, normalisierten Zwischenform. Die Transformation nach
anndata/.h5ad ist bewusst NICHT Teil dieses Wrappers — das ist ein
separater, späterer Schritt auf Mediator-Seite (siehe `wrappers/gdc/client.py`
für dasselbe Prinzip beim ersten Wrapper).

Zwei-Tier-Zugriffsmuster, analog zum GDC-Wrapper, aber mit anderer
API-Mechanik:
  - Metadaten-Tier (`query`, `search`, `get_schema`): GEO hat keinen
    einzelnen JSON-Suchendpunkt wie GDC, sondern ein zweistufiges Muster:
    `esearch` liefert zu einem Suchterm eine paginierte Liste interner UIDs,
    `esummary` liefert dazu die eigentlichen Metadaten (DocumentSummary je
    UID). Beide Schritte werden hier in `query()` gebündelt. Für
    Feldnamen/Schema-Introspektion gibt es `einfo` (statt `_mapping` bei
    GDC).
  - Bulk-Tier (`get_ftp_link`, `download_supplementary_files`): GEO hat
    keinen Manifest-Endpunkt und kein externes Bulk-Download-Tool wie
    `gdc-client` — `esummary` liefert stattdessen bereits einen direkten
    FTP-Verzeichnislink (`ftplink`) je Treffer, der sich per HTTP-GET
    abrufen lässt.

ONTOLOGIE-/MAPPING-SCHICHT (spätere Ausbaustufe, analog zum GDC-Wrapper):
`get_schema()` liefert die Roh-Feld-Tags der GEO/NCBI-API (z. B. "ORGN",
"ACCN", "ETYP"). Diese Liste ist die Grundlage, gegen die künftige
Feld-Mappings (GEO-Feld -> internes DataBridge-Schema/Ontologie-Begriff)
definiert werden. `query`/`search` geben Ergebnisse aktuell noch mit den
NCBI-Originalfeldnamen zurück (`results`) — die Übersetzung in ein
einheitliches internes Schema ist die Stelle, an der eine Mapping-Tabelle
oder Ontologie-Anbindung andocken würde.

Hinweis zur NCBI-Nutzungsrichtlinie: automatisierte Zugriffe sollen laut
NCBI `tool`- und `email`-Parameter mitschicken und sind ohne `api_key` auf
3 Anfragen/Sekunde begrenzt (siehe Docstring von `GEOWrapper.__init__`).

English: Wrapper for the GEO (Gene Expression Omnibus) API — NCBI
E-utilities.

In the spirit of the mediator-wrapper pattern, this module encapsulates all
access to one concrete data source (here: GEO via the NCBI E-utilities,
https://www.ncbi.nlm.nih.gov/books/NBK25497/) and delivers data in a
normalized intermediate form expected by the mediator. The transformation to
anndata/.h5ad is deliberately NOT part of this wrapper — that is a separate,
later step on the mediator side (see `wrappers/gdc/client.py` for the same
principle in the first wrapper).

Two-tier access pattern, analogous to the GDC wrapper, but with different
API mechanics:
  - Metadata tier (`query`, `search`, `get_schema`): GEO has no single JSON
    search endpoint like GDC, but a two-step pattern: `esearch` returns a
    paginated list of internal UIDs for a search term, `esummary` then
    returns the actual metadata (DocumentSummary per UID). Both steps are
    bundled here in `query()`. For field-name/schema introspection there is
    `einfo` (instead of `_mapping` for GDC).
  - Bulk tier (`get_ftp_link`, `download_supplementary_files`): GEO has no
    manifest endpoint and no external bulk-download tool like `gdc-client`
    — instead, `esummary` already delivers a direct FTP directory link
    (`ftplink`) per hit, which can be fetched via HTTP GET.

ONTOLOGY/MAPPING LAYER (later expansion stage, analogous to the GDC
wrapper): `get_schema()` supplies the raw field tags of the GEO/NCBI API
(e.g. "ORGN", "ACCN", "ETYP"). This list is the basis against which future
field mappings (GEO field -> internal DataBridge schema/ontology term) are
defined. `query`/`search` currently still return results with the original
NCBI field names (`results`) — the translation into a unified internal
schema is the place where a mapping table or ontology connection would dock
in.

Note on the NCBI usage policy: per NCBI, automated access should include
`tool` and `email` parameters and is limited to 3 requests/second without an
`api_key` (see the docstring of `GEOWrapper.__init__`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import requests

from .cache import WrapperCache

DEFAULT_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TIMEOUT = 30

# Entrez-Datenbank für GEO-Metadaten (Series/DataSets/Samples/Platforms).
# Andere Entrez-Datenbanken (z. B. "pubmed") sind bewusst außerhalb des
# Testfalls dieses Wrappers.
# EN: Entrez database for GEO metadata (series/datasets/samples/platforms).
# Other Entrez databases (e.g. "pubmed") are deliberately outside this
# wrapper's test case.
GEO_DB = "gds"

StrOrList = Union[str, Iterable[str]]


def build_search_term(
    *,
    accession: Optional[str] = None,
    organism: Optional[StrOrList] = None,
    entry_type: Optional[str] = "gse",
    extra: Optional[list[str]] = None,
) -> Optional[str]:
    """Baut einen NCBI-Entrez-Suchterm (`term`) für die GEO-Datenbank (`gds`)
    aus vereinfachten Suchparametern.

    Deckt bewusst nur die für den Prototyp benötigten Feld-Tags ab (volle
    Liste über `GEOWrapper.get_schema()` bzw. `einfo.fcgi?db=gds`):
      - ACCN  – GEO-Accession (z. B. "GSE68849")
      - ORGN  – Organismus (z. B. "Homo sapiens")
      - ETYP  – Eintragstyp: gse (Series), gds (curated DataSet), gpl
                (Platform), gsm (Sample). Standardwert "gse", analog zum
                GDC-Wrapper-Standard `access="open"` (sinnvoller Default
                statt aller Eintragstypen gemischt).
    Weitere Bedingungen lassen sich über `extra` (Liste roher
    Entrez-Term-Fragmente) ergänzen, ohne diese Funktion zu ändern — analog
    zu `extra` bei `build_filters()` im GDC-Wrapper.

    Beispiel (Testfall Serien-Metadaten, Mensch):
        build_search_term(organism="Homo sapiens", entry_type="gse")
        -> 'Homo sapiens[ORGN] AND gse[ETYP]'

    English: Builds an NCBI Entrez search term (`term`) for the GEO database
    (`gds`) from simplified search parameters.

    Deliberately covers only the field tags needed for the prototype (full
    list via `GEOWrapper.get_schema()` or `einfo.fcgi?db=gds`):
      - ACCN  – GEO accession (e.g. "GSE68849")
      - ORGN  – organism (e.g. "Homo sapiens")
      - ETYP  – entry type: gse (series), gds (curated dataset), gpl
                (platform), gsm (sample). Default value "gse", analogous to
                the GDC wrapper's default `access="open"` (a sensible
                default instead of all entry types mixed together).
    Further conditions can be added via `extra` (a list of raw Entrez term
    fragments) without changing this function — analogous to `extra` in
    `build_filters()` in the GDC wrapper.

    Example (test case series metadata, human):
        build_search_term(organism="Homo sapiens", entry_type="gse")
        -> 'Homo sapiens[ORGN] AND gse[ETYP]'
    """
    parts: list[str] = []

    def _field(tag: str, value: StrOrList) -> None:
        values = [value] if isinstance(value, str) else list(value)
        if len(values) == 1:
            parts.append(f"{values[0]}[{tag}]")
        else:
            parts.append("(" + " OR ".join(f"{v}[{tag}]" for v in values) + ")")

    if accession:
        _field("ACCN", accession)
    if organism:
        _field("ORGN", organism)
    if entry_type:
        _field("ETYP", entry_type)
    if extra:
        parts.extend(extra)

    if not parts:
        return None
    return " AND ".join(parts)


class GEOWrapper:
    """Kapselt den Zugriff auf GEO (Gene Expression Omnibus) für den Mediator.

    Basis-URL laut NCBI-E-utilities-Dokumentation:
    https://eutils.ncbi.nlm.nih.gov/entrez/eutils (konfigurierbar über den
    Konstruktor-Parameter `base_url` — analog zum GDC-Wrapper wäre eine
    Umgebungsvariable `GEO_API_BASE_URL` der nächste Schritt, sobald der
    Mediator diesen Wrapper anbindet, siehe README.md).

    `tool`/`email`/`api_key`: NCBI bittet automatisierte Aufrufer, sich über
    `tool` und `email` zu identifizieren, und begrenzt Zugriffe ohne
    `api_key` auf 3 Anfragen/Sekunde (siehe
    https://www.ncbi.nlm.nih.gov/books/NBK25497/). `api_key` fällt ohne
    Angabe auf die Umgebungsvariable `GEO_API_KEY` zurück, falls gesetzt.

    English: Encapsulates access to GEO (Gene Expression Omnibus) for the
    mediator.

    Base URL per the NCBI E-utilities documentation:
    https://eutils.ncbi.nlm.nih.gov/entrez/eutils (configurable via the
    constructor parameter `base_url` — analogous to the GDC wrapper, an
    environment variable `GEO_API_BASE_URL` would be the next step once the
    mediator connects this wrapper, see README.md).

    `tool`/`email`/`api_key`: NCBI asks automated callers to identify
    themselves via `tool` and `email`, and limits access without an
    `api_key` to 3 requests/second (see
    https://www.ncbi.nlm.nih.gov/books/NBK25497/). `api_key` falls back to
    the `GEO_API_KEY` environment variable if not given and set.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        cache: Optional[WrapperCache] = None,
        timeout: int = DEFAULT_TIMEOUT,
        tool: Optional[str] = "databridge-geo-wrapper",
        email: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.cache = cache or WrapperCache()
        self.tool = tool
        self.email = email
        self.api_key = api_key or os.environ.get("GEO_API_KEY")

    def _base_params(self, params: dict) -> dict:
        """Ergänzt gemeinsame E-utilities-Parameter (Tool-/E-Mail-Kennung,
        optionaler API-Key) um jeden Request, wie von NCBI empfohlen.

        English: Adds common E-utilities parameters (tool/email
        identification, optional API key) to every request, as recommended
        by NCBI.
        """
        merged = dict(params)
        if self.tool:
            merged["tool"] = self.tool
        if self.email:
            merged["email"] = self.email
        if self.api_key:
            merged["api_key"] = self.api_key
        return merged

    # ------------------------------------------------------------------
    # Metadaten-Tier
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        term: Optional[str] = None,
        db: str = GEO_DB,
        size: int = 20,
        from_: int = 0,
        sort: Optional[str] = None,
    ) -> dict:
        """Führt eine paginierte Suche gegen eine Entrez-Datenbank (Standard:
        `gds`) aus.

        Zwei-Schritt-Muster laut NCBI-E-utilities-Dokumentation: `esearch`
        liefert zu `term` eine Liste interner UIDs (paginiert über
        `retstart`/`retmax`, hier als `from_`/`size` benannt — analog zum
        GDC-Wrapper), `esummary` liefert dazu die DocumentSummaries. Beide
        Schritte werden hier gebündelt (bei GDC genügt ein einzelner
        Endpunkt-Call).

        Die Suchterm-Spezifikation selbst wird als Tier-1-Cache-Eintrag
        ("Recipe") abgelegt, wie im GDC-Wrapper.

        English: Runs a paginated search against an Entrez database (default:
        `gds`).

        Two-step pattern per the NCBI E-utilities documentation: `esearch`
        returns a list of internal UIDs for `term` (paginated via
        `retstart`/`retmax`, named `from_`/`size` here — analogous to the
        GDC wrapper), `esummary` then returns the DocumentSummaries. Both
        steps are bundled here (a single endpoint call is enough for GDC).

        The search-term specification itself is stored as a tier-1 cache
        entry ("recipe"), as in the GDC wrapper.
        """
        recipe = {"term": term, "db": db, "size": size, "from": from_, "sort": sort}
        recipe_key = self.cache.recipes.key_for(recipe)
        self.cache.recipes.set(recipe_key, recipe)

        search_params = self._base_params(
            {
                "db": db,
                "term": term or "all[FILT]",
                "retmode": "json",
                "retstart": from_,
                "retmax": size,
            }
        )
        if sort:
            search_params["sort"] = sort

        search_response = self.session.get(
            f"{self.base_url}/esearch.fcgi", params=search_params, timeout=self.timeout
        )
        search_response.raise_for_status()
        search_payload = search_response.json().get("esearchresult", {})
        uids = search_payload.get("idlist", [])

        results: list[dict] = []
        if uids:
            summary_params = self._base_params({"db": db, "id": ",".join(uids), "retmode": "json"})
            summary_response = self.session.get(
                f"{self.base_url}/esummary.fcgi", params=summary_params, timeout=self.timeout
            )
            summary_response.raise_for_status()
            summary_payload = summary_response.json().get("result", {})
            results = [summary_payload[uid] for uid in uids if uid in summary_payload]

        return {
            "source": "geo",
            "db": db,
            "recipe_key": recipe_key,
            "pagination": {
                "total": int(search_payload.get("count", 0)),
                "retstart": int(search_payload.get("retstart", from_)),
                "retmax": int(search_payload.get("retmax", size)),
            },
            # NCBI-Originalfeldnamen unverändert (z. B. "accession",
            # "gdstype", "entrytype", "ftplink") — Übersetzung ins interne
            # Schema ist Aufgabe der späteren Ontologie-/Mapping-Schicht,
            # analog zum GDC-Wrapper (siehe Modul-Docstring).
            # EN: Original NCBI field names unchanged (e.g. "accession",
            # "gdstype", "entrytype", "ftplink") — translation into the
            # internal schema is the job of the later ontology/mapping
            # layer, analogous to the GDC wrapper (see module docstring).
            "results": results,
        }

    def search(
        self,
        *,
        accession: Optional[str] = None,
        organism: Optional[StrOrList] = None,
        entry_type: Optional[str] = "gse",
        db: str = GEO_DB,
        size: int = 20,
        from_: int = 0,
    ) -> dict:
        """Komfort-Funktion analog zu `GDCWrapper.search()`: baut einen
        Suchterm aus vereinfachten Parametern (Accession, Organismus,
        Eintragstyp) und ruft `query()` auf. Standardwert `entry_type="gse"`
        (Series) als sinnvollster Default für Serien-Metadaten, analog zu
        `GDCWrapper.search()`s Standard `access="open"`.

        Beispiel: search(organism="Homo sapiens", entry_type="gse")

        English: Convenience function analogous to `GDCWrapper.search()`:
        builds a search term from simplified parameters (accession,
        organism, entry type) and calls `query()`. Default
        `entry_type="gse"` (series) as the most sensible default for series
        metadata, analogous to `GDCWrapper.search()`'s default
        `access="open"`.

        Example: search(organism="Homo sapiens", entry_type="gse")
        """
        term = build_search_term(accession=accession, organism=organism, entry_type=entry_type)
        return self.query(term=term, db=db, size=size, from_=from_)

    def get_schema(self, db: str = GEO_DB) -> list[str]:
        """Ruft `einfo` für eine Entrez-Datenbank ab und liefert die
        verfügbaren Such-Feld-Tags sortiert als Liste (z. B. "ACCN", "ETYP",
        "ORGN").

        Analog zu `GDCWrapper.get_schema()` (dort `_mapping`): Diese
        Feldliste ist die Grundlage, gegen die künftige Feld-Mappings
        (GEO-Feld-Tag -> internes DataBridge-Schema/Ontologie-Begriff)
        definiert werden.

        English: Fetches `einfo` for an Entrez database and returns the
        available search field tags sorted as a list (e.g. "ACCN", "ETYP",
        "ORGN").

        Analogous to `GDCWrapper.get_schema()` (`_mapping` there): this
        field list is the basis against which future field mappings (GEO
        field tag -> internal DataBridge schema/ontology term) are defined.
        """
        params = self._base_params({"db": db, "retmode": "json"})
        response = self.session.get(f"{self.base_url}/einfo.fcgi", params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        # `dbinfo` ist laut NCBI-Antwort eine Liste (auch bei genau einer
        # angefragten Datenbank), keine einzelne Objekt-Struktur.
        # EN: Per the NCBI response, `dbinfo` is a list (even for exactly
        # one requested database), not a single object structure.
        dbinfo_list = payload.get("einforesult", {}).get("dbinfo", [])
        fields = dbinfo_list[0].get("fieldlist", []) if dbinfo_list else []
        return sorted(field["name"] for field in fields if "name" in field)

    # ------------------------------------------------------------------
    # Bulk-Tier
    # ------------------------------------------------------------------

    def get_ftp_link(self, accession: str) -> Optional[str]:
        """Liefert den FTP-Verzeichnislink für eine GEO-Accession (Series-Matrix-
        und Supplementary-Dateien), aus dem `ftplink`-Feld des
        `esummary`-DocumentSummary.

        GEO hat keinen eigenständigen Manifest-Endpunkt wie GDC
        (`/files?return_type=manifest`); stattdessen liefert `esummary` das
        FTP-Zielverzeichnis direkt mit. Diese Methode kapselt den dafür
        nötigen Umweg über eine Ein-Treffer-Suche nach der Accession.

        English: Returns the FTP directory link for a GEO accession
        (series-matrix and supplementary files), from the `ftplink` field of
        the `esummary` DocumentSummary.

        GEO has no standalone manifest endpoint like GDC
        (`/files?return_type=manifest`); instead, `esummary` delivers the
        FTP target directory directly. This method encapsulates the
        necessary detour via a single-hit search for the accession.
        """
        result = self.search(accession=accession, entry_type=None, size=1)
        hits = result["results"]
        if not hits:
            return None
        return hits[0].get("ftplink") or None

    def download_supplementary_files(
        self,
        accession: str,
        output_dir: str,
        *,
        subdir: str = "suppl",
        filenames: Optional[list[str]] = None,
    ) -> dict:
        """Lädt Dateien aus einem GEO-Series-FTP-Verzeichnis direkt per HTTP
        herunter.

        Anders als beim GDC-Wrapper (`download_via_gdc_client`, externes
        Tool `gdc-client` per Subprocess) gibt es für GEO kein
        vergleichbares externes Bulk-Download-Tool — die von `esummary`
        gelieferte `ftplink`-Adresse ist ein regulärer, auch per HTTPS
        abrufbarer Verzeichnispfad.

        Das `ftplink`-Basisverzeichnis selbst enthält (live gegen
        `ftp.ncbi.nlm.nih.gov` verifiziert) keine Dateien, sondern
        Unterordner — `matrix/` (Series-Matrix), `miniml/`, `soft/` und
        `suppl/` (die eigentlichen Supplementary-Dateien, z. B. Rohdaten als
        `.tar`/`.txt.gz`). `subdir` wählt diesen Unterordner aus, Standard
        `"suppl"`.

        Ohne `filenames` wird das Unterverzeichnis als HTML-Listing
        abgerufen und die enthaltenen Dateinamen per einfacher
        Link-Erkennung extrahiert (keine zusätzliche HTML-Parser-Abhängigkeit
        — `wrappers/pyproject.toml` listet bewusst nur `requests`). Absolute
        Links (z. B. der NCBI-Footer-Link) und der Parent-Directory-Eintrag
        werden dabei ausgeschlossen.

        Rohdaten gehören konzeptionell in den Tier-3-Cache (`self.cache.raw`,
        siehe cache.py) und sollten nach Verarbeitung via `purge()` wieder
        entfernt werden — wie im GDC-Wrapper nur als Hinweis, der eigentliche
        Zielpfad wird vom Aufrufer vorgegeben.

        English: Downloads files from a GEO series FTP directory directly
        via HTTP.

        Unlike the GDC wrapper (`download_via_gdc_client`, external
        `gdc-client` tool via subprocess), there is no comparable external
        bulk-download tool for GEO — the `ftplink` address delivered by
        `esummary` is a regular directory path also fetchable via HTTPS.

        The `ftplink` base directory itself contains (verified live against
        `ftp.ncbi.nlm.nih.gov`) no files but subfolders — `matrix/`
        (series matrix), `miniml/`, `soft/` and `suppl/` (the actual
        supplementary files, e.g. raw data as `.tar`/`.txt.gz`). `subdir`
        selects this subfolder, default `"suppl"`.

        Without `filenames`, the subdirectory is fetched as an HTML listing
        and the contained file names are extracted via simple link detection
        (no additional HTML-parser dependency — `wrappers/pyproject.toml`
        deliberately lists only `requests`). Absolute links (e.g. the NCBI
        footer link) and the parent-directory entry are excluded from this.

        Raw data conceptually belongs in the tier-3 cache (`self.cache.raw`,
        see cache.py) and should be removed again after processing via
        `purge()` — as in the GDC wrapper, only a hint here, the actual
        target path is supplied by the caller.
        """
        ftp_link = self.get_ftp_link(accession)
        if not ftp_link:
            return {"status": "not_found", "accession": accession}

        root = ftp_link.replace("ftp://", "https://", 1) if ftp_link.startswith("ftp://") else ftp_link
        if not root.endswith("/"):
            root += "/"
        base = f"{root}{subdir}/" if subdir else root

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        names = filenames
        if names is None:
            listing = self.session.get(base, timeout=self.timeout)
            listing.raise_for_status()
            hrefs = re.findall(r'href="([^"]+)"', listing.text)
            names = sorted(
                href for href in hrefs
                if not href.startswith(("http://", "https://", "/")) and not href.endswith("/")
            )

        downloaded: list[str] = []
        for name in names:
            response = self.session.get(base + name, timeout=self.timeout)
            response.raise_for_status()
            (out_dir / name).write_bytes(response.content)
            downloaded.append(name)

        return {"status": "completed", "accession": accession, "source_dir": base, "files": downloaded}

    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine GEO-Antwort in das Zielformat anndata/.h5ad.

        Bewusst nicht Teil dieses Wrappers (siehe Modul-Docstring) — der
        Wrapper liefert strukturierte Metadaten/Rohdaten-Referenzen, die
        Transformation nach anndata ist ein separater Mediator-seitiger
        Schritt.

        English: Converts a GEO response into the target format anndata/.h5ad.

        Deliberately not part of this wrapper (see module docstring) — the
        wrapper delivers structured metadata/raw-data references, the
        transformation to anndata is a separate mediator-side step.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
