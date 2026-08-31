# DataBridge — Runbook (alle Befehle zum Starten)

Kurzreferenz, um das Projekt und alle Skripte zum Laufen zu bringen.

> **Wichtig:** Alle Befehle **aus dem Projekt-Root** ausführen (dort wo diese
> Datei, `docker-compose.yml` und `requirements.txt` liegen — bei dir
> `C:\Dev\F+E\F-E_Projekt1`) und mit **aktivierter Conda-Env**:
> ```powershell
> conda activate F+E
> cd C:\Dev\F+E\F-E_Projekt1
> ```

---

## 1. Schnellstart — alles mit einem Befehl (`start_all.ps1`)

Ein Skript fährt die **komplette Pipeline** hoch: prüft/startet Docker, startet
Fuseki, initialisiert das Wissensnetz, baut/startet den Mediator-**Container**
(mit `gdc-client`), lädt alle Kohorten in den Graphen, ruft die Pancancer-
Expressions-`.h5ad` ab und öffnet zum Schluss die Oberfläche (MP-lite).

```powershell
conda activate F+E
cd C:\Dev\F+E\F-E_Projekt1
powershell -ExecutionPolicy Bypass -File .\start_all.ps1
```

Was das Skript der Reihe nach macht: (1) Abhängigkeiten sicherstellen →
(2) Docker prüfen, ggf. Docker Desktop starten und warten → (3) Fuseki starten →
(4) `wissensnetz init` → (5) Mediator-Container bauen/starten (`docker compose`,
enthält `gdc-client`) → (6) alle Oviedo-Kohorten laden (`load_gdc.py --pancancer`,
Basis der Kohorten-Färbung) → (6c) Pancancer-`.h5ad` abrufen
(`fetch_pancancer_h5ad.py` → `wissensnetz/data/pancancer.h5ad`) → (7) Bokeh öffnen.

Optionen:

| Option | Wirkung |
| --- | --- |
| `-Size 100` | mehr Fälle **pro Kohorte** beim Graph-Load |
| `-PancancerSize 80` | mehr Proben in der Pancancer-`.h5ad` (längere Downloads) |
| `-SkipLoad` | Dienste starten, aber weder Graph-Load noch Pancancer-Abruf |
| `-NoUi` | ohne Bokeh-Oberfläche (nur Dienste) |
| `-SkipInstall` | `pip install` überspringen |
| `-MediatorPort 8001` | anderen Mediator-Port verwenden |

Hinweise: Der **Mediator** läuft jetzt als **Docker-Container** (kein eigenes
Fenster mehr; Logs via `docker compose logs -f mediator`); die **Oberfläche** läuft
im aktuellen Fenster. Der **erste Lauf baut das Mediator-Image** (einige Minuten,
lädt `gdc-client` aus bioconda). **Strg+C beendet alles** — es stoppt die Oberfläche
und fährt danach automatisch Mediator + `graph-db` (`docker compose down`) herunter
und schließt das Fenster.

Damit sich das Fenster wirklich schließt, das Skript **direkt in der aktivierten
Session** starten (nicht als `powershell -File`-Kindprozess):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start_all.ps1
```

Manuelles Herunterfahren (falls `-NoUi` lief oder etwas hängen blieb):
```powershell
.\stop_all.ps1
```

> Die folgenden Abschnitte erklären **dieselben Schritte einzeln** — als
> Detailreferenz, falls etwas hakt oder du nur einen Teil starten willst.

---

## 0. Voraussetzungen
- Conda-Env **F+E** aktiv, **Docker Desktop** installiert, Terminal im Projekt-Root.

## 1. Einmalige Einrichtung (Abhängigkeiten)
```powershell
pip install -r requirements.txt
```
Installiert die lokalen Pakete editable (`wissensnetz`, `wrappers` → gibt dir den
`wissensnetz`-Befehl) plus Prototyp-/Mediator-/Test-Pakete.

## 2. Triple-Store starten & initialisieren
```powershell
docker compose up -d graph-db          # Fuseki starten
wissensnetz status                     # Erreichbarkeit prüfen
wissensnetz init                       # Dataset 'databridge' + TBox + Rückkanal-Vokabular laden (idempotent)
```
Fuseki-Weboberfläche: <http://localhost:3030>  (Login `admin` / `admin`).

## 3. Schnelltest mit Beispieldaten (ohne GDC)
```powershell
wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl
wissensnetz query "SELECT (COUNT(?c) AS ?n) WHERE { ?c a db:Case }"
wissensnetz context TCGA-A1-A0SB
```

## 4. Mit echten TCGA/GDC-Daten arbeiten
Der GDC-Abruf + das Mapping nach Turtle laufen über den **Mediator** (Kollege B);
das Wissensnetz konsumiert das Turtle.

**a) Mediator starten** (eigenes Terminal, im Projekt-Root):
```powershell
cd mediator
uvicorn app.main:app --port 8000
```
(Alternativ als Container: `docker compose up -d mediator` — baut länger.)

**b) Fälle abrufen und laden** (Hilfsskript, ein Befehl):
```powershell
python scripts/load_gdc.py --project TCGA-BRCA --size 50
```
Optionen: `--size`, `--project`, `--graph <IRI>`, `--mediator-url <url>`.

**Alle 32 Oviedo-Kohorten (Pancancer)** für die Krebsarten-Ansicht in MP-Lite:
```powershell
python scripts/load_gdc.py --pancancer --size 50
```
`--size` gilt pro Projekt; ein fehlschlagendes Projekt bricht den Lauf nicht ab
(Warnung + Zusammenfassung am Ende). Für eine Teilmenge: `--projects TCGA-ACC,TCGA-BRCA`.

Alternativ lädt der Mediator direkt selbst (`POST /transform` mit
`"load": true` schreibt das erzeugte Turtle per Graph Store Protocol in
`graph-db` — kein externer Zwischenschritt nötig, siehe Root-README):
```powershell
curl -X POST http://localhost:8000/transform `
  -H "Content-Type: application/json" `
  -d '{\"source\": \"gdc\", \"project_id\": \"TCGA-BRCA\", \"size\": 50, \"load\": true}'
```

**c) Damit arbeiten:**
```powershell
wissensnetz query "SELECT ?sid WHERE { ?c a db:Case ; db:submitterId ?sid } LIMIT 5"
wissensnetz context <einer-der-submitterIds>
```

## 5. Wissensnetz-CLI (Referenz)
| Befehl | Zweck |
| --- | --- |
| `wissensnetz status` | Erreichbarkeit, Dataset, TBox prüfen |
| `wissensnetz init [--force]` | Dataset + TBox + Rückkanal-Vokabular laden |
| `wissensnetz load <datei.ttl \| ->` | Turtle laden (`-` = stdin), `--graph <IRI>` |
| `wissensnetz query "<SPARQL>"` | SELECT/ASK ausführen (`--raw` ohne PREFIXE) |
| `wissensnetz hierarchy <klasse> [--up]` | Unter-/Oberklassen (`rdfs:subClassOf*`) |
| `wissensnetz context <case-oder-diagnose-ref>` | Fall-/Diagnose-Kontext (②) |
| `wissensnetz feedback <event.json> [--user]` | MP-Selektion zurückschreiben (③) |
| `wissensnetz findings [--user]` | gespeicherte Erkenntnisse auflisten |

## 6. MP-lite-Prototyp starten (Loop MP ↔ Wissensnetz)
```powershell
bokeh serve --show wissensnetz/prototype/mp_lite/app.py
```
Öffnet den Browser: Punkte selektieren → Kontext (②); Hypothese eintragen →
„Selektion als Erkenntnis speichern" (③). Details: `wissensnetz/prototype/README.md`.

## 6b. Wissensnetz visuell ansehen (pyvis)
```powershell
python scripts\graph_view.py --limit 500     # erzeugt graph_view.html und öffnet es
```
Interaktives Netz aus dem aktuellen Fuseki-Inhalt, farbcodiert: Schema (blau),
TCGA-Instanzen (grün), Rückkanal/Annotationen (rot), externe Konzepte wie NCIt
(lila). Einfach erneut ausführen, um das Wachstum zu sehen. `start_all.ps1` ruft
das beim Start automatisch auf. Optionen: `--limit`, `--output`, `--no-open`.

## 6c. Pancancer-Expressions-Karte erzeugen (Aufgabe 10)
Statt des kleinen BRCA-Referenz-`.h5ad` eine **Pancancer**-Expressions-Landkarte
(echte Gene-Expression über viele TCGA-Kohorten, globale tSNE) live über den
Mediator-Export (`POST /export/anndata`) beschaffen.

**Voraussetzungen:** Mediator läuft (Abschnitt 4a), im Mediator-Container ein
funktionierender **`gdc-client`**, und **Fuseki ist gefüllt** (Abschnitt 4b —
liefert die `obs`-Klinikfelder). Fehlt eins davon, meldet das Skript einen klaren
Fehler (meist HTTP 503) statt eines Stacktrace.

```powershell
python scripts\fetch_pancancer_h5ad.py --size 20     # kleiner Smoke-Test zuerst!
python scripts\fetch_pancancer_h5ad.py               # Default: alle Kohorten, size 160
```
Legt `wissensnetz/data/pancancer.h5ad` an; der Report zeigt `n_obs`/`n_vars`,
`obsm_keys` und die vertretenen Kohorten. **MP-Lite bevorzugt diese Datei
automatisch** — danach nur die Oberfläche neu laden:
```powershell
bokeh serve --show wissensnetz/prototype/mp_lite/app.py
```
Die Statuszeile nennt dann `pancancer.h5ad`, der „genes"-Slider morpht entlang der
globalen tSNE, Punkte sind nach Krebsart gefärbt, Marker-Slider (CA9/SAA1) aktiv.

Optionen: `--size` (1..200, große RNA-Seq-Downloads dauern — klein anfangen),
`--projects TCGA-ACC,TCGA-BRCA` (Teilmenge), `--out <pfad>`, `--mediator-url <url>`.
Für eine **gleichmäßig über die Kohorten balancierte** Karte (Oviedo-treu, aber mehr
Downloads): `--balanced --per-cohort-size 5` (pro Kohorte ein Abruf, danach eine
globale tSNE im Skript). Ohne die Datei bleibt MP-Lite beim BRCA-Fixture (Aufgabe 9).

## 7. Rückkanal per CLI testen
```powershell
wissensnetz feedback wissensnetz/data/sample/selection_event.json
wissensnetz findings
```

## 8. Tests
```powershell
pip install -e ".\wissensnetz[test]"     # falls pytest fehlt
cd wissensnetz
pytest                                    # braucht laufendes Fuseki (sonst werden Tests übersprungen)
```

## 9. Stoppen / Aufräumen
```powershell
.\stop_all.ps1               # alles herunterfahren (Mediator, Oberfläche, graph-db)
docker compose down          # nur Container stoppen (Daten bleiben im Volume)
docker compose down -v       # inkl. Löschen der Fuseki-Daten (Dataset weg)
```
Beim Start über `start_all.ps1` genügt **Strg+C** — das fährt alles herunter.

---

## Troubleshooting
- **`no configuration file provided: not found`** → nicht im Projekt-Root. `cd C:\Dev\F+E\F-E_Projekt1`.
- **`Fuseki nicht erreichbar`** → `docker compose up -d graph-db`, dann `wissensnetz status`.
- **`Mediator nicht erreichbar`** (bei `load_gdc.py`) → Mediator starten (Abschnitt 4a).
- **`wissensnetz` wird nicht gefunden** → `pip install -r requirements.txt` (installiert das CLI) und Env aktiv.
- **Port 3030/8000 belegt** → in `.env` `GRAPH_DB_PORT` bzw. beim `uvicorn`-Start `--port` ändern.
- **Zeilenenden (LF/CRLF) im `git status`** → Anzeige-Rauschen; nicht committen (ggf. `.gitattributes` mit `* text=auto eol=lf` ergänzen).

## Wer macht was (Kurz)
- **Wrapper** (`wrappers/`, Kollege A): GDC-API-Zugriff.
- **Mediator** (`mediator/`, Kollege B): FastAPI + GDC→RDF/Turtle (`/transform`), anndata (geplant).
- **Wissensnetz** (`wissensnetz/`, Marcel): Fuseki-Store, SPARQL-Anreicherung, Rückkanal, MP-lite-Prototyp.
