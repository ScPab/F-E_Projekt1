# ADR-0001: GDC-Wrapper als Python-Package statt eigener Container

**Status:** Angenommen
**Datum:** 2026-08-09

## Kontext

Die Architektur folgt dem Mediator-Wrapper-Muster: Der Mediator nimmt
Anfragen entgegen, Wrapper-Module kapseln je eine externe Datenquelle
(erste Quelle: GDC Developer API). Es war zu klären, ob jeder Wrapper als
eigener Docker-Container/Service läuft oder als Python-Package innerhalb
des Mediator-Containers eingebunden wird.

## Entscheidung

Der GDC-Wrapper (und vorerst alle weiteren Wrapper) liegt als eigenständiges
Python-Unterpaket unter `/wrappers/gdc` und wird beim Bau des
Mediator-Containers installiert (siehe `mediator/environment.yml`,
`mediator/Dockerfile`). Es gibt keinen separaten `wrapper-gdc`-Service in
`docker-compose.yml`.

## Betrachtete Alternativen

- **Eigener Container pro Wrapper** – saubere Prozess-/Deployment-Trennung,
  unabhängige Skalierung, aber: zusätzlicher Netzwerk-Overhead für synchrone
  Anfragen, mehr Orchestrierungs- und Betriebsaufwand, ohne dass aktuell ein
  Bedarf für unabhängiges Skalieren oder einen anderen Technologie-Stack
  besteht.
- **Python-Package innerhalb des Mediators (gewählt)** – geringerer
  Overhead, einfachere lokale Entwicklung, Trennung bleibt auf Code-Ebene
  (eigenes Unterpaket je Datenquelle) bestehen.

## Konsequenzen

- Neue Datenquellen werden als neues Unterpaket unter `/wrappers` ergänzt,
  ohne dass sich an der Compose-Struktur etwas ändert.
- Sollte ein Wrapper künftig eigene Laufzeit-/Skalierungsanforderungen
  bekommen, kann er ohne Bruch am Mediator-Interface in einen eigenen
  Service ausgelagert werden (Interface-Grenze ist bereits durch das
  Package definiert).
- Alle Wrapper teilen sich aktuell die Conda-Umgebung des Mediators
  (`environment.yml`); bei sehr unterschiedlichen Abhängigkeiten je Quelle
  müsste dies überdacht werden.
