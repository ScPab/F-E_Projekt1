# DataBridge

DataBridge beschafft Forschungsdaten aus öffentlichen Repositorien automatisch,
beschreibt sie semantisch und bereitet sie für Visualisierungswerkzeuge auf.
Anwendungsfall ist die Onkologie und Genetik, Testfall sind TCGA-Daten über die
GDC Developer API.

Studienprojekt FuE-Projekt-1 im SS 2026 an der Hochschule Karlsruhe, in
Kooperation mit der Universität Oviedo (Projekt-Code `26ss_CB_DataBridge`).
Die Aufgabenstellung liegt unter `Orga/`.

## Die Idee in fünf Sätzen

Datenbestände wie TCGA sind zu groß, um sie vollständig zu laden und danach zu
filtern. Deshalb steht am Anfang eine Auswahl: der Forscher stellt in der
Oberfläche zusammen, was ihn interessiert, und genau diese Auswahl ist der
Auftrag an das System. Der Mediator holt dazu die Daten über den passenden
Wrapper, übersetzt sie und verzweigt das Ergebnis in zwei Richtungen: die
Bedeutung geht als RDF/OWL in das Wissensnetz, die Messwerte gehen als
anndata-Datei (`.h5ad`) an die Visualisierung. Der Graph startet leer und wächst
mit den Aufrufen, statt einmal global vorgeladen zu werden. Umgekehrt können
Erkenntnisse aus der Visualisierung als Rückkanal wieder im Graphen landen.

## Wie die Teile zusammenspielen

```
  Explorer (frontend/)          Auswahl zusammenstellen, Ergebnis ansehen
          |  HTTP
          v
  Mediator (mediator/)          Auftrag annehmen, übersetzen, verzweigen
          |              \
          |  Wrapper       \  anndata (.h5ad)
          v                 \
  Quellen (wrappers/)         ---> Visualisierung
  gdc, geo, ena, cbioportal
          |  RDF/OWL
          v
  Wissensnetz (wissensnetz/)    Ontologie, Anreicherung, Rückkanal
          |  SPARQL
          v
  Triple-Store (Fuseki)         Container aus docker-compose.yml
```

Der Mediator und der Triple-Store laufen als Container, die Oberfläche läuft als
normales Programm auf dem Rechner. Die Komponenten sprechen nur über HTTP und
SPARQL miteinander, nicht über gemeinsame Dateien oder Importe.

## Schnellstart

Vorausgesetzt werden Docker Desktop, Miniconda mit der Umgebung `F+E` und das
Repository unter `C:\Dev\F+E\F-E_Projekt1`.

```powershell
conda activate F+E
cd C:\Dev\F+E\F-E_Projekt1
.\start_all.ps1
```

Das Skript prüft die Abhängigkeiten, startet Docker, Fuseki und den Mediator,
initialisiert das Wissensnetz, lädt einen Demo-Scope und öffnet den DataBridge
Explorer. Danach beendet es sich, die Dienste laufen weiter.

Erreichbar sind anschließend:

| Dienst | Adresse | Hinweis |
| --- | --- | --- |
| Mediator (FastAPI) | http://localhost:8000 | `/health`, interaktive API unter `/docs` |
| Triple-Store (Fuseki) | http://localhost:3030 | Login `admin` / `admin` |
| DataBridge Explorer | eigenes Fenster | PySide6, kein Browser-Tab |

Beenden mit `.\stop_all.ps1`. Alle Befehle im Einzelnen, auch die Wege ohne
Startskript, stehen in [`RUNBOOK.md`](RUNBOOK.md).

Zwei Stolpersteine, die oft Zeit kosten:

- Ohne aktive Conda-Umgebung `F+E` zeigt `python` auf einen anderen Interpreter,
  und die Pakete fehlen. Kennt PowerShell `conda` nicht, hilft einmalig
  `conda init powershell` und ein neues Terminal.
- PySide6 muss aus conda kommen, nicht aus pip, sonst scheitert der Import von
  `QtCore`. Die Begründung steht in [`frontend/README.md`](frontend/README.md).

## Der Projektordner im Überblick

| Ordner | Was darin liegt |
| --- | --- |
| `frontend/` | DataBridge Explorer, die Auswahl-Oberfläche in PySide6. Läuft als Programm auf dem Rechner, nicht im Container. |
| `mediator/` | Der zentrale Dienst (FastAPI). Nimmt Aufträge an, ruft die Wrapper, übersetzt nach RDF/OWL und baut die `.h5ad`-Dateien. Läuft im Container. |
| `wrappers/` | Je ein Modul pro Datenquelle: `gdc`, `geo`, `ena`, `cbioportal`. Python-Pakete, die im Mediator-Container mitlaufen. |
| `wissensnetz/` | Die semantische Schicht: Ontologie, Zugriff auf den Store, Anreicherung per SPARQL, Rückkanal und das Kommandozeilenwerkzeug `wissensnetz`. Unter `prototype/mp_lite/` liegt der Bokeh-Prototyp als Vergleichsmaßstab. |
| `scripts/` | Hilfsskripte zum Laden und Prüfen: `load_gdc.py`, `run_selection.py`, `graph_view.py`, `check_h5ad.py`. |
| `docs/` | Diagramme (drawio) zu Architektur, Ablauf und Skriptkette sowie `adding_new_sources.md`, die Anleitung zum Anbinden einer neuen Quelle. |
| `memory/` | Das fortlaufende Projektgedächtnis. `context.md` ist der ausführlichste Stand und nennt die Begründungen hinter den Entscheidungen. |
| `recherche/` | Konzeptbilder zur Navigation im Wissensnetz, ältere Konzept- und Rechercheunterlagen unter `_archiv/`. |
| `Orga/` | Aufgabenstellung der Hochschule und Anträge. |
| `Export Anndata/` | Abgelegte `.h5ad`-Dateien aus Testläufen. |
| `morphing-projections-demo-and-dataset-preparation-master/` | Die Original-Demo aus Oviedo als Referenz und Herkunftsnachweis. Kein Teil der Laufzeit, es importiert nichts daraus. |

Der Triple-Store hat keinen eigenen Ordner mehr, er steht als Dienst `graph-db`
in `docker-compose.yml` und legt seine Daten in einem Docker-Volume ab.

Wichtige Dateien im Projekt-Root:

| Datei | Zweck |
| --- | --- |
| `start_all.ps1`, `stop_all.ps1` | Alles starten beziehungsweise alles stoppen. |
| `docker-compose.yml` | Mediator und Triple-Store als Container. |
| `requirements.txt` | Pakete für die Conda-Umgebung `F+E` auf dem Rechner. |
| `.env.example` | Vorlage für `.env`, einmal kopieren und anpassen. |
| `RUNBOOK.md` | Alle Befehle im Detail, dazu Troubleshooting. |
| `How to Use.pdf`, `Instructions.pptx` | Bedienanleitung des Teams für Nutzer. |
| `Installationsguide_DE-EN-ES.pdf` | Installationsanleitung in drei Sprachen. |
| `graph_view.html` | Erzeugte Diagnoseansicht des Graphen, entsteht mit `start_all.ps1 -WithGraphView`. |

## Wer macht was

| Komponente | Zuständig |
| --- | --- |
| `wrappers/` | Julian Lanfermann |
| `mediator/` | Pablo Scherer |
| `wissensnetz/`, `frontend/`, Startskripte | Marcel Thiel |

Die Grenze ist bewusst strikt: jeder ändert nur seine Komponente, die Kopplung
läuft über HTTP und SPARQL. So bleiben die Teile unabhängig voneinander
lauffähig.

## Wo es weitergeht

| Frage | Datei |
| --- | --- |
| Wie starte ich etwas Bestimmtes? | [`RUNBOOK.md`](RUNBOOK.md) |
| Was ist der aktuelle Stand und warum? | [`memory/context.md`](memory/context.md) |
| Wie funktioniert die Oberfläche? | [`frontend/README.md`](frontend/README.md) |
| Wie ist das Wissensnetz aufgebaut? | [`wissensnetz/README.md`](wissensnetz/README.md), [`wissensnetz/ontology/README.md`](wissensnetz/ontology/README.md) |
| Wie übersetzt der Mediator nach RDF? | [`mediator/app/semantic/README.md`](mediator/app/semantic/README.md) |
| Wie funktioniert ein einzelner Wrapper? | `wrappers/<quelle>/README.md`, zum Beispiel [`wrappers/gdc/README.md`](wrappers/gdc/README.md) |
| Wie binde ich eine neue Quelle an? | [`docs/adding_new_sources.md`](docs/adding_new_sources.md) |
