# Wrapper: GDC (Genomic Data Commons)

Erster Wrapper der DataBridge-Architektur. Kapselt den Zugriff auf die
[GDC Developer API](https://api.gdc.cancer.gov) (Testfall: TCGA-Daten).

## Entscheidung: Python-Package statt eigener Container

Der Wrapper liegt **als Python-Package innerhalb des Mediator-Containers**
vor (installiert aus `/wrappers`), **nicht** als separater Docker-Service.

**Begründung:** In dieser frühen Ausbaustufe ruft der Mediator den Wrapper
synchron als Bibliotheksfunktion auf – ein eigener Container würde nur
zusätzliche Netzwerk-/Serialisierungs-Overhead und Orchestrierungsaufwand
bedeuten, ohne aktuellen Nutzen (kein unabhängiges Skalieren, kein anderer
Technologie-Stack nötig). Die Trennung nach dem Mediator-Wrapper-Muster wird
stattdessen auf Code-Ebene durchgesetzt: Jede Datenquelle bekommt ein
eigenes, unabhängiges Unterpaket unter `/wrappers`. Sollte ein Wrapper später
eigene Skalierungs- oder Laufzeitanforderungen bekommen (z. B. lang laufende
Abfragen, andere Sprache), kann er ohne Änderung am Mediator-Interface in
einen eigenen Service ausgelagert werden.

Siehe [`/docs/adr/0001-wrapper-als-python-package.md`](../../docs/adr/0001-wrapper-als-python-package.md).

## Status

Abfrage- und Schema-Introspektionslogik implementiert (`client.py`):

- `GDCWrapper.query()` / `.search()` — paginierte Metadaten-Suche gegen
  `/cases`, `/files`, `/projects`, `/annotations` mit vereinfachten
  Suchparametern (Projekt-ID, Experimentstrategie, Access-Level).
- `build_filters()` — baut daraus einen validen GDC-`filters`-JSON-Query
  (Operatoren `and`/`in`; weitere Bedingungen über `extra`).
- `GDCWrapper.get_schema()` — ruft `_mapping` ab und liefert verfügbare
  Feldnamen; Grundlage für die spätere Ontologie-/Mapping-Schicht.
- `GDCWrapper.build_manifest()` — erzeugt ein Manifest (`/files?return_type=manifest`)
  für `gdc-client`.
- `GDCWrapper.download_via_gdc_client()` — Platzhalter, der ein Manifest an
  das externe Tool `gdc-client` übergibt (Subprocess); der eigentliche
  Bulk-Download läuft containerintern separat.
- `cache.py` — Datei-basiertes Grundgerüst für die drei Cache-Tiers
  (Recipes / materialisierte anndata-Referenzen / transiente Rohdaten),
  Verzeichnis über `DATABRIDGE_CACHE_DIR` konfigurierbar.

Die Transformation nach anndata/.h5ad ist weiterhin **nicht** Teil dieses
Wrappers (separater, späterer Schritt).

Erreichbar über die Mediator-REST-API (`POST /query`, `GET
/schema/{endpoint}`, `POST /manifest`) — siehe Root-README für
Beispielaufrufe.
