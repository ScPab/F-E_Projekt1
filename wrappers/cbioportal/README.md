# Wrapper: cBioPortal

Vierter Wrapper der DataBridge-Architektur (nach `wrappers/gdc`,
`wrappers/geo`, `wrappers/ena`). Kapselt den Zugriff auf
[cBioPortal](https://www.cbioportal.org/api) — bereits aufbereitete
klinische und genomische Krebsdaten aus vielen Studien (u. a. auch
TCGA/GDC-Daten in kuratierter Form), beliebt als Grundlage für
Visualisierung.

## Entscheidung: Python-Package statt eigener Container

Wie bei den anderen Wrappern liegt dieser Wrapper **als Python-Package
innerhalb des Mediator-Containers** vor (Unterpaket unter `/wrappers`,
automatisch erfasst durch `wrappers/pyproject.toml`), **nicht** als
separater Docker-Service — Begründung siehe
[ADR-0001](../../docs/adr/0001-wrapper-als-python-package.md) bzw.
[`wrappers/gdc/README.md`](../gdc/README.md).

## Struktureller Unterschied zu GDC/GEO/ENA

Die anderen drei Wrapper haben einen einzelnen generischen Such-Endpunkt
(`query()`/`search()`). cBioPortal hat stattdessen ein
**Ressourcen-pro-Endpunkt-Design** — deshalb hat dieser Wrapper bewusst
**keine** `query()`/`search()`-Methoden, sondern eine Methode je
Ressourcentyp (`list_studies`, `get_clinical_data`, ...). Das Schema ist
außerdem **studienspezifisch** (klinische Attribute unterscheiden sich je
Studie), nicht global wie bei GDC/GEO/ENA — `get_schema()` braucht deshalb
eine `study_id`.

## Status

Implementiert (`client.py`) und gegen die echte API verifiziert (siehe
unten):

- `CBioPortalWrapper.list_studies()` — Studien auflisten, optional
  serverseitig gefiltert über `keyword` (z. B. `keyword="breast"`).
  Pagination seitenbasiert (`pageSize`/`pageNumber`), hier als
  `size`/`from_` benannt wie bei den anderen Wrappern (`from_` muss
  Vielfaches von `size` sein, siehe `_page_number`).
- `CBioPortalWrapper.get_schema(study_id)` — klinische Attribute einer
  Studie (`clinical-attributes`), analog zu `GDCWrapper.get_schema()`
  (dort `_mapping`), aber studienspezifisch statt global.
- `CBioPortalWrapper.get_clinical_data(study_id, ...)` — klinische
  Datenpunkte (Attribut/Wert je Patient oder Sample) einer Studie.
- `CBioPortalWrapper.list_molecular_profiles()` /
  `.list_sample_lists()` / `.get_molecular_data()` — Bulk-Tier-Äquivalent:
  genomische Profildaten (Mutationen, Kopienzahl-Varianten, Expression) für
  eine Gen-/Sample-Auswahl, über den POST-Endpunkt
  `/molecular-profiles/{id}/molecular-data/fetch`. Anders als bei
  GDC/GEO/ENA liefert cBioPortal keine rohen Sequenzdateien — das ist
  bewusst außerhalb des Scopes dieses Wrappers.
- `cache.py` — dieselbe drei-Tier-Cache-Struktur wie bei den anderen
  Wrappern, eigenständige Kopie (kein Import aus den anderen Wrapper-
  Paketen, siehe ADR-0001). Tier 3 (Rohdaten) bleibt hier praktisch
  ungenutzt, da cBioPortal selbst keine Rohdaten liefert.

Die Transformation nach anndata/.h5ad ist — wie bei den anderen Wrappern —
**nicht** Teil dieses Wrappers.

## Noch offen

- **Noch nicht an den Mediator angebunden**: keine REST-Endpunkte in
  `mediator/app/main.py`, keine `CBIOPORTAL_API_BASE_URL` in
  `.env.example`. Nächster Schritt auf Mediator-Seite (Kollege B).
- **`get_clinical_data()` filtert nicht nach einzelnen Attributen** — nur
  der GET-Endpunkt ist implementiert (liefert alle Attribute der Studie);
  der separate `POST .../clinical-data/fetch`-Endpunkt für eine gezielte
  Attribut-/Patienten-Auswahl ist bewusst nicht umgesetzt (nicht live
  verifiziert, um nichts Ungetestetes zu committen).
- **Keine echte Gesamttrefferzahl** — wie bei ENA liefert die API keine
  Gesamtzahl im Response; `pagination.has_more` ist nur eine Heuristik.
- **`from_` muss Vielfaches von `size` sein** (seitenbasierte Pagination) —
  anders als bei den anderen drei Wrappern, die einen freien Offset
  erlauben. Bei falscher Nutzung wirft `_page_number` einen `ValueError`.
- Kein Rate-Limiting/Retry-Handling.

## Verifiziert gegen die echte API

```bash
python wrappers/cbioportal/scripts/check_connection.py
```

prüft nacheinander Studien-Suche (Stichwort `breast`), Schema-Introspektion
(klinische Attribute der Studie `acc_tcga`) und einen Molekulardaten-Abruf
(Kopienzahl-Varianten für zwei Beispielgene).
