# Cleanup-Log: ungenutzter Code in den Wrappern entfernt

**Datum:** 2026-09-27
**Betrifft:** nur `wrappers/` (`*/client.py`, `*/cache.py`, `ena/README.md`)
**Warum:** Repo-weite Suche (Mediator, Frontend, Scripts, Wissensnetz, Tests)
ergab, dass die unten aufgeführten Methoden von **niemandem im Repo
aufgerufen werden**. Gleiches Vorgehen wie
`mediator/docs/CLEANUP_LOG_unused_endpoints.md`.

**Ausdrücklich NICHT entfernt:** die GDC-Expressions-Funktionen
(`search_expression_files`, `download_expression_files`,
`build_expression_filters`, `extract_sample_case_rows`, `EXPRESSION_*`).
Sie werden zwar aktuell nur von den eigenen Tests genutzt (der Mediator baut
die Logik in `fetch_selection_files` inline nach), sind aber getestete
HANDOFF-Lieferung (Teil 3a) und bleiben für eine spätere Umstellung erhalten.

**Hinweis außerhalb von `wrappers/` (nicht angefasst):**
`mediator/app/semantic/expression.py` erwähnt im Modul-Docstring (Zeile 4
und 33), dass `Wrapper.to_anndata()` bewusst `NotImplementedError` wirft —
die Methode gibt es jetzt nicht mehr, die Aussage "Wrapper bauen kein
anndata" stimmt aber weiterhin.

English: Cleanup log — unused code removed from the wrappers. A repo-wide
search found that the methods below are called by no one. The GDC
expression functions were deliberately kept (tested HANDOFF deliverable).
Each block below is in its original state — copy it back to restore.

## Wie wiederherstellen

Jeder Block unten steht im Originalzustand da — einfach an die genannte
Stelle zurückkopieren. Alternativ den Commit vor diesem Cleanup auschecken:
`git log --oneline -- wrappers/`.

Beim ENA-Wrapper zusätzlich `from pathlib import Path` wieder importieren
und die Abschnittsüberschrift `# Bulk-Tier` vor `get_download_links`
einfügen.

---

## 1. ENA-Bulk-Tier (`wrappers/ena/client.py`)

FASTQ-Download-Adressen je Read-Run suchen und herunterladen. ENA ist in der
Auswahl-Pipeline des Mediators bewusst nicht angebunden; der Mediator nutzt
vom ENA-Wrapper nur `search()` (Zweig `ena` in `POST /transform`).

### `get_download_links()` — `wrappers/ena/client.py`

War direkt nach `get_schema()`, unter der Überschrift `# Bulk-Tier`.

```python
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
```

### `download_fastq_files()` — `wrappers/ena/client.py`

Direkt nach `get_download_links()`.

```python
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
```


Dazu gehörte in `ena/README.md` unter "Noch offen" der Punkt:
*"Kontrollierte (nicht offene) Daten liefern ein leeres `fastq_ftp`-Feld —
`get_download_links()` gibt dafür aktuell nur eine leere Dateiliste zurück,
ohne das explizit als "kontrollierter Zugriff" zu kennzeichnen."*

---

## 2. `to_anndata()`-Platzhalter (alle vier Wrapper)

Warf nur `NotImplementedError`; diente als Hinweis, dass die
anndata-Transformation Mediator-Aufgabe ist. Das steht weiterhin im
Modul-Docstring jedes `client.py`. War jeweils die letzte Methode der
Wrapper-Klasse.

### `to_anndata()` — `wrappers/gdc/client.py`

Letzte Methode der Klasse.

```python
    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine GDC-Antwort in das Zielformat anndata/.h5ad.

        Bewusst nicht Teil dieses Wrappers (siehe Modul-Docstring) — der
        Wrapper liefert strukturierte Metadaten/Rohdaten-Referenzen, die
        Transformation nach anndata ist ein separater Mediator-seitiger
        Schritt.

        English: Converts a GDC response into the target format anndata/.h5ad.

        Deliberately not part of this wrapper (see module docstring) — the
        wrapper delivers structured metadata/raw-data references, the
        transformation to anndata is a separate mediator-side step.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
```

### `to_anndata()` — `wrappers/geo/client.py`

Letzte Methode der Klasse.

```python
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
```

### `to_anndata()` — `wrappers/ena/client.py`

Letzte Methode der Klasse.

```python
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
```

### `to_anndata()` — `wrappers/cbioportal/client.py`

Letzte Methode der Klasse.

```python
    def to_anndata(self, raw_response: object) -> None:
        """Überführt eine cBioPortal-Antwort in das Zielformat anndata/.h5ad.

        Bewusst nicht Teil dieses Wrappers (siehe Modul-Docstring) — der
        Wrapper liefert strukturierte Metadaten-/Profildaten, die
        Transformation nach anndata ist ein separater Mediator-seitiger
        Schritt.

        English: Converts a cBioPortal response into the target format anndata/.h5ad.

        Deliberately not part of this wrapper (see module docstring) — the
        wrapper delivers structured metadata/profile data, the
        transformation to anndata is a separate mediator-side step.
        """
        raise NotImplementedError(
            "Transformation nach anndata ist bewusst kein Teil des Wrappers, "
            "siehe Modul-Docstring."
        )
```


In `gdc/client.py` verwiesen zwei Kommentare auf `to_anndata`
(Abschnitt "Expressionsdaten" und Docstring von `download_expression_files`);
sie verweisen jetzt nur noch auf den Modul-Docstring.

---

## 3. `_FileBackedCache.has()` (alle vier `cache.py`)

Der Mediator prüft Cache-Treffer über `get()` auf `None`. War jeweils direkt
nach `set()`, identisch in allen vier Dateien:

```python
    def has(self, key: str) -> bool:
        return self._path(key).exists()
```

---

## 4. Ungenutzter Import (`wrappers/geo/client.py`)

`from typing import Any, Iterable, Optional, Union` → `Any` entfernt
(von pyflakes als unbenutzt gemeldet, war schon vor diesem Cleanup ungenutzt).
