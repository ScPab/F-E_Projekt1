# Wrapper: GEO (Gene Expression Omnibus)

Zweiter Wrapper der DataBridge-Architektur (nach `wrappers/gdc`). Kapselt den
Zugriff auf GEO über die
[NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/) (Datenbank
`gds` — Series/DataSets/Samples/Platforms).

## Entscheidung: Python-Package statt eigener Container

Wie beim GDC-Wrapper liegt dieser Wrapper **als Python-Package innerhalb des
Mediator-Containers** vor (Unterpaket unter `/wrappers`, automatisch erfasst
durch `wrappers/pyproject.toml`), **nicht** als separater Docker-Service —
Begründung siehe [ADR-0001](../../docs/adr/0001-wrapper-als-python-package.md)
bzw. [`wrappers/gdc/README.md`](../gdc/README.md).

## Status

Abfrage- und Schema-Introspektionslogik implementiert (`client.py`) und
gegen die echte NCBI-API verifiziert (siehe unten):

- `GEOWrapper.query()` / `.search()` — zweistufige Metadaten-Suche
  (`esearch` liefert UIDs, `esummary` liefert die DocumentSummaries dazu),
  paginiert über `retstart`/`retmax` (analog `from`/`size` beim
  GDC-Wrapper). GDC hat dafür einen einzelnen JSON-Endpunkt; GEO braucht
  zwei Requests, die hier gebündelt werden.
- `build_search_term()` — baut aus vereinfachten Parametern (Accession,
  Organismus, Eintragstyp `gse`/`gds`/`gpl`/`gsm`) einen NCBI-Entrez-Suchterm;
  weitere Bedingungen über `extra` (Liste roher Term-Fragmente), analog zu
  `build_filters()` beim GDC-Wrapper.
- `GEOWrapper.get_schema()` — ruft `einfo` für die Datenbank `gds` ab und
  liefert die verfügbaren Such-Feld-Tags (z. B. `ORGN`, `ACCN`, `ETYP`);
  Grundlage für die spätere Ontologie-/Mapping-Schicht, analog zum
  GDC-Wrapper (`_mapping`).
- `GEOWrapper.get_ftp_link()` / `.download_supplementary_files()` —
  Bulk-Tier: GEO hat keinen Manifest-Endpunkt und kein externes
  Download-Tool wie `gdc-client`; stattdessen liefert `esummary` bereits
  einen direkten FTP-Verzeichnislink (`ftplink`), der per HTTP-GET
  abrufbar ist.
- `cache.py` — dieselbe drei-Tier-Cache-Struktur wie beim GDC-Wrapper
  (Recipes / materialisierte anndata-Referenzen / transiente Rohdaten),
  eigenständige Kopie (kein Import aus `wrappers/gdc`, um die Wrapper
  unabhängig voneinander zu halten, siehe ADR-0001).

Die Transformation nach anndata/.h5ad ist — wie beim GDC-Wrapper — **nicht**
Teil dieses Wrappers.

## Noch offen

- **Noch nicht an den Mediator angebunden**: kein `POST /query`-Äquivalent
  in `mediator/app/main.py`, keine `GEO_API_BASE_URL` in `.env.example`.
  Das ist der nächste Schritt auf Mediator-Seite (Kollege B), analog zur
  bestehenden GDC-Anbindung.
- **Suchterm-Fragmente in `extra` sind ungeprüfter Rohtext** (kein
  Escaping/Validierung) — bewusst analog zur `extra`-Erweiterung von
  `build_filters()` im GDC-Wrapper, dort ebenfalls unvalidiert.
- **`download_supplementary_files()` ohne `filenames`** parst die
  HTML-Verzeichnisliste mit einer einfachen Regex statt eines echten
  HTML-Parsers (keine zusätzliche Abhängigkeit neben `requests`, siehe
  `wrappers/pyproject.toml`) — bei einer Änderung des NCBI-Listing-Formats
  müsste das angepasst werden.
- Kein NCBI-`api_key` standardmäßig gesetzt (ohne Key: max. 3
  Anfragen/Sekunde laut NCBI-Doku) — bei Bedarf über
  `GEOWrapper(..., api_key=...)` bzw. Umgebungsvariable `GEO_API_KEY`.

## Verifiziert gegen die echte API

```bash
python wrappers/geo/scripts/check_connection.py
```

prüft nacheinander Metadaten-Suche (`Homo sapiens`, Series) und
Schema-Introspektion (`einfo`, Datenbank `gds`).
