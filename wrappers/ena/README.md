# Wrapper: ENA (European Nucleotide Archive)

Dritter Wrapper der DataBridge-Architektur (nach `wrappers/gdc`,
`wrappers/geo`). Kapselt den Zugriff auf ENA über die
[EBI Portal API](https://www.ebi.ac.uk/ena/portal/api/) — das europäische
Pendant zu GDC für Rohsequenzdaten (FASTQ) und die zugehörigen Studien-
/Sample-Metadaten.

## Entscheidung: Python-Package statt eigener Container

Wie bei den anderen Wrappern liegt dieser Wrapper **als Python-Package
innerhalb des Mediator-Containers** vor (Unterpaket unter `/wrappers`,
automatisch erfasst durch `wrappers/pyproject.toml`), **nicht** als
separater Docker-Service — Begründung siehe
[ADR-0001](../../docs/adr/0001-wrapper-als-python-package.md) bzw.
[`wrappers/gdc/README.md`](../gdc/README.md).

## Status

Abfrage- und Schema-Introspektionslogik implementiert (`client.py`) und
gegen die echte EBI-API verifiziert (siehe unten):

- `ENAWrapper.query()` / `.search()` — Metadaten-Suche über einen einzelnen
  JSON-Endpunkt (`/search`), sehr ähnlich zum GDC-Wrapper: Suchquery +
  Feldliste + `limit`/`offset`-Pagination (hier `size`/`from_` genannt).
- `build_query()` — baut aus vereinfachten Parametern (Studien-Accession,
  Library-Strategie, Sequenzier-Plattform) einen ENA-Suchquery-String;
  weitere Bedingungen über `extra` (Liste roher Query-Fragmente), analog zu
  `build_filters()` beim GDC-Wrapper.
- `ENAWrapper.get_schema()` — ruft `/returnFields` ab und liefert die
  verfügbaren Feldnamen (`columnId`) je Ergebnistyp; Grundlage für die
  spätere Ontologie-/Mapping-Schicht, analog zum GDC-Wrapper (`_mapping`).
- Kein Bulk-Tier: Die FASTQ-Download-Funktionen (`get_download_links()` /
  `download_fastq_files()`) wurden entfernt, weil ENA nicht an die
  Auswahl-Pipeline angebunden ist und niemand sie aufrief. Originalcode
  zum Wiederherstellen: [`wrappers/CLEANUP_LOG_unused_code.md`](../CLEANUP_LOG_unused_code.md).
- `cache.py` — dieselbe drei-Tier-Cache-Struktur wie bei den anderen
  Wrappern (Recipes / materialisierte anndata-Referenzen / transiente
  Rohdaten), eigenständige Kopie (kein Import aus `wrappers/gdc` oder
  `wrappers/geo`, um die Wrapper unabhängig voneinander zu halten, siehe
  ADR-0001).

Die Transformation nach anndata/.h5ad ist — wie bei den anderen Wrappern —
**nicht** Teil dieses Wrappers.

## Noch offen

- **Noch nicht an den Mediator angebunden**: kein `POST /query`-Äquivalent
  in `mediator/app/main.py`, keine `ENA_API_BASE_URL` in `.env.example`.
  Das ist der nächste Schritt auf Mediator-Seite (Kollege B), analog zur
  bestehenden GDC-Anbindung.
- **Keine echte Gesamttrefferzahl** — anders als GDC (`pagination.total`)
  oder GEO (`esearchresult.count`) liefert die ENA-`/search`-Antwort keine
  Gesamtzahl. `pagination.has_more` in `query()` ist nur eine Heuristik
  (Seite komplett voll → vermutlich weitere Treffer), kein Beweis.
- **`extra`-Query-Fragmente sind ungeprüfter Rohtext** (kein
  Escaping/Validierung) — bewusst analog zur `extra`-Erweiterung von
  `build_filters()` im GDC-Wrapper, dort ebenfalls unvalidiert.
- Kein Rate-Limiting/Retry-Handling — bei sehr vielen Requests
  hintereinander ungetestet.

## Verifiziert gegen die echte API

```bash
python wrappers/ena/scripts/check_connection.py
```

prüft nacheinander Metadaten-Suche (Studie `PRJEB1234`) und
Schema-Introspektion (`returnFields`, Ergebnistyp `read_run`).
