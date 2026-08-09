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

Reines Grundgerüst (`client.py`), noch ohne Abfrage- oder Transformationslogik.
