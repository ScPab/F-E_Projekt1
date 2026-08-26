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
        """
        params = self._base_params({"db": db, "retmode": "json"})
        response = self.session.get(f"{self.base_url}/einfo.fcgi", params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        # `dbinfo` ist laut NCBI-Antwort eine Liste (auch bei genau einer
        # angefragten Datenbank), keine einzelne Objekt-Struktur.
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
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
