"""
Wrapper für die GDC (Genomic Data Commons) Developer API — Testfall TCGA.

Im Sinne des Mediator-Wrapper-Musters kapselt dieses Modul den gesamten
Zugriff auf eine konkrete Datenquelle (hier: GDC-REST-API) und liefert Daten
in einer vom Mediator erwarteten, normalisierten Zwischenform. Die
Transformation nach anndata/.h5ad ist bewusst NICHT Teil dieses Wrappers —
das ist ein separater, späterer Schritt auf Mediator-Seite.

Zwei-Tier-Zugriffsmuster laut GDC-Dokumentation (https://api.gdc.cancer.gov):
  - Metadaten-Tier (`query`, `search`, `get_schema`): paginierbare
    JSON-Endpunkte (`/projects`, `/cases`, `/files`, `/annotations`), für
    Open-Access-Daten ohne Auth-Token nutzbar.
  - Bulk-Tier (`build_manifest`, `download_via_gdc_client`): Manifest-
    Erzeugung über `/files?return_type=manifest` + Übergabe an das externe
    Tool `gdc-client` für den eigentlichen Datei-Download.

ONTOLOGIE-/MAPPING-SCHICHT (spätere Ausbaustufe, Entscheidungsliste
Feld 5/17): `get_schema()` liefert die Rohfeldnamen der GDC-API. Diese Liste
ist die Grundlage, gegen die künftige Feld-Mappings (GDC-Feldname -> internes
DataBridge-Schema/Ontologie-Begriff) definiert werden. `query`/`search`
geben Ergebnisse aktuell noch mit den GDC-Originalfeldnamen zurück
(`results`) — die Übersetzung in ein einheitliches internes Schema ist die
Stelle, an der eine Mapping-Tabelle oder Ontologie-Anbindung andocken würde.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import requests

from .cache import WrapperCache

DEFAULT_TIMEOUT = 30

# Metadaten-Endpunkte laut GDC-API-Dokumentation.
METADATA_ENDPOINTS = ("projects", "cases", "files", "annotations")

StrOrList = Union[str, Iterable[str]]


def build_filters(
    *,
    project_id: Optional[StrOrList] = None,
    experimental_strategy: Optional[StrOrList] = None,
    data_type: Optional[StrOrList] = None,
    access: Optional[StrOrList] = "open",
    extra: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Baut einen GDC-`filters`-JSON-Query aus vereinfachten Suchparametern.

    Deckt bewusst nur die für den Prototyp benötigten Operatoren ab
    (`and` + `in`) — nicht alle GDC-Operatoren (`>=`, `range` etc.). Weitere
    Bedingungen lassen sich über `extra` (Liste roher Filter-Fragmente)
    ergänzen, ohne diese Funktion zu ändern.

    Beispiel (Testfall TCGA-BRCA / RNA-Seq / open):
        build_filters(project_id="TCGA-BRCA", experimental_strategy="RNA-Seq")

    `data_type` filtert auf `files.data_type` (z. B. "Gene Expression
    Quantification" / "miRNA Expression Quantification") — Grundlage für
    `build_expression_filters` (siehe dort, HANDOFF Teil 3/3a).
    """
    content: list[dict] = []

    def _in(field: str, value: StrOrList) -> None:
        values = [value] if isinstance(value, str) else list(value)
        content.append({"op": "in", "content": {"field": field, "value": values}})

    if project_id:
        _in("cases.project.project_id", project_id)
    if experimental_strategy:
        _in("files.experimental_strategy", experimental_strategy)
    if data_type:
        _in("files.data_type", data_type)
    if access:
        _in("files.access", access)
    if extra:
        content.extend(extra)

    if not content:
        return None
    if len(content) == 1:
        return content[0]
    return {"op": "and", "content": content}


# ----------------------------------------------------------------------
# Expressionsdaten (HANDOFF Teil 3/3a, wissensnetz/HANDOFF_anndata.md):
# RNA-Seq-Gene-Counts bzw. miRNA-Seq-Quantifizierung je Probe. Der Wrapper
# beschafft nur die Rohdateien + Proben/Case-Zuordnung — der Zusammenbau zur
# anndata-Matrix (`X`/`obs`/`var`) ist bewusst Mediator-Aufgabe (siehe
# `to_anndata` unten sowie `mediator/app/semantic/expression.py`).
# ----------------------------------------------------------------------

# assay -> GDC-Filterwerte (`files.data_type` / `files.experimental_strategy`).
EXPRESSION_ASSAYS: dict[str, dict[str, str]] = {
    "rna_seq": {
        "data_type": "Gene Expression Quantification",
        "experimental_strategy": "RNA-Seq",
    },
    "mirna_seq": {
        "data_type": "miRNA Expression Quantification",
        "experimental_strategy": "miRNA-Seq",
    },
}

# assay -> Spaltennamen, die `expression.parse_gdc_quantification_file`
# (Mediator-Seite) für diesen Dateityp erwartet — Teil der "Form, die der
# Mediator zu einer Matrix zusammenbauen kann" (HANDOFF_anndata.md, 3a).
EXPRESSION_QUANTIFICATION_COLUMNS: dict[str, dict[str, Optional[str]]] = {
    "rna_seq": {"id_column": "gene_id", "value_column": "tpm_unstranded", "label_column": "gene_name"},
    "mirna_seq": {"id_column": "miRNA_ID", "value_column": "reads_per_million_miRNA_mapped", "label_column": None},
}

# Felder, die für die Proben/Case-Zuordnung nötig sind (siehe
# `extract_sample_case_rows`); zusätzliche Felder können darüber hinaus
# angefragt werden.
EXPRESSION_FILE_FIELDS: list[str] = [
    "file_id",
    "file_name",
    "data_type",
    "experimental_strategy",
    "cases.submitter_id",
    "cases.samples.sample_id",
    "cases.samples.sample_type",
]


def build_expression_filters(
    *,
    assay: str,
    project_id: Optional[StrOrList] = None,
    access: Optional[StrOrList] = "open",
    extra: Optional[list[dict]] = None,
) -> dict:
    """`build_filters`-Variante, fest auf einen Expressions-Assay eingeschränkt.

    `assay`: einer von `EXPRESSION_ASSAYS` (`"rna_seq"` / `"mirna_seq"`).
    """
    if assay not in EXPRESSION_ASSAYS:
        raise ValueError(f"Unbekannter Assay: {assay!r} (erwartet: {tuple(EXPRESSION_ASSAYS)})")
    assay_filter = EXPRESSION_ASSAYS[assay]
    filters = build_filters(
        project_id=project_id,
        experimental_strategy=assay_filter["experimental_strategy"],
        data_type=assay_filter["data_type"],
        access=access,
        extra=extra,
    )
    assert filters is not None  # data_type ist immer gesetzt -> content nie leer
    return filters


def extract_sample_case_rows(hits: list[dict]) -> list[dict[str, Optional[str]]]:
    """Flacht GDC-`files`-Treffer (mit `cases.submitter_id` +
    `cases.samples.sample_id`/`sample_type`) zu einer Zeile je
    (Datei, Probe)-Paar ab — die "Proben↔Case-Zuordnung", die der Mediator
    laut HANDOFF_anndata.md (Abschnitt 3a/3b) vom Wrapper erwartet.

    Ein Treffer ohne `cases`/`samples` (unerwartet für TCGA-Quantifizierungs-
    dateien, aber keine GDC-Garantie) liefert keine Zeile statt eines Fehlers.
    """
    rows: list[dict[str, Optional[str]]] = []
    for hit in hits:
        file_id = hit.get("file_id")
        file_name = hit.get("file_name")
        for case in hit.get("cases") or []:
            submitter_id = case.get("submitter_id")
            for sample in case.get("samples") or []:
                rows.append(
                    {
                        "file_id": file_id,
                        "file_name": file_name,
                        "submitter_id": submitter_id,
                        "sample_id": sample.get("sample_id"),
                        "sample_type": sample.get("sample_type"),
                    }
                )
    return rows


class GDCWrapper:
    """Kapselt den Zugriff auf die GDC Developer API für den Mediator.

    Basis-URL laut GDC-Dokumentation: https://api.gdc.cancer.gov
    (konfigurierbar über Umgebungsvariable GDC_API_BASE_URL, siehe
    .env.example — nach demselben Muster könnten spätere Wrapper für
    GEO/ENA ihre jeweilige Basis-URL konfigurierbar halten).
    """

    def __init__(
        self,
        base_url: str,
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
        endpoint: str,
        *,
        filters: Optional[dict] = None,
        fields: Optional[list[str]] = None,
        size: int = 20,
        from_: int = 0,
        sort: Optional[str] = None,
    ) -> dict:
        """Führt eine paginierte Suche gegen einen Metadaten-Endpunkt aus.

        `endpoint`: einer von `projects`, `cases`, `files`, `annotations`.
        Pagination folgt dem GDC-Muster (`from`/`size`); die Antwort enthält
        die von GDC gelieferten Pagination-Metadaten unverändert.

        Die Query-Spezifikation selbst wird als Tier-1-Cache-Eintrag
        ("Recipe") abgelegt — Vorbereitung dafür, identische Anfragen
        künftig wiederzuerkennen, statt sie erneut gegen GDC auszuführen.
        """
        if endpoint not in METADATA_ENDPOINTS:
            raise ValueError(f"Unbekannter Metadaten-Endpunkt: {endpoint!r} (erwartet: {METADATA_ENDPOINTS})")

        recipe = {
            "endpoint": endpoint,
            "filters": filters,
            "fields": fields,
            "size": size,
            "from": from_,
            "sort": sort,
        }
        recipe_key = self.cache.recipes.key_for(recipe)
        self.cache.recipes.set(recipe_key, recipe)

        # POST statt GET: bei umfangreichen Filtern (z. B. `files.file_id`-Listen
        # mit hunderten Werten, wie sie ein Multi-Kohorten-Export erzeugt) wird
        # die GET-Query-String-Länge von GDCs Server abgelehnt (HTTP 414 "Request-
        # URI Too Long", live reproduziert bei ~320 IDs / ~13 KB Filter-JSON). Die
        # GDC-API akzeptiert denselben Parametersatz unverändert auch per
        # POST-Body — damit unabhängig von der Filtergröße robust.
        body: dict[str, Any] = {"from": from_, "size": size, "format": "json"}
        if filters:
            body["filters"] = filters
        if fields:
            body["fields"] = ",".join(fields)
        if sort:
            body["sort"] = sort

        response = self.session.post(f"{self.base_url}/{endpoint}", json=body, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data", {})
        return {
            "source": "gdc",
            "endpoint": endpoint,
            "recipe_key": recipe_key,
            "pagination": data.get("pagination", {}),
            # GDC-Originalfeldnamen unverändert; Übersetzung ins interne
            # Schema ist Aufgabe der späteren Ontologie-/Mapping-Schicht.
            "results": data.get("hits", []),
        }

    def search(
        self,
        endpoint: str = "files",
        *,
        project_id: Optional[StrOrList] = None,
        experimental_strategy: Optional[StrOrList] = None,
        access: Optional[StrOrList] = "open",
        fields: Optional[list[str]] = None,
        size: int = 20,
        from_: int = 0,
    ) -> dict:
        """Komfort-Funktion für den Standard-Testfall: baut Filter aus
        vereinfachten Parametern (Projekt, Experimentstrategie, Access-Level)
        und ruft `query` auf. Standardwert `access="open"`, um
        Controlled-Access-Daten im Prototyp auszuschließen (siehe Kontext:
        Open-Access-Daten benötigen keinen Auth-Token).

        Beispiel: search("files", project_id="TCGA-BRCA", experimental_strategy="RNA-Seq")
        """
        filters = build_filters(
            project_id=project_id,
            experimental_strategy=experimental_strategy,
            access=access,
        )
        return self.query(endpoint, filters=filters, fields=fields, size=size, from_=from_)

    def search_expression_files(
        self,
        *,
        assay: str,
        project_id: Optional[StrOrList] = None,
        access: Optional[StrOrList] = "open",
        fields: Optional[list[str]] = None,
        size: int = 20,
        from_: int = 0,
    ) -> dict:
        """Sucht Expressions-Quantifizierungsdateien (RNA-Seq/miRNA-Seq) inkl.
        Proben/Case-Zuordnung (HANDOFF Teil 3a).

        Ergänzt vom Aufrufer übergebene `fields` immer um
        `EXPRESSION_FILE_FIELDS`, damit `extract_sample_case_rows` auf dem
        Ergebnis (`result["results"]`) funktioniert.
        """
        merged_fields = list(dict.fromkeys(EXPRESSION_FILE_FIELDS + (fields or [])))
        filters = build_expression_filters(assay=assay, project_id=project_id, access=access)
        return self.query("files", filters=filters, fields=merged_fields, size=size, from_=from_)

    def get_schema(self, endpoint: str) -> list[str]:
        """Ruft `_mapping` für einen Endpunkt ab und liefert die verfügbaren
        Feldnamen sortiert als Liste.

        Vorbereitung für die spätere Ontologie-/Mapping-Schicht (siehe
        Modul-Docstring): Diese Feldliste ist die Grundlage, gegen die
        künftige Feld-Mappings definiert werden.
        """
        if endpoint not in METADATA_ENDPOINTS:
            raise ValueError(f"Unbekannter Endpunkt: {endpoint!r} (erwartet: {METADATA_ENDPOINTS})")

        response = self.session.get(f"{self.base_url}/{endpoint}/_mapping", timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return sorted(payload.get("fields", []))

    # ------------------------------------------------------------------
    # Bulk-Tier
    # ------------------------------------------------------------------

    def build_manifest(self, *, filters: Optional[dict] = None, size: int = 10000) -> str:
        """Erzeugt ein Manifest (TSV) für `gdc-client` aus einer Files-Query.

        Die GDC-API hat keinen eigenständigen `/manifest`-Endpunkt; das
        Manifest wird stattdessen über `/files` mit `return_type=manifest`
        erzeugt. Der Rückgabewert ist der rohe Manifest-Text, wie ihn
        `gdc-client` als Eingabedatei erwartet.

        POST statt GET (siehe `query()`): ein Manifest über hunderte
        `file_id`s (z. B. Pancancer-Export) sprengt sonst die GET-Query-
        String-Länge (HTTP 414, live reproduziert).
        """
        body: dict[str, Any] = {"return_type": "manifest", "size": size}
        if filters:
            body["filters"] = filters

        response = self.session.post(f"{self.base_url}/files", json=body, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def download_via_gdc_client(self, manifest_content: str, output_dir: str) -> dict:
        """Platzhalter-Funktion: übergibt ein Manifest an das externe Tool
        `gdc-client` (Subprocess-Aufruf).

        Der eigentliche Bulk-Download (FASTQ/BAM) läuft bewusst
        containerintern separat über `gdc-client` (Wiederaufnahme,
        Parallelisierung und Integritätsprüfung sind dort bereits gelöst),
        nicht über einzelne HTTP-Requests dieses Wrappers. Falls
        `gdc-client` im Container nicht installiert ist, wird das ohne
        Absturz signalisiert (`status="not_run"`).

        Rohdaten gehören konzeptionell in den Tier-3-Cache
        (`self.cache.raw`, siehe cache.py) und sollten nach Verarbeitung via
        `purge()` wieder entfernt werden — hier nur als Hinweis, da der
        eigentliche Download-Zielpfad vom Aufrufer vorgegeben wird.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = out_dir / "manifest.txt"
        manifest_path.write_text(manifest_content, encoding="utf-8")

        command = ["gdc-client", "download", "-m", str(manifest_path), "-d", str(out_dir)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            return {
                "status": "completed" if result.returncode == 0 else "failed",
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {
                "status": "not_run",
                "command": command,
                "hint": "gdc-client ist im Container nicht installiert/im PATH. "
                "Der Bulk-Download läuft containerintern separat über gdc-client.",
            }

    def download_expression_files(
        self,
        *,
        assay: str,
        project_id: Optional[StrOrList] = None,
        output_dir: str,
        access: Optional[StrOrList] = "open",
        size: int = 10000,
    ) -> dict:
        """Beschafft Expressions-Rohdaten für den Mediator (HANDOFF Teil 3a):
        Manifest bauen, über `gdc-client` herunterladen und die
        Proben↔Case-Zuordnung + lokalen Dateipfade je Probe liefern — in der
        Form, die `mediator/app/semantic/expression.assemble_matrix`/
        `build_obs` direkt entgegennehmen (`sample_files`/`sample_case_map`/
        `sample_types`).

        Baut bewusst KEIN anndata (siehe `to_anndata`/Modul-Docstring) —
        das bleibt der separate Mediator-Schritt.
        """
        filters = build_expression_filters(assay=assay, project_id=project_id, access=access)
        metadata = self.query("files", filters=filters, fields=EXPRESSION_FILE_FIELDS, size=size)
        rows = extract_sample_case_rows(metadata["results"])

        manifest = self.build_manifest(filters=filters, size=size)
        download = self.download_via_gdc_client(manifest, output_dir)

        sample_case_map: dict[str, str] = {}
        sample_types: dict[str, str] = {}
        sample_files: dict[str, Path] = {}
        out_dir = Path(output_dir)
        for row in rows:
            sample_id, file_id, file_name = row["sample_id"], row["file_id"], row["file_name"]
            if not sample_id or not file_id or not file_name:
                continue
            sample_case_map[sample_id] = row["submitter_id"]
            if row.get("sample_type"):
                sample_types[sample_id] = row["sample_type"]
            if download["status"] == "completed":
                # gdc-client legt jede Datei unter <output_dir>/<file_id>/<file_name> ab.
                local_path = out_dir / file_id / file_name
                if local_path.exists():
                    sample_files[sample_id] = local_path

        return {
            "assay": assay,
            "filters": filters,
            "quantification_columns": EXPRESSION_QUANTIFICATION_COLUMNS[assay],
            "download": download,
            "files": rows,
            "sample_case_map": sample_case_map,
            "sample_types": sample_types,
            "sample_files": sample_files,
        }

    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine GDC-Antwort in das Zielformat anndata/.h5ad.

        Bewusst nicht Teil dieses Wrappers (siehe Modul-Docstring) — der
        Wrapper liefert strukturierte Metadaten/Rohdaten-Referenzen, die
        Transformation nach anndata ist ein separater Mediator-seitiger
        Schritt.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
