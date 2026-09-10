# DataBridge · Wissensnetz — Änderungen Aufgabe 1 & 2 (Review-Dokument)

> **Zweck:** Dieses Dokument ist bewusst *self-contained* geschrieben, damit es
> einer separaten Claude-Session **ohne Repo-Zugriff** zur Analyse/Review
> übergeben werden kann. Es enthält Kontext, Design-Entscheidungen mit
> Begründung, den vollständigen Diff (Anhang A) und die verifizierten
> Test-/Ausführungs-Ausgaben (Anhang B).
>
> Branch: `Wissensnetz` · 2 Commits auf Basis `fc73f56` (Mediator).
> Umgebung der Verifikation: Docker `stain/jena-fuseki:latest` (Fuseki **5.1.0**,
> Jena TDB2), Python **3.14**, rdflib **7.6**, requests **2.34**, pytest **9.1**.

---

## 1. Aufgabenstellung & Rahmen

**Projekt DataBridge** koppelt TCGA-Daten (GDC-API) an Visualisierungstools der
Uni Oviedo. Arbeitsteilung:
- **Wrapper** (`wrappers/gdc/`) — GDC-API-Zugriff (Kollege A, fertig).
- **Mediator** (`mediator/`) — FastAPI + GDC→RDF/Turtle-Mapping (Kollege B).
- **Wissensnetz** (`wissensnetz/`, *mein* Teil) — RDF-Store + SPARQL + Rückkanal.

**Komponentengrenze (strikt, aus `wissensnetz/CLAUDE.md`):**
- Nur unter `wissensnetz/` schreiben; `mediator/` und `wrappers/` **nicht** ändern.
- Kein Import von Code aus `mediator/`/`wrappers/` (Abhängigkeitsrichtung nur
  Mediator→Wissensnetz).
- Das GDC→RDF-Mapping **nicht** nachbauen — nur den fertigen Turtle-Output konsumieren.
- Kommunikation nur über HTTP/SPARQL gegen den `graph-db`-Service (Apache Jena Fuseki).
- Eigenständiges, installierbares Python-Paket; Branch `Wissensnetz`; kleine Commits.

**Umgesetzt wurden Aufgabe 1 und 2:**

| Aufgabe | Inhalt | Abnahmekriterium |
| --- | --- | --- |
| **1** | Fuseki-Dataset `databridge` beim Start anlegen + TBox `databridge-core.ttl` laden | Nach `docker compose up graph-db` existiert das Dataset; SPARQL liefert die TBox-Klassen (`db:Case`, `db:Diagnosis`, …) |
| **2** | Graphstore-Client `load_turtle` / `query` / `update`; Mediator-Turtle laden | Beispieldaten geladen, `query` liefert erwartete Cases/Diagnosen; Pytest gegen laufendes Fuseki (Skip wenn nicht erreichbar) |

Aufgabe 3 (SPARQL-Anreicherung) und 4 (Rückkanal) sind **bewusst noch offen**
(laut CLAUDE.md „Empfohlener Einstieg": erst 1+2, dann Review).

---

## 2. Was neu ist (Dateiübersicht)

**Neues Paket `wissensnetz/` (src-Layout, installierbar):**

| Datei | Rolle |
| --- | --- |
| `pyproject.toml` | Installierbares Paket „wissensnetz" (Muster wie `wrappers/`), Console-Script `wissensnetz`, Test-Extra |
| `requirements.txt` | Laufzeit-/Test-Abhängigkeiten (`rdflib`, `requests`, `pytest`) |
| `src/wissensnetz/config.py` | Verbindungs-/Namespace-Konfiguration aus ENV (`Settings`, `PREFIXES`) |
| `src/wissensnetz/graphstore.py` | **Aufgabe 2:** Fuseki-Client (`GraphStore`): `load_turtle`, `query`, `update`, `ask`, Dataset-Admin |
| `src/wissensnetz/init.py` | **Aufgabe 1:** `initialize()` — Dataset sicherstellen + TBox laden (idempotent) |
| `src/wissensnetz/cli.py` | CLI `wissensnetz status\|init\|load\|query` |
| `src/wissensnetz/__init__.py` | Öffentliche API (`GraphStore`, `Settings`, `initialize`) |
| `data/sample/cases_brca_sample.ttl` | **Eingefrorene** Mediator-Turtle-Ausgabe (Fixture, 58 Tripel) |
| `tests/conftest.py` | Fixtures: `store` (Skip wenn Fuseki fehlt), `loaded_store` |
| `tests/test_init.py` | Aufgabe-1-Abnahme (TBox-Klassen abfragbar, Idempotenz) |
| `tests/test_graphstore.py` | Aufgabe-2-Abnahme (Cases/Diagnosen laden & lesen) |
| `README.md` | End-to-End-Ablauf, CLI/API-Referenz, Teststrategie |

**Geänderte Dateien außerhalb `wissensnetz/`** (bewusst, siehe §4):

| Datei | Änderung |
| --- | --- |
| `docker-compose.yml` | `FUSEKI_DATASET_1=${GRAPH_DB_DATASET:-databridge}` im `graph-db`-Service |
| `graph-db/README.md` | Abschnitt „Dataset-Initialisierung (Wissensnetz)" + Auth-Hinweis |
| `.env.example` | `GRAPH_DB_URL` (optional), `GRAPH_DB_ADMIN_USER/PASSWORD` im graph-db-Block |

`wissensnetz/CLAUDE.md` und `wissensnetz/TASKS_wissensnetz.md` (Kontext-/Aufgaben-
Dateien, zuvor untracked) wurden mit auf den Branch committet.

---

## 3. Zentrale Design-Entscheidungen (mit Begründung)

### 3.1 Dataset-Anlage per `FUSEKI_DATASET_1` (statt Assembler in `graph-db/init/`)
Die Aufgabe bot zwei Wege an (Assembler-`.ttl` in `graph-db/init/` **oder**
`FUSEKI_DATASET_*`-ENV) und verlangt „den Weg, der zum `stain/jena-fuseki`-Image
passt". Gewählt: die **image-eigene** Variable `FUSEKI_DATASET_1`. Sie erzeugt
beim Container-Start einen TDB2-Assembler unter `/fuseki/configuration/databridge.ttl`
(mit `TDB=2` → persistent im Volume `graph-db-data`). Der vorhandene Mount
`./graph-db/init:/init:ro` zeigt **nicht** auf Fusekis Konfigurationsverzeichnis
(`/fuseki/configuration`), ein Assembler dort würde also gar nicht automatisch
geladen — der ENV-Weg ist damit der robustere und wurde dokumentiert.
*Verifiziert:* Log „Creating dataset databridge"; Config + TDB2-DB überleben `restart`.

### 3.2 TBox-Load durch `wissensnetz init` (SPARQL/GSP), idempotent, in den Default-Graph
Der Container legt nur das (leere) Dataset an; die TBox lädt der Client-Schritt
`wissensnetz init`. Das passt zum dokumentierten End-to-End-Ablauf
(`up → init → load → query`) und der DoD („Init legt Dataset+TBox an").
- **Idempotent:** `init` prüft per `ASK { db:Case a owl:Class }` und überspringt
  das Laden, wenn die TBox schon da ist (`--force` erzwingt Neuladen). So bleibt
  auch die bnode-basierte Cardinality-Restriktion frei von Duplikaten bei Re-Runs.
- **Default-Graph:** TBox **und** ABox liegen im selben Default-Graph, damit
  einfache Abfragen Klassen und Instanzen ohne `GRAPH`-Klausel sehen (der
  generierte Assembler setzt *kein* `unionDefaultGraph`). Named Graphs kommen
  erst beim Rückkanal (Aufgabe 4, „Named Graph pro Nutzer").
- **Fallback:** `init` legt das Dataset zusätzlich per Admin-API an, falls es
  fehlt — funktioniert also auch ohne die `FUSEKI_DATASET_1`-Variable.

### 3.3 `load_turtle` sendet Turtle **roh** (RDF-star-Falle)
Der Turtle-Text wird unverändert per Graph Store Protocol an Fuseki übertragen —
**kein** rdflib-Parse/Serialize-Roundtrip. Grund (CLAUDE.md): Der Mediator hängt
RDF-star-Blöcke (`<< s p o >> …`) als Text an, die rdflib je nach Version nicht
parst; Fuseki hat nativen RDF-star-Support (ADR-0002). So bleiben spätere
Provenienz-/Konfidenz-Aussagen erhalten. (Die aktuelle Beispiel-Fixture enthält
keine RDF-star-Blöcke, weil die Alignment-Tabelle leer ist — der rohe Transport
ist aber die Voraussetzung dafür, dass es bei befüllter Tabelle funktioniert.)

### 3.4 Authentifizierung: nur Schreibzugriffe brauchen Basic-Auth
Beim Testen zeigte sich (und wurde in der `shiro.ini` des Images bestätigt):
`/*/update/**`, `/*/data/**` und `/$/**` erfordern Basic-Auth (`admin`/`admin`),
SPARQL-*Query* (`/**`) ist anonym. Daher sendet der Client Admin-Credentials
**nur** bei `update()`, `load_turtle()` und Dataset-Admin — `query()` bleibt
anonym (funktioniert damit auch in read-only-Setups). Passwort über
`GRAPH_DB_ADMIN_PASSWORD` konfigurierbar.

### 3.5 Beispiel-ABox als **eingefrorene** Mediator-Ausgabe (keine Reimplementierung)
`data/sample/cases_brca_sample.ttl` ist die 1:1-Ausgabe von
`mediator/scripts/example_gdc_to_rdf.py` (== `POST /transform`), als Fixture
eingecheckt. So wird der Mediator-Output *konsumiert*, ohne das Mapping
nachzubauen oder Mediator-Code zu importieren (Komponentengrenze). Der Header der
Datei weist ausdrücklich darauf hin, sie bei Mapping-Änderungen neu zu ziehen.

### 3.6 Weitere Punkte
- **src-Layout + Console-Script** `wissensnetz` (entry point `wissensnetz.cli:main`);
  Muster analog `wrappers/pyproject.toml`. Mediator kann später optional
  `pip install -e ./wissensnetz` nutzen (Richtung Mediator→Wissensnetz).
- **Tests skippen**, wenn kein Fuseki erreichbar ist (`is_reachable()` via `/$/ping`),
  statt zu scheitern — CI ohne Store bleibt grün.
- **Ergebnis-Format** von `query()`: Liste von `{var: wert}`-Dicts (SPARQL-JSON,
  Werte als String), ASK → `[{"boolean": bool}]`.

---

## 4. Komponentengrenze — Compliance & bewusste Grenzfälle

**Eingehalten:**
- `git diff --name-only fc73f56 HEAD | grep -E '^(mediator|wrappers)/'` → **leer**
  (keine Änderungen an fremden Komponenten; siehe Anhang B).
- Kein Import aus `mediator/`/`wrappers/`; nur `rdflib`/`requests` + Stdlib.
- GDC→RDF-Mapping nicht nachgebaut (nur eingefrorene Turtle-Fixture konsumiert).

**Bewusst außerhalb `wissensnetz/` geändert — zur Review:**
`docker-compose.yml`, `graph-db/README.md`, `.env.example`. Begründung: Die
Regel nennt ausdrücklich nur `mediator/` und `wrappers/` als tabu; laut CLAUDE.md
„besitzt das Wissensnetz den RDF-Store" (`graph-db`). Die Aufgabe verlangt zudem
explizit, `graph-db/README.md` um den Init-Weg zu ergänzen und das Dataset „beim
Start" anzulegen (nur via `docker-compose` möglich). Die Änderungen sind minimal
und additiv (eine ENV-Zeile, ein README-Abschnitt, drei ENV-Beispiele) und
fassen den `mediator`-Service **nicht** an. → *Sollte das Team `docker-compose.yml`
als geteilte Infrastruktur strenger schützen wollen, ist dies der Punkt zum
Gegensteuern.*

---

## 5. Punkte, auf die die Review besonders schauen sollte

1. **Grenzfall-Interpretation** (§4): Sind Änderungen an `docker-compose.yml`/
   `graph-db/` akzeptabel, oder soll die Dataset-Anlage rein client-seitig
   (`init` per Admin-API) passieren, ganz ohne Compose-Änderung?
2. **Graph-Layout:** TBox+ABox im Default-Graph. Für Aufgabe 3 (Hierarchie via
   `rdfs:subClassOf*`) unkritisch; für Aufgabe 4 sind Named Graphs pro Nutzer
   vorgesehen. Reicht das, oder sollte die TBox früh in einen eigenen Graph?
3. **Sicherheit (Prototyp):** Admin-Passwort `admin` im Klartext in
   `docker-compose.yml`/`.env.example`. Für die FuE-Prototyp-Phase bewusst so;
   für später zu härten.
4. **`_resolve_turtle`-Heuristik** (Text vs. Pfad): unterscheidet an Suffix
   `.ttl` + Existenz + Länge < 260. Über die CLI unkritisch (dort wird Existenz
   vorab geprüft); über die API ist ein `Path`-Objekt der eindeutige Weg.
5. **`create_dataset` toleriert HTTP 409** (existiert bereits) — bewusst für
   Idempotenz; sonst wird der Status geprüft.
6. **Windows/Zeilenenden:** Git meldet LF→CRLF-Normalisierung; keine `.gitattributes`
   ergänzt (Repo hatte bisher keine). Ggf. Team-Konvention prüfen.
7. **Abhängigkeiten:** `rdflib` ist als Dependency deklariert, wird in Aufgabe 1+2
   aber noch nicht zwingend gebraucht (roher Turtle-Transport). Es ist für die
   ETL/Serialisierung in Aufgabe 4 vorgesehen — bewusst früh deklariert.

---

### 5.1 Während der Verifikation gefunden & behoben (Commit 3)
Beim **Wiederholen** der Tests gegen den *persistenten* Store fielen zwei
Count-basierte Abnahme-Tests durch: Der `load_turtle`-Test hatte einen
`UNITTEST`-Case in den Default-Graph geschrieben, wodurch „COUNT `db:Case` == 4"
ab dem zweiten Lauf 5 zählte. Auf dem ersten (leeren) Volume war es nicht
aufgefallen, weil der störende Test zufällig zuletzt lief. Behoben durch:
(a) Eingrenzung der Beispiel-Abfragen auf das Projekt `TCGA-BRCA` (robust gegen
fremde Daten), (b) Laden des `load_turtle`-Tests in einen eigenen **Named Graph**
mit `DROP GRAPH` im `finally`. Ergebnis: 9/9 grün bei zwei aufeinanderfolgenden
Läufen gegen denselben Store (Anhang B.3). *Lehre für Aufgabe 3/4: Tests, die
gegen einen persistenten Store laufen, müssen sich selbst isolieren.*

## 6. Nächste Schritte (nicht Teil dieser Änderung)
- **Aufgabe 3** `enrichment.py`: Klassen-/Krankheitshierarchie (`rdfs:subClassOf*`),
  Fall-/Diagnose-Kontext; als Funktionen + `wissensnetz query …`.
- **Aufgabe 4** `feedback.py`: MP-Selektions-Event → `oa:Annotation`/PROV-O/RDF-star,
  SPARQL-star-INSERT in Named Graph pro Nutzer. `graphstore.update()` steht bereit.

---

## Anhang A — Vollständiger Diff (`git diff fc73f56 HEAD`)

```diff
diff --git a/.env.example b/.env.example
index 01cbb8a..1d9e0e3 100644
--- a/.env.example
+++ b/.env.example
@@ -25,3 +25,14 @@ DATABRIDGE_ONTOLOGY_DIR=./wissensnetz/ontology
 # diese Variablen an das jeweilige Zielsystem anpassen.
 GRAPH_DB_PORT=3030
 GRAPH_DB_DATASET=databridge
+
+# Vom Wissensnetz-Client (Paket wissensnetz/) gelesen. Innerhalb von Compose
+# spricht der Client den Service über GRAPH_DB_URL=http://graph-db:3030 an;
+# außerhalb (lokale Entwicklung/Tests) wird ohne GRAPH_DB_URL aus Host/Port
+# http://localhost:${GRAPH_DB_PORT} gebildet — diese Variable ist daher nur bei
+# Bedarf zu setzen. Das Admin-Passwort muss zu ADMIN_PASSWORD des graph-db-
+# Containers passen (docker-compose.yml) und wird für Schreibzugriffe
+# (SPARQL Update / Graph Store Protocol) benötigt.
+# GRAPH_DB_URL=http://localhost:3030
+GRAPH_DB_ADMIN_USER=admin
+GRAPH_DB_ADMIN_PASSWORD=admin
diff --git a/docker-compose.yml b/docker-compose.yml
index b891b05..0884bc7 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -42,6 +42,12 @@ services:
     environment:
       - ADMIN_PASSWORD=admin
       - TDB=2
+      # Legt beim Container-Start ein persistentes TDB2-Dataset an (Feature des
+      # stain/jena-fuseki-Images: FUSEKI_DATASET_N -> Assembler-Config unter
+      # /fuseki/configuration, im Volume persistiert). Name aus .env, Default
+      # "databridge". Die TBox lädt anschließend `wissensnetz init` (SPARQL/GSP)
+      # — siehe graph-db/README.md und wissensnetz/README.md.
+      - FUSEKI_DATASET_1=${GRAPH_DB_DATASET:-databridge}
     ports:
       - "${GRAPH_DB_PORT:-3030}:3030"
     volumes:
diff --git a/graph-db/README.md b/graph-db/README.md
index 8fe9547..3da17de 100644
--- a/graph-db/README.md
+++ b/graph-db/README.md
@@ -15,7 +15,45 @@ für die Abwägung und den aktuellen Stand der Entscheidung.
 `graph-db`. Es ist **kein eigener Code** enthalten, nur Konfiguration.
 
 - `init/` – Ablage für künftige Initialisierungs-/Konfigurationsdateien
-  (z. B. Fuseki-Dataset-Assembler, initiale Turtle-Dateien). Aktuell leer.
+  (z. B. Fuseki-Dataset-Assembler, initiale Turtle-Dateien). Aktuell leer:
+  Für die Dataset-Anlage wurde der ENV-Weg gewählt (siehe unten), nicht ein
+  Assembler-`.ttl` in diesem Ordner.
+
+## Dataset-Initialisierung (Wissensnetz)
+
+Gewählter Weg, passend zum `stain/jena-fuseki`-Image: **Dataset per ENV-Variable
+beim Container-Start, TBox anschließend per `wissensnetz init`.**
+
+1. **Dataset anlegen** — `docker-compose.yml` setzt im `graph-db`-Service
+   `FUSEKI_DATASET_1=${GRAPH_DB_DATASET:-databridge}`. Das Image legt daraus
+   beim Start ein **persistentes TDB2-Dataset** an (`TDB=2`); der generierte
+   Assembler landet unter `/fuseki/configuration/databridge.ttl`, die Daten
+   unter `/fuseki/databases/databridge` — beides im benannten Volume
+   `graph-db-data`, also über Container-Neustarts hinweg persistent. Nach
+   `docker compose up graph-db` existiert das Dataset unter
+   `http://localhost:3030/databridge`.
+
+2. **TBox laden** — die Ontologie `wissensnetz/ontology/databridge-core.ttl`
+   wird nicht vom Container, sondern vom Wissensnetz-Client geladen (idempotent,
+   über SPARQL/Graph Store Protocol):
+
+   ```
+   pip install -e ./wissensnetz
+   wissensnetz init          # Dataset sicherstellen + TBox laden
+   ```
+
+   `wissensnetz init` legt das Dataset zusätzlich über die Fuseki-Admin-API an,
+   falls es fehlt — der Schritt funktioniert also auch, wenn der Container ohne
+   `FUSEKI_DATASET_1` gestartet wurde.
+
+Der End-to-End-Ablauf (up → init → load → query → feedback) ist in
+[`../wissensnetz/README.md`](../wissensnetz/README.md) beschrieben.
+
+**Zugriffsschutz:** Die mitgelieferte `shiro.ini` erlaubt SPARQL-*Query* anonym,
+verlangt für SPARQL-*Update* und Graph Store Protocol (`/*/update`, `/*/data`)
+sowie die Admin-API (`/$/`) aber Basic-Auth (`admin`/`admin`). Der
+Wissensnetz-Client sendet die Admin-Credentials für Schreibzugriffe automatisch
+(konfigurierbar über `GRAPH_DB_ADMIN_PASSWORD`).
 
 ## Austausch gegen eine Property-Graph-DB
 
diff --git a/wissensnetz/CLAUDE.md b/wissensnetz/CLAUDE.md
new file mode 100644
index 0000000..7631bdd
--- /dev/null
+++ b/wissensnetz/CLAUDE.md
@@ -0,0 +1,56 @@
+# Wissensnetz — Arbeitskontext für Claude Code
+
+Diese Datei gilt für Arbeiten im Ordner `wissensnetz/` (Teilbereich Marcel).
+Sie beschreibt den **dauerhaften** Kontext und die harten Regeln. Die konkrete,
+abzuarbeitende Aufgabenliste steht in `wissensnetz/TASKS_wissensnetz.md`.
+
+## Projektkontext
+DataBridge (Master-FuE-Projekt, HS Karlsruhe / Uni Oviedo) koppelt TCGA-Daten
+(GDC-API) an die Visualisierungstools der Uni Oviedo (Morphing Projections,
+GEM-i). Arbeitsteilung im Team:
+- **Wrapper** (`wrappers/gdc/`): GDC-API-Zugriff — FERTIG (Kollege A).
+- **Mediator + Konvertierung** (`mediator/`): FastAPI + GDC→RDF-Mapping
+  (`app/semantic/mapping.py`, `POST /transform` liefert Turtle-Text),
+  anndata (später) — FERTIG/laufend (Kollege B).
+- **Wissensnetz** (`wissensnetz/`, MEIN Teil): RDF-Store + SPARQL + Rückkanal.
+
+## Komponentengrenze (strikt)
+> Der Mediator produziert RDF/Turtle. Das Wissensnetz besitzt den RDF-Store und
+> seine Lese-/Schreib-Oberfläche. Naht = RDF/Turtle. Kommunikation nur über
+> HTTP/SPARQL gegen den `graph-db`-Service (Apache Jena Fuseki).
+
+## Harte Regeln
+- **Nur unter `wissensnetz/` schreiben.** `mediator/` und `wrappers/` NICHT ändern.
+- Kein Import von Code aus `mediator/` oder `wrappers/`
+  (Abhängigkeitsrichtung nur Mediator→Wissensnetz, nie umgekehrt).
+- **Das GDC→RDF-Mapping NICHT nachbauen** — B besitzt es; wir konsumieren nur
+  den fertigen Turtle-Output.
+- Kein anndata, kein GDC-API-Zugriff (fremde Teile).
+- Eigenständiges, installierbares Python-Paket (Muster wie `wrappers/pyproject.toml`),
+  damit der Mediator es später optional per `pip install -e ./wissensnetz` nutzen kann.
+- Git-Branch `Wissensnetz` verwenden (auschecken/anlegen, falls nötig), kleine Commits.
+
+## Wo was liegt (zum Verstehen lesen, nicht ändern)
+- Ontologie/TBox (unser): `wissensnetz/ontology/databridge-core.ttl`,
+  `ontology/alignment/ncit_primary_diagnosis.json`, `ontology/README.md`
+  (Namespace `db:` = `http://databridge.hka/onto#`, Instanzen
+  `http://databridge.hka/instance/`).
+- Turtle-Erzeugung von B (nur als Referenz): `mediator/app/semantic/mapping.py`,
+  `mediator/app/main.py` (`/transform`, `/ontology`),
+  `mediator/scripts/example_gdc_to_rdf.py`, `mediator/sample_data/cases_brca_sample.json`.
+- Konzepte (PDF, in `recherche/`): `Wissensnetz_Gesamtueberblick`,
+  `Mapping-Konzept_GDC-zu-RDF-OWL`, `Rueckkanal-Konzept_MP-zu-RDF`.
+- Entscheidung Graph-Modell: `docs/adr/0002-graph-db-wahl-offen.md` (RDF/OWL + RDF-star).
+- Infrastruktur: `docker-compose.yml` (Service `graph-db`), `.env.example`, `graph-db/README.md`.
+
+## Technik & Fuseki-Konfiguration
+- `rdflib` (Graph bauen/serialisieren) + `requests`/`SPARQLWrapper` für Fuseki-HTTP
+  (SPARQL Query, SPARQL Update, Graph Store Protocol).
+- Fuseki (`graph-db`): lokal `http://localhost:3030`, in Compose `http://graph-db:3030`;
+  Dataset `databridge` (ENV `GRAPH_DB_DATASET`), Admin-Passwort `admin`.
+  Konfiguration über ENV lesen (Muster wie `.env.example`).
+- **RDF-star-Falle:** `serialize_with_provenance` hängt `<< s p o >>`-Blöcke als
+  Text an — das ist KEIN gültiges Turtle 1.1; rdflib parst es je nach Version nicht.
+  Solche Ausgaben direkt in Fuseki laden (nativer RDF-star-Support, ADR-0002) bzw.
+  für den Rückkanal SPARQL-star-INSERT nutzen; verifizieren, dass die Aussagen
+  wieder abfragbar sind.
diff --git a/wissensnetz/README.md b/wissensnetz/README.md
new file mode 100644
index 0000000..671d714
--- /dev/null
+++ b/wissensnetz/README.md
@@ -0,0 +1,130 @@
+# Wissensnetz — RDF-Store, SPARQL & Rückkanal
+
+Teilbereich **Wissensnetz** des DataBridge-Projekts: besitzt den RDF-Store
+(Apache Jena Fuseki, Service `graph-db`) und seine Lese-/Schreib-Oberfläche.
+
+**Komponentengrenze:** Der Mediator produziert RDF/Turtle, das Wissensnetz
+konsumiert es. Die Naht ist RDF/Turtle; kommuniziert wird ausschließlich per
+HTTP/SPARQL gegen `graph-db`. Dieses Paket importiert **keinen** Code aus
+`mediator/` oder `wrappers/` und baut das GDC→RDF-Mapping **nicht** nach.
+Kontext/Regeln: [`CLAUDE.md`](CLAUDE.md), Aufgaben:
+[`TASKS_wissensnetz.md`](TASKS_wissensnetz.md).
+
+## Installation
+
+Eigenständiges, installierbares Python-Paket (Muster wie `wrappers/`):
+
+```bash
+python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
+pip install -e ./wissensnetz
+```
+
+Konfiguration über Umgebungsvariablen (siehe `.env.example`, Abschnitt
+`graph-db`): `GRAPH_DB_URL` (Default `http://localhost:3030`),
+`GRAPH_DB_DATASET` (`databridge`), `GRAPH_DB_ADMIN_USER`/`GRAPH_DB_ADMIN_PASSWORD`
+(`admin`/`admin`, für Schreibzugriffe).
+
+## End-to-End-Ablauf
+
+```bash
+# 1) Store starten (legt das persistente TDB2-Dataset 'databridge' an)
+docker compose up -d graph-db
+
+# 2) Dataset sicherstellen + TBox (databridge-core.ttl) laden
+wissensnetz init
+
+# 3) Beispiel-ABox laden (eingefrorene Mediator-Ausgabe, s. u.)
+wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl
+
+# 4) Abfragen
+wissensnetz query "SELECT ?sid ?label WHERE {
+  ?c a db:Case ; db:submitterId ?sid ; db:hasDiagnosis ?d .
+  ?d db:primaryDiagnosisLabel ?label } ORDER BY ?sid"
+
+# Status jederzeit prüfen:
+wissensnetz status
+```
+
+Schritt 2 ist **idempotent** (bereits geladene TBox wird übersprungen,
+`--force` erzwingt Neuladen). Die Standard-PREFIXE (`db:`, `ncit:`, `prov:`,
+`owl:`, `rdfs:`, …) stellt `wissensnetz query` automatisch voran (`--raw`
+schaltet das ab).
+
+Die Beispieldaten unter [`data/sample/cases_brca_sample.ttl`](data/sample/cases_brca_sample.ttl)
+sind die **eingefrorene Turtle-Ausgabe des Mediators**
+(`mediator/scripts/example_gdc_to_rdf.py` bzw. `POST /transform`), nicht selbst
+erzeugt — sie dienen als Fixture zum Laden/Abfragen. Alternativ direkt aus dem
+Mediator laden:
+
+```bash
+# Turtle vom Mediator erzeugen und in den Store laden
+python mediator/scripts/example_gdc_to_rdf.py           # schreibt scripts/output/tcga_brca_sample.ttl
+wissensnetz load mediator/scripts/output/tcga_brca_sample.ttl
+```
+
+## CLI
+
+| Befehl | Zweck |
+| --- | --- |
+| `wissensnetz status` | Erreichbarkeit, Dataset und TBox prüfen |
+| `wissensnetz init [--force]` | Dataset sicherstellen + TBox laden (Aufgabe 1) |
+| `wissensnetz load <datei.ttl \| ->` | Turtle laden, `--graph <IRI>` für Named Graph (Aufgabe 2) |
+| `wissensnetz query "<SPARQL>"` | SELECT/ASK ausführen, `--raw` ohne PREFIXE (Aufgabe 2) |
+
+## Python-API
+
+```python
+from wissensnetz import GraphStore, initialize
+
+store = GraphStore()          # liest Verbindung aus ENV
+initialize(store)             # Dataset + TBox (Aufgabe 1)
+store.load_turtle("data/sample/cases_brca_sample.ttl")   # Aufgabe 2
+rows = store.query("PREFIX db: <http://databridge.hka/onto#> "
+                   "SELECT ?c WHERE { ?c a db:Case }")
+```
+
+`load_turtle` überträgt den Turtle-Text **roh** an Fuseki (kein rdflib-
+Roundtrip), damit RDF-star-Ausgaben (`<< s p o >>`, Provenienz/Konfidenz aus
+dem Mediator) erhalten bleiben — Fuseki hat nativen RDF-star-Support
+(siehe [ADR-0002](../docs/adr/0002-graph-db-wahl-offen.md) und CLAUDE.md,
+„RDF-star-Falle").
+
+## Tests
+
+```bash
+pip install -e "./wissensnetz[test]"
+cd wissensnetz && pytest
+```
+
+Die Tests laufen gegen ein **laufendes Fuseki** und decken Laden + Abfragen ab
+(Aufgabe 1: TBox-Klassen abfragbar; Aufgabe 2: Beispiel-Cases/Diagnosen). Ist
+kein Fuseki erreichbar, werden sie **übersprungen** (kein Fehler) — praktisch
+für CI ohne Store.
+
+## Verzeichnisstruktur
+
+```
+wissensnetz/
+  pyproject.toml            # installierbares Paket "wissensnetz"
+  requirements.txt
+  README.md                 # dieses Dokument
+  src/wissensnetz/
+    config.py               # Fuseki-URL, Dataset, Namespaces aus ENV
+    graphstore.py           # (2) Fuseki-Client: load_turtle / query / update
+    init.py                 # (1) Dataset sicherstellen + TBox laden
+    cli.py                  # CLI-Einstieg
+  ontology/                 # TBox databridge-core.ttl + Alignment (vorhanden)
+  data/sample/              # eingefrorene Mediator-Turtle-Ausgabe (Fixture)
+  tests/                    # pytest (Skip ohne laufendes Fuseki)
+```
+
+## Stand / Nächste Schritte
+
+- **Aufgabe 1 (Dataset + TBox-Init):** umgesetzt.
+- **Aufgabe 2 (Graphstore-Client):** umgesetzt.
+- **Aufgabe 3 (SPARQL-Anreicherung, Lesen):** offen — `enrichment.py` +
+  `wissensnetz query`-Erweiterungen (Klassen-/Krankheitshierarchie,
+  Fall-/Diagnose-Kontext).
+- **Aufgabe 4 (Rückkanal, Schreiben):** offen — `feedback.py` (MP-Selektions-
+  Event → `oa:Annotation`/PROV-O/RDF-star, SPARQL-star-INSERT in Named Graph
+  pro Nutzer). `graphstore.update()` steht dafür bereit.
diff --git a/wissensnetz/TASKS_wissensnetz.md b/wissensnetz/TASKS_wissensnetz.md
new file mode 100644
index 0000000..0621d54
--- /dev/null
+++ b/wissensnetz/TASKS_wissensnetz.md
@@ -0,0 +1,72 @@
+# Aufgaben: Wissensnetz — Triple-Store, SPARQL & Rückkanal
+
+> Kontext und harte Regeln stehen in `wissensnetz/CLAUDE.md` (bitte zuerst
+> beachten). Diese Datei ist die konkrete Arbeitsanweisung. Vor Beginn die unter
+> „Wo was liegt“ in `CLAUDE.md` genannten Dateien lesen, um Turtle-Format und
+> TBox zu verstehen.
+
+## Zielstruktur (Vorschlag, anpassbar)
+```
+wissensnetz/
+  pyproject.toml            # installierbares Paket "wissensnetz"
+  README.md                 # Setup + End-to-End-Ablauf
+  requirements.txt
+  src/wissensnetz/
+    config.py               # Fuseki-URL, Dataset, Namespaces aus ENV
+    graphstore.py           # (2) Fuseki-Client: load_turtle / query / update
+    enrichment.py           # (3) vordefinierte SPARQL-Abfragen
+    feedback.py             # (4) Rückkanal: Selektion→RDF, write/readback
+    cli.py                  # CLI-Einstieg für alle Schritte
+  init/                     # (1) Fuseki-Dataset-Konfiguration
+  data/sample/              # simuliertes MP-Selektions-Event (JSON)
+  tests/                    # pytest je Aufgabe
+```
+
+## Aufgaben (in Reihenfolge, jede mit Abnahmekriterium)
+
+### 1 — Fuseki-Dataset & TBox-Initialisierung
+Dataset `databridge` beim Start anlegen (Assembler-`.ttl` unter `graph-db/init/`
+ODER passende `FUSEKI_DATASET_*`-ENV — wähle den Weg, der zum `stain/jena-fuseki`-
+Image passt, und dokumentiere ihn) und die TBox
+`wissensnetz/ontology/databridge-core.ttl` laden.
+**Abnahme:** nach `docker compose up graph-db` existiert das Dataset und eine
+SPARQL-Abfrage liefert die TBox-Klassen (`db:Case`, `db:Diagnosis`, …).
+
+### 2 — Graphstore-Client
+`graphstore.py`: `load_turtle(text_or_path, graph=None)`, `query(sparql) -> rows`,
+`update(sparql)`. Turtle-Ausgabe aus `mediator/scripts/example_gdc_to_rdf.py` bzw.
+`POST /transform` in Fuseki laden.
+**Abnahme:** Beispieldaten geladen, `query` liefert die erwarteten Cases/Diagnosen
+zurück. Pytest deckt load+query gegen ein laufendes Fuseki ab (Skip, wenn nicht
+erreichbar).
+
+### 3 — SPARQL-Anreicherung (Lesen)
+`enrichment.py`: mindestens (a) Klassen-/Krankheitshierarchie via
+`rdfs:subClassOf*`, (b) Fall-/Diagnose-Kontext zu einer gegebenen Case-/Diagnosis-
+IRI (verknüpfte Konzepte + Alignment-Ziele). Als Funktionen + CLI
+(`wissensnetz query ...`).
+**Abnahme:** korrekte Ergebnismengen gegen die geladenen Beispieldaten; Tests vorhanden.
+
+### 4 — Rückkanal (Schreiben)
+`feedback.py`: simuliertes MP-Selektions-Event
+(`data/sample/selection_event.json`; Felder: Nutzer, Probenmenge, Hypothese/
+Reclassification from→to, Sicht, Morph-t, Konfidenz, Zeit) → RDF als
+`oa:Annotation` + PROV-O + RDF-star, geschrieben per SPARQL Update in einen
+**Named Graph pro Nutzer**; plus Rück-Abfrage. Modellierung nach
+`recherche/Rueckkanal-Konzept_MP-zu-RDF`.
+**Abnahme:** Event wird geschrieben und ist per SPARQL wieder auslesbar; Test vorhanden.
+
+### Querschnitt
+`wissensnetz/README.md` mit End-to-End-Ablauf (`docker compose up graph-db` → init
+→ load → query → feedback), `requirements.txt`, CLI-Einstieg, `pytest` grün.
+`graph-db/README.md` um den gewählten Init-Weg ergänzen.
+
+## Definition of Done
+`docker compose up graph-db` → Init legt Dataset+TBox an → Beispiel-Turtle geladen
+→ eine SPARQL-Abfrage liefert erwartete Zeilen → ein Rückkanal-Event wird
+geschrieben und zurückgelesen → alle Tests grün → README dokumentiert die Schritte.
+Mediator/Wrapper unverändert.
+
+## Empfohlener Einstieg
+Zuerst **Aufgabe 1 + 2** umsetzen (Fuseki nutzbar machen + Store-Client), dann
+Rückfrage/Review, danach 3 und 4.
diff --git a/wissensnetz/data/sample/cases_brca_sample.ttl b/wissensnetz/data/sample/cases_brca_sample.ttl
new file mode 100644
index 0000000..0d73716
--- /dev/null
+++ b/wissensnetz/data/sample/cases_brca_sample.ttl
@@ -0,0 +1,86 @@
+# TCGA-BRCA-Beispiel-ABox — EINGEFRORENE Ausgabe des Mediators, KEINE eigene
+# Mapping-Logik. Erzeugt von mediator/scripts/example_gdc_to_rdf.py
+# (== POST /transform) aus mediator/sample_data/cases_brca_sample.json.
+#
+# Diese Datei ist eine Referenz-Fixture für das Wissensnetz (Aufgabe 2): Sie
+# wird per graphstore.load_turtle() in Fuseki geladen und in Tests abgefragt.
+# Bei Änderungen am Mapping neu aus dem Mediator ziehen — hier NICHT von Hand
+# pflegen (Komponentengrenze: der Mediator besitzt das GDC->RDF-Mapping).
+#
+# Alignment-Tabelle war leer -> primary_diagnosis nur als Literal
+# (db:primaryDiagnosisLabel), kein db:primaryDiagnosis/NCIt und daher auch
+# keine RDF-star-Bloecke. 58 Tripel aus 4 Cases.
+
+@prefix db: <http://databridge.hka/onto#> .
+@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
+
+<http://databridge.hka/instance/demographic/11111111-1111-4111-8111-111111111111> a db:Demographic ;
+    db:gender "female"^^xsd:string ;
+    db:isDemographicOf <http://databridge.hka/instance/case/11111111-1111-4111-8111-111111111111> .
+
+<http://databridge.hka/instance/demographic/22222222-2222-4222-8222-222222222222> a db:Demographic ;
+    db:gender "female"^^xsd:string ;
+    db:isDemographicOf <http://databridge.hka/instance/case/22222222-2222-4222-8222-222222222222> .
+
+<http://databridge.hka/instance/demographic/33333333-3333-4333-8333-333333333333> a db:Demographic ;
+    db:gender "female"^^xsd:string ;
+    db:isDemographicOf <http://databridge.hka/instance/case/33333333-3333-4333-8333-333333333333> .
+
+<http://databridge.hka/instance/demographic/44444444-4444-4444-8444-444444444444> a db:Demographic ;
+    db:gender "male"^^xsd:string ;
+    db:isDemographicOf <http://databridge.hka/instance/case/44444444-4444-4444-8444-444444444444> .
+
+<http://databridge.hka/instance/diagnosis/d-11111111> a db:Diagnosis ;
+    db:ageAtDiagnosis 21200 ;
+    db:describesCase <http://databridge.hka/instance/case/11111111-1111-4111-8111-111111111111> ;
+    db:primaryDiagnosisLabel "Infiltrating duct carcinoma, NOS"^^xsd:string .
+
+<http://databridge.hka/instance/diagnosis/d-22222222> a db:Diagnosis ;
+    db:ageAtDiagnosis 19870 ;
+    db:describesCase <http://databridge.hka/instance/case/22222222-2222-4222-8222-222222222222> ;
+    db:primaryDiagnosisLabel "Lobular carcinoma, NOS"^^xsd:string .
+
+<http://databridge.hka/instance/diagnosis/d-33333333> a db:Diagnosis ;
+    db:ageAtDiagnosis 25630 ;
+    db:describesCase <http://databridge.hka/instance/case/33333333-3333-4333-8333-333333333333> ;
+    db:primaryDiagnosisLabel "Infiltrating duct carcinoma, NOS"^^xsd:string .
+
+<http://databridge.hka/instance/diagnosis/d-44444444> a db:Diagnosis ;
+    db:ageAtDiagnosis 23360 ;
+    db:describesCase <http://databridge.hka/instance/case/44444444-4444-4444-8444-444444444444> ;
+    db:primaryDiagnosisLabel "Adenocarcinoma, NOS"^^xsd:string .
+
+<http://databridge.hka/instance/case/11111111-1111-4111-8111-111111111111> a db:Case ;
+    db:belongsToProject <http://databridge.hka/instance/project/TCGA-BRCA> ;
+    db:caseId "11111111-1111-4111-8111-111111111111"^^xsd:string ;
+    db:hasDemographic <http://databridge.hka/instance/demographic/11111111-1111-4111-8111-111111111111> ;
+    db:hasDiagnosis <http://databridge.hka/instance/diagnosis/d-11111111> ;
+    db:submitterId "TCGA-A1-A0SB"^^xsd:string .
+
+<http://databridge.hka/instance/case/22222222-2222-4222-8222-222222222222> a db:Case ;
+    db:belongsToProject <http://databridge.hka/instance/project/TCGA-BRCA> ;
+    db:caseId "22222222-2222-4222-8222-222222222222"^^xsd:string ;
+    db:hasDemographic <http://databridge.hka/instance/demographic/22222222-2222-4222-8222-222222222222> ;
+    db:hasDiagnosis <http://databridge.hka/instance/diagnosis/d-22222222> ;
+    db:submitterId "TCGA-A1-A0SD"^^xsd:string .
+
+<http://databridge.hka/instance/case/33333333-3333-4333-8333-333333333333> a db:Case ;
+    db:belongsToProject <http://databridge.hka/instance/project/TCGA-BRCA> ;
+    db:caseId "33333333-3333-4333-8333-333333333333"^^xsd:string ;
+    db:hasDemographic <http://databridge.hka/instance/demographic/33333333-3333-4333-8333-333333333333> ;
+    db:hasDiagnosis <http://databridge.hka/instance/diagnosis/d-33333333> ;
+    db:submitterId "TCGA-A1-A0SE"^^xsd:string .
+
+<http://databridge.hka/instance/case/44444444-4444-4444-8444-444444444444> a db:Case ;
+    db:belongsToProject <http://databridge.hka/instance/project/TCGA-BRCA> ;
+    db:caseId "44444444-4444-4444-8444-444444444444"^^xsd:string ;
+    db:hasDemographic <http://databridge.hka/instance/demographic/44444444-4444-4444-8444-444444444444> ;
+    db:hasDiagnosis <http://databridge.hka/instance/diagnosis/d-44444444> ;
+    db:submitterId "TCGA-A1-A0SH"^^xsd:string .
+
+<http://databridge.hka/instance/project/TCGA-BRCA> a db:Project ;
+    db:hasCase <http://databridge.hka/instance/case/11111111-1111-4111-8111-111111111111>,
+        <http://databridge.hka/instance/case/22222222-2222-4222-8222-222222222222>,
+        <http://databridge.hka/instance/case/33333333-3333-4333-8333-333333333333>,
+        <http://databridge.hka/instance/case/44444444-4444-4444-8444-444444444444> ;
+    db:projectId "TCGA-BRCA"^^xsd:string .
diff --git a/wissensnetz/pyproject.toml b/wissensnetz/pyproject.toml
new file mode 100644
index 0000000..068b374
--- /dev/null
+++ b/wissensnetz/pyproject.toml
@@ -0,0 +1,28 @@
+[build-system]
+requires = ["setuptools>=68"]
+build-backend = "setuptools.build_meta"
+
+[project]
+name = "wissensnetz"
+version = "0.1.0"
+description = "RDF-Store-, SPARQL- und Rückkanal-Schicht des DataBridge-Wissensnetzes (Fuseki/Jena)."
+requires-python = ">=3.11"
+dependencies = [
+    "rdflib>=7",
+    "requests>=2.28",
+]
+
+# Eigenständiges, installierbares Paket (Muster wie wrappers/pyproject.toml).
+# Der Mediator kann es später optional per `pip install -e ./wissensnetz`
+# nutzen — Abhängigkeitsrichtung bleibt Mediator -> Wissensnetz.
+[project.optional-dependencies]
+test = ["pytest>=7"]
+
+[project.scripts]
+wissensnetz = "wissensnetz.cli:main"
+
+[tool.setuptools.packages.find]
+where = ["src"]
+
+[tool.pytest.ini_options]
+testpaths = ["tests"]
diff --git a/wissensnetz/requirements.txt b/wissensnetz/requirements.txt
new file mode 100644
index 0000000..98ce839
--- /dev/null
+++ b/wissensnetz/requirements.txt
@@ -0,0 +1,8 @@
+# Laufzeit-Abhängigkeiten des Wissensnetz-Pakets.
+# Installation als Paket bevorzugt:  pip install -e ./wissensnetz
+# (dann werden diese Abhängigkeiten aus pyproject.toml gezogen).
+rdflib>=7
+requests>=2.28
+
+# Tests:
+pytest>=7
diff --git a/wissensnetz/src/wissensnetz/__init__.py b/wissensnetz/src/wissensnetz/__init__.py
new file mode 100644
index 0000000..75f7e40
--- /dev/null
+++ b/wissensnetz/src/wissensnetz/__init__.py
@@ -0,0 +1,15 @@
+"""Wissensnetz — RDF-Store, SPARQL und Rückkanal des DataBridge-Projekts.
+
+Öffentliche API (Aufgabe 1 + 2):
+
+    from wissensnetz import GraphStore, Settings, initialize
+"""
+
+from __future__ import annotations
+
+from .config import Settings
+from .graphstore import GraphStore, GraphStoreError
+from .init import initialize
+
+__all__ = ["GraphStore", "GraphStoreError", "Settings", "initialize"]
+__version__ = "0.1.0"
diff --git a/wissensnetz/src/wissensnetz/cli.py b/wissensnetz/src/wissensnetz/cli.py
new file mode 100644
index 0000000..494830a
--- /dev/null
+++ b/wissensnetz/src/wissensnetz/cli.py
@@ -0,0 +1,131 @@
+"""CLI-Einstieg für das Wissensnetz (``wissensnetz ...``).
+
+Aktuell umgesetzt (Aufgabe 1 + 2):
+
+    wissensnetz status                 Erreichbarkeit + Dataset/TBox prüfen
+    wissensnetz init [--force]         Dataset sicherstellen + TBox laden
+    wissensnetz load <datei.ttl|->     Turtle laden (Default- oder Named Graph)
+    wissensnetz query "<SPARQL>"       SELECT/ASK ausführen (Tabellen-Ausgabe)
+
+Die Unterbefehle für Anreicherung (Aufgabe 3) und Rückkanal (Aufgabe 4)
+folgen in eigenen Modulen und werden hier ergänzt.
+"""
+
+from __future__ import annotations
+
+import argparse
+import sys
+from pathlib import Path
+
+from .config import PREFIXES, Settings
+from .graphstore import GraphStore, GraphStoreError
+from .init import initialize, tbox_loaded
+
+
+def _build_parser() -> argparse.ArgumentParser:
+    parser = argparse.ArgumentParser(
+        prog="wissensnetz",
+        description="RDF-Store-Werkzeuge des DataBridge-Wissensnetzes (Fuseki/SPARQL).",
+    )
+    sub = parser.add_subparsers(dest="command", required=True)
+
+    sub.add_parser("status", help="Erreichbarkeit, Dataset und TBox prüfen")
+
+    p_init = sub.add_parser("init", help="Dataset sicherstellen und TBox laden")
+    p_init.add_argument("--force", action="store_true", help="TBox neu laden, auch wenn vorhanden")
+
+    p_load = sub.add_parser("load", help="Turtle-Datei laden ('-' = stdin)")
+    p_load.add_argument("source", help="Pfad zur .ttl-Datei oder '-' für stdin")
+    p_load.add_argument("--graph", default=None, help="IRI eines Named Graph (Default: Default-Graph)")
+
+    p_query = sub.add_parser("query", help="SPARQL SELECT/ASK ausführen")
+    p_query.add_argument("sparql", help="SPARQL-Abfrage; Standard-PREFIXE werden vorangestellt")
+    p_query.add_argument(
+        "--raw",
+        action="store_true",
+        help="Abfrage unverändert senden (keine PREFIXE voranstellen)",
+    )
+
+    return parser
+
+
+def _cmd_status(store: GraphStore) -> int:
+    s = store.settings
+    print(f"Fuseki:  {s.base_url}  (Dataset '{s.dataset}')")
+    if not store.is_reachable():
+        print("Status:  NICHT erreichbar — läuft 'docker compose up graph-db'?")
+        return 1
+    print("Status:  erreichbar")
+    try:
+        exists = store.dataset_exists()
+    except GraphStoreError as exc:
+        print(f"Dataset: unbekannt ({exc})")
+        return 1
+    print(f"Dataset: {'vorhanden' if exists else 'FEHLT (init ausführen)'}")
+    if exists:
+        print(f"TBox:    {'geladen' if tbox_loaded(store) else 'nicht geladen (init ausführen)'}")
+    return 0
+
+
+def _cmd_init(store: GraphStore, force: bool) -> int:
+    report = initialize(store, force=force)
+    print(f"Dataset '{report['dataset']}': "
+          f"{'neu angelegt' if report['dataset_created'] else 'bereits vorhanden'}")
+    print(f"TBox:    {report['tbox']}")
+    print(f"Klassen: {report['owl_classes']} owl:Class im Store")
+    return 0
+
+
+def _cmd_load(store: GraphStore, source: str, graph: str | None) -> int:
+    if source == "-":
+        turtle = sys.stdin.read()
+        store.load_turtle(turtle, graph=graph)
+        origin = "stdin"
+    else:
+        path = Path(source)
+        if not path.exists():
+            print(f"Datei nicht gefunden: {path}", file=sys.stderr)
+            return 1
+        store.load_turtle(path, graph=graph)
+        origin = str(path)
+    target = f"Named Graph <{graph}>" if graph else "Default-Graph"
+    print(f"Geladen: {origin} -> {target}")
+    return 0
+
+
+def _cmd_query(store: GraphStore, sparql: str, raw: bool) -> int:
+    full = sparql if raw else PREFIXES + sparql
+    rows = store.query(full)
+    if not rows:
+        print("(keine Ergebnisse)")
+        return 0
+    columns = list(rows[0].keys())
+    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in columns}
+    print("  ".join(c.ljust(widths[c]) for c in columns))
+    print("  ".join("-" * widths[c] for c in columns))
+    for r in rows:
+        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))
+    print(f"\n{len(rows)} Zeile(n)")
+    return 0
+
+
+def main(argv: list[str] | None = None) -> int:
+    args = _build_parser().parse_args(argv)
+    store = GraphStore(Settings.from_env())
+    try:
+        if args.command == "status":
+            return _cmd_status(store)
+        if args.command == "init":
+            return _cmd_init(store, args.force)
+        if args.command == "load":
+            return _cmd_load(store, args.source, args.graph)
+        if args.command == "query":
+            return _cmd_query(store, args.sparql, args.raw)
+    except (GraphStoreError, FileNotFoundError) as exc:
+        print(f"Fehler: {exc}", file=sys.stderr)
+        return 1
+    return 2  # unbekannter Befehl (argparse fängt das eigentlich vorher ab)
+
+
+if __name__ == "__main__":
+    raise SystemExit(main())
diff --git a/wissensnetz/src/wissensnetz/config.py b/wissensnetz/src/wissensnetz/config.py
new file mode 100644
index 0000000..78d5d83
--- /dev/null
+++ b/wissensnetz/src/wissensnetz/config.py
@@ -0,0 +1,85 @@
+"""Konfiguration des Wissensnetz-Clients (Fuseki-Anbindung + Namespaces).
+
+Alles wird aus Umgebungsvariablen gelesen (Muster wie ``.env.example`` im
+Repo-Root). Innerhalb von Docker Compose zeigt ``GRAPH_DB_URL`` auf
+``http://graph-db:3030`` (Service-Name), außerhalb auf ``localhost``.
+
+Komponentengrenze: Dieses Paket spricht ausschließlich per HTTP/SPARQL gegen
+den ``graph-db``-Service (Apache Jena Fuseki). Es importiert keinen Code aus
+``mediator/`` oder ``wrappers/``.
+"""
+
+from __future__ import annotations
+
+import os
+from dataclasses import dataclass
+
+# --- Namespaces (identisch zur TBox databridge-core.ttl / Mediator-Mapping) ---
+DB = "http://databridge.hka/onto#"
+INSTANCE = "http://databridge.hka/instance/"
+NCIT = "http://purl.obolibrary.org/obo/NCIT_"
+PROV = "http://www.w3.org/ns/prov#"
+OA = "http://www.w3.org/ns/oa#"
+
+# Für SPARQL-Abfragen wiederverwendbarer PREFIX-Block.
+PREFIXES = f"""\
+PREFIX db:   <{DB}>
+PREFIX ncit: <{NCIT}>
+PREFIX prov: <{PROV}>
+PREFIX oa:   <{OA}>
+PREFIX owl:  <http://www.w3.org/2002/07/owl#>
+PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
+PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
+PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
+"""
+
+
+def _default_base_url() -> str:
+    """Basis-URL aus ``GRAPH_DB_URL`` oder aus Host/Port zusammengesetzt."""
+    explicit = os.environ.get("GRAPH_DB_URL")
+    if explicit:
+        return explicit.rstrip("/")
+    host = os.environ.get("GRAPH_DB_HOST", "localhost")
+    port = os.environ.get("GRAPH_DB_PORT", "3030")
+    return f"http://{host}:{port}"
+
+
+@dataclass(frozen=True)
+class Settings:
+    """Verbindungsparameter für den Fuseki-Store."""
+
+    base_url: str
+    dataset: str
+    admin_user: str
+    admin_password: str
+
+    @classmethod
+    def from_env(cls) -> "Settings":
+        return cls(
+            base_url=_default_base_url(),
+            dataset=os.environ.get("GRAPH_DB_DATASET", "databridge"),
+            admin_user=os.environ.get("GRAPH_DB_ADMIN_USER", "admin"),
+            admin_password=os.environ.get("GRAPH_DB_ADMIN_PASSWORD", "admin"),
+        )
+
+    # --- abgeleitete Endpunkt-URLs (Fuseki-Konvention) ---
+    @property
+    def query_url(self) -> str:
+        return f"{self.base_url}/{self.dataset}/query"
+
+    @property
+    def update_url(self) -> str:
+        return f"{self.base_url}/{self.dataset}/update"
+
+    @property
+    def gsp_url(self) -> str:
+        """Graph Store Protocol-Endpunkt (Laden von Turtle)."""
+        return f"{self.base_url}/{self.dataset}/data"
+
+    @property
+    def admin_datasets_url(self) -> str:
+        return f"{self.base_url}/$/datasets"
+
+    @property
+    def ping_url(self) -> str:
+        return f"{self.base_url}/$/ping"
diff --git a/wissensnetz/src/wissensnetz/graphstore.py b/wissensnetz/src/wissensnetz/graphstore.py
new file mode 100644
index 0000000..c503e4e
--- /dev/null
+++ b/wissensnetz/src/wissensnetz/graphstore.py
@@ -0,0 +1,169 @@
+"""Graphstore-Client (Aufgabe 2): HTTP-Zugriff auf den Fuseki-``graph-db``.
+
+Drei Kern-Operationen entlang der Aufgabenstellung:
+
+* :meth:`GraphStore.load_turtle` — Turtle in den Store laden (Graph Store
+  Protocol). Der Text wird **roh** an Fuseki gesendet, nicht durch rdflib
+  geparst/re-serialisiert — so bleibt auch RDF-star-Turtle
+  (``<< s p o >>``-Blöcke aus dem Mediator) erhalten, das rdflib je nach
+  Version nicht parst (siehe CLAUDE.md, "RDF-star-Falle"; ADR-0002:
+  natives RDF-star in Fuseki).
+* :meth:`GraphStore.query` — SELECT/ASK-Abfrage, Ergebnis als Liste von
+  ``{variable: wert}``-Dicts (SPARQL-JSON-Results).
+* :meth:`GraphStore.update` — SPARQL Update (INSERT/DELETE), z. B. für den
+  Rückkanal (Aufgabe 4).
+
+Kommunikation ausschließlich per HTTP/SPARQL gegen den ``graph-db``-Service.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+from typing import Any
+
+import requests
+
+from .config import Settings
+
+# Fuseki akzeptiert Turtle-star unter dem Turtle-Media-Type.
+_TURTLE = "text/turtle"
+_SPARQL_JSON = "application/sparql-results+json"
+
+
+class GraphStoreError(RuntimeError):
+    """Fehler bei der Kommunikation mit dem Fuseki-Store."""
+
+
+class GraphStore:
+    """Dünner Fuseki-Client über die drei SPARQL-/GSP-HTTP-Endpunkte."""
+
+    def __init__(self, settings: Settings | None = None, *, timeout: float = 30.0) -> None:
+        self.settings = settings or Settings.from_env()
+        self.timeout = timeout
+        self._session = requests.Session()
+
+    # -- Verfügbarkeit -----------------------------------------------------
+    def is_reachable(self) -> bool:
+        """True, wenn der Fuseki-Server antwortet (für Test-Skips/CLI)."""
+        try:
+            resp = self._session.get(self.settings.ping_url, timeout=self.timeout)
+            return resp.ok
+        except requests.RequestException:
+            return False
+
+    # -- Lesen -------------------------------------------------------------
+    def query(self, sparql: str) -> list[dict[str, Any]]:
+        """Führt eine SELECT/ASK-Abfrage aus und liefert vereinfachte Zeilen.
+
+        SELECT -> Liste von Dicts ``{var: wert}`` (Wert = Literal-/IRI-String).
+        ASK    -> ``[{"boolean": True/False}]``.
+        """
+        resp = self._session.post(
+            self.settings.query_url,
+            data={"query": sparql},
+            headers={"Accept": _SPARQL_JSON},
+            timeout=self.timeout,
+        )
+        self._raise_for_status(resp, "SPARQL-Query fehlgeschlagen")
+        payload = resp.json()
+
+        if "boolean" in payload:
+            return [{"boolean": payload["boolean"]}]
+
+        rows: list[dict[str, Any]] = []
+        for binding in payload.get("results", {}).get("bindings", []):
+            rows.append({var: cell.get("value") for var, cell in binding.items()})
+        return rows
+
+    def ask(self, sparql: str) -> bool:
+        """Bequemer Wrapper für ASK-Abfragen."""
+        result = self.query(sparql)
+        return bool(result and result[0].get("boolean"))
+
+    # -- Schreiben ---------------------------------------------------------
+    def update(self, sparql: str) -> None:
+        """Führt ein SPARQL Update (INSERT/DELETE/LOAD) aus.
+
+        Schreibzugriff ist in Fuseki durch Basic-Auth geschützt
+        (shiro.ini: ``/*/update/**`` = admin), daher mit Admin-Credentials.
+        """
+        resp = self._session.post(
+            self.settings.update_url,
+            data={"update": sparql},
+            auth=self._admin_auth(),
+            timeout=self.timeout,
+        )
+        self._raise_for_status(resp, "SPARQL-Update fehlgeschlagen")
+
+    def load_turtle(self, text_or_path: str | Path, graph: str | None = None) -> None:
+        """Lädt Turtle in den Store (Graph Store Protocol, POST = anhängen).
+
+        ``text_or_path`` ist entweder Turtle-Text oder ein Pfad zu einer
+        ``.ttl``-Datei. ``graph`` = IRI eines Named Graph; ohne Angabe wird
+        der Default-Graph beschrieben.
+
+        Der Turtle-Text wird unverändert übertragen (kein rdflib-Roundtrip),
+        damit RDF-star erhalten bleibt.
+        """
+        turtle = self._resolve_turtle(text_or_path)
+        params = {"graph": graph} if graph else {"default": ""}
+        # GSP-Schreibzugriff ist Basic-Auth-geschützt (shiro.ini: /*/data/**).
+        resp = self._session.post(
+            self.settings.gsp_url,
+            params=params,
+            data=turtle.encode("utf-8"),
+            headers={"Content-Type": _TURTLE},
+            auth=self._admin_auth(),
+            timeout=self.timeout,
+        )
+        self._raise_for_status(resp, "Turtle-Load (GSP) fehlgeschlagen")
+
+    # -- Dataset-Verwaltung (Aufgabe 1, Fallback ohne FUSEKI_DATASET_*) -----
+    def dataset_exists(self) -> bool:
+        """Prüft über die Fuseki-Admin-API, ob das Dataset registriert ist."""
+        resp = self._session.get(
+            self.settings.admin_datasets_url,
+            auth=self._admin_auth(),
+            timeout=self.timeout,
+        )
+        self._raise_for_status(resp, "Dataset-Liste konnte nicht gelesen werden")
+        names = {ds.get("ds.name") for ds in resp.json().get("datasets", [])}
+        return f"/{self.settings.dataset}" in names or self.settings.dataset in names
+
+    def create_dataset(self, *, db_type: str = "tdb2") -> None:
+        """Legt das Dataset persistent an (idempotent: 409 wird toleriert)."""
+        resp = self._session.post(
+            self.settings.admin_datasets_url,
+            params={"dbName": self.settings.dataset, "dbType": db_type},
+            auth=self._admin_auth(),
+            timeout=self.timeout,
+        )
+        if resp.status_code == 409:  # existiert bereits
+            return
+        self._raise_for_status(resp, "Dataset konnte nicht angelegt werden")
+
+    def ensure_dataset(self, *, db_type: str = "tdb2") -> bool:
+        """Stellt sicher, dass das Dataset existiert. True = neu angelegt."""
+        if self.dataset_exists():
+            return False
+        self.create_dataset(db_type=db_type)
+        return True
+
+    # -- intern ------------------------------------------------------------
+    def _admin_auth(self) -> tuple[str, str]:
+        return (self.settings.admin_user, self.settings.admin_password)
+
+    @staticmethod
+    def _resolve_turtle(text_or_path: str | Path) -> str:
+        if isinstance(text_or_path, Path):
+            return text_or_path.read_text(encoding="utf-8")
+        candidate = Path(text_or_path)
+        # Nur als Pfad behandeln, wenn es plausibel einer ist und existiert.
+        if len(str(text_or_path)) < 260 and candidate.suffix == ".ttl" and candidate.exists():
+            return candidate.read_text(encoding="utf-8")
+        return str(text_or_path)
+
+    @staticmethod
+    def _raise_for_status(resp: requests.Response, context: str) -> None:
+        if not resp.ok:
+            raise GraphStoreError(f"{context}: HTTP {resp.status_code} — {resp.text[:500]}")
diff --git a/wissensnetz/src/wissensnetz/init.py b/wissensnetz/src/wissensnetz/init.py
new file mode 100644
index 0000000..8676c82
--- /dev/null
+++ b/wissensnetz/src/wissensnetz/init.py
@@ -0,0 +1,68 @@
+"""Initialisierung des Stores (Aufgabe 1): Dataset sicherstellen + TBox laden.
+
+Ablauf von :func:`initialize`:
+
+1. Dataset ``databridge`` sicherstellen. Regulär legt es bereits der
+   ``graph-db``-Container beim Start an (``FUSEKI_DATASET_1`` im
+   ``stain/jena-fuseki``-Image, siehe ``graph-db/README.md``). Läuft der
+   Container ohne diese Variable, wird das Dataset hier über die Fuseki-
+   Admin-API nachgezogen — so ist ``wissensnetz init`` in sich abgeschlossen.
+2. TBox ``ontology/databridge-core.ttl`` in den Default-Graph laden
+   (idempotent: bei bereits vorhandener TBox übersprungen, außer ``force``).
+
+Die TBox liegt bewusst im selben (Default-)Graph wie später die ABox, damit
+einfache SPARQL-Abfragen Klassen und Instanzen ohne ``GRAPH``-Klausel sehen.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+from .config import PREFIXES
+from .graphstore import GraphStore
+
+# ontology/ liegt im Paket-Repo neben src/ — von hier aus zwei Ebenen hoch.
+_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "ontology"
+TBOX_PATH = _ONTOLOGY_DIR / "databridge-core.ttl"
+
+# Marker-Abfrage: Ist die TBox bereits geladen?
+_TBOX_PRESENT = PREFIXES + "ASK { db:Case a owl:Class }"
+
+
+def tbox_loaded(store: GraphStore) -> bool:
+    """True, wenn die TBox (Marker-Klasse ``db:Case``) im Store vorhanden ist."""
+    return store.ask(_TBOX_PRESENT)
+
+
+def initialize(
+    store: GraphStore | None = None,
+    *,
+    tbox_path: Path = TBOX_PATH,
+    force: bool = False,
+) -> dict[str, object]:
+    """Dataset sicherstellen und TBox laden. Liefert einen Kurzbericht."""
+    store = store or GraphStore()
+
+    if not tbox_path.exists():
+        raise FileNotFoundError(f"TBox-Datei nicht gefunden: {tbox_path}")
+
+    dataset_created = store.ensure_dataset()
+
+    already = tbox_loaded(store)
+    if already and not force:
+        tbox_action = "skipped (bereits vorhanden)"
+    else:
+        store.load_turtle(tbox_path)
+        tbox_action = "reloaded (force)" if already else "loaded"
+
+    class_count = store.query(
+        PREFIXES + "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a owl:Class }"
+    )
+    n_classes = class_count[0].get("n") if class_count else "0"
+
+    return {
+        "dataset": store.settings.dataset,
+        "dataset_created": dataset_created,
+        "tbox": tbox_action,
+        "owl_classes": n_classes,
+    }
diff --git a/wissensnetz/tests/conftest.py b/wissensnetz/tests/conftest.py
new file mode 100644
index 0000000..7399291
--- /dev/null
+++ b/wissensnetz/tests/conftest.py
@@ -0,0 +1,38 @@
+"""Gemeinsame pytest-Fixtures.
+
+Alle Store-Tests laufen gegen ein **laufendes Fuseki**. Ist keins erreichbar
+(z. B. in CI ohne ``docker compose up graph-db``), werden sie übersprungen
+statt zu scheitern — so bleibt die Suite auch ohne Infrastruktur grün.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import pytest
+
+from wissensnetz import GraphStore
+from wissensnetz.init import initialize
+
+SAMPLE_TTL = Path(__file__).resolve().parents[1] / "data" / "sample" / "cases_brca_sample.ttl"
+
+
+@pytest.fixture(scope="session")
+def store() -> GraphStore:
+    """Erreichbarer, initialisierter Store — sonst Skip der gesamten Suite."""
+    gs = GraphStore()
+    if not gs.is_reachable():
+        pytest.skip(
+            f"Fuseki nicht erreichbar unter {gs.settings.base_url} — "
+            "'docker compose up graph-db' und ggf. GRAPH_DB_URL setzen."
+        )
+    # Dataset + TBox sicherstellen (idempotent), damit Tests unabhängig laufen.
+    initialize(gs)
+    return gs
+
+
+@pytest.fixture(scope="session")
+def loaded_store(store: GraphStore) -> GraphStore:
+    """Store mit geladener Beispiel-ABox (idempotent, Tripel-Mengensemantik)."""
+    store.load_turtle(SAMPLE_TTL)
+    return store
diff --git a/wissensnetz/tests/test_graphstore.py b/wissensnetz/tests/test_graphstore.py
new file mode 100644
index 0000000..ae81c7c
--- /dev/null
+++ b/wissensnetz/tests/test_graphstore.py
@@ -0,0 +1,85 @@
+"""Aufgabe 2 — Abnahme: Beispiel-ABox laden und erwartete Cases/Diagnosen lesen.
+
+Die Abfragen sind bewusst auf das Projekt ``TCGA-BRCA`` eingegrenzt, damit sie
+gegen einen **persistenten** Store robust bleiben (andere Daten im Store — z. B.
+aus früheren Läufen oder anderen Projekten — verfälschen die Ergebnismenge dann
+nicht). Das entspricht auch dem realen Zugriff: man fragt seine Teilmenge ab,
+nicht den gesamten Store.
+"""
+
+from __future__ import annotations
+
+from wissensnetz.config import PREFIXES
+from wissensnetz.graphstore import GraphStore
+
+PROJECT = "<http://databridge.hka/instance/project/TCGA-BRCA>"
+EXPECTED_SUBMITTER_IDS = {"TCGA-A1-A0SB", "TCGA-A1-A0SD", "TCGA-A1-A0SE", "TCGA-A1-A0SH"}
+
+
+def test_load_and_count_cases(loaded_store: GraphStore) -> None:
+    rows = loaded_store.query(
+        PREFIXES
+        + f"SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE {{ ?c a db:Case ; db:belongsToProject {PROJECT} }}"
+    )
+    assert int(rows[0]["n"]) == 4
+
+
+def test_case_submitter_ids(loaded_store: GraphStore) -> None:
+    rows = loaded_store.query(
+        PREFIXES
+        + f"SELECT ?sid WHERE {{ ?c a db:Case ; db:belongsToProject {PROJECT} ; db:submitterId ?sid }}"
+    )
+    assert {r["sid"] for r in rows} == EXPECTED_SUBMITTER_IDS
+
+
+def test_diagnosis_labels(loaded_store: GraphStore) -> None:
+    rows = loaded_store.query(
+        PREFIXES
+        + f"""
+        SELECT ?label WHERE {{
+            ?c a db:Case ; db:belongsToProject {PROJECT} ; db:hasDiagnosis ?d .
+            ?d db:primaryDiagnosisLabel ?label .
+        }}
+        """
+    )
+    labels = {r["label"] for r in rows}
+    assert "Infiltrating duct carcinoma, NOS" in labels
+    assert "Lobular carcinoma, NOS" in labels
+    assert len(rows) == 4
+
+
+def test_case_diagnosis_join(loaded_store: GraphStore) -> None:
+    # Fall -> Diagnose -> Label über die ObjectProperty db:hasDiagnosis.
+    rows = loaded_store.query(
+        PREFIXES
+        + f"""
+        SELECT ?sid ?label WHERE {{
+            ?c a db:Case ; db:belongsToProject {PROJECT} ;
+               db:submitterId ?sid ; db:hasDiagnosis ?d .
+            ?d db:primaryDiagnosisLabel ?label .
+        }}
+        """
+    )
+    pairs = {(r["sid"], r["label"]) for r in rows}
+    assert ("TCGA-A1-A0SB", "Infiltrating duct carcinoma, NOS") in pairs
+    assert ("TCGA-A1-A0SH", "Adenocarcinoma, NOS") in pairs
+
+
+def test_load_turtle_into_named_graph(store: GraphStore) -> None:
+    # Isoliert in einem eigenen Named Graph laden und danach wieder verwerfen,
+    # damit der Test den restlichen Store nicht verunreinigt (Test-Isolation).
+    graph = "urn:wissensnetz:test:load-from-text"
+    try:
+        store.load_turtle(
+            """@prefix db: <http://databridge.hka/onto#> .
+            <http://databridge.hka/instance/case/UNITTEST-1> a db:Case ;
+                db:submitterId "UNITTEST-1" .""",
+            graph=graph,
+        )
+        assert store.ask(
+            PREFIXES
+            + f'ASK {{ GRAPH <{graph}> {{ '
+            '<http://databridge.hka/instance/case/UNITTEST-1> db:submitterId "UNITTEST-1" }}'
+        )
+    finally:
+        store.update(f"DROP GRAPH <{graph}>")
diff --git a/wissensnetz/tests/test_init.py b/wissensnetz/tests/test_init.py
new file mode 100644
index 0000000..5e6df4e
--- /dev/null
+++ b/wissensnetz/tests/test_init.py
@@ -0,0 +1,36 @@
+"""Aufgabe 1 — Abnahme: Dataset existiert und TBox-Klassen sind abfragbar."""
+
+from __future__ import annotations
+
+from wissensnetz.config import PREFIXES
+from wissensnetz.graphstore import GraphStore
+from wissensnetz.init import initialize, tbox_loaded
+
+EXPECTED_CLASSES = {
+    "http://databridge.hka/onto#Project",
+    "http://databridge.hka/onto#Case",
+    "http://databridge.hka/onto#Demographic",
+    "http://databridge.hka/onto#Diagnosis",
+}
+
+
+def test_dataset_exists_after_init(store: GraphStore) -> None:
+    assert store.dataset_exists()
+
+
+def test_initialize_is_idempotent(store: GraphStore) -> None:
+    # Zweiter Lauf darf nicht scheitern und meldet die TBox als vorhanden.
+    report = initialize(store)
+    assert report["dataset"] == store.settings.dataset
+    assert report["tbox"].startswith("skipped")
+    assert tbox_loaded(store)
+
+
+def test_tbox_classes_queryable(store: GraphStore) -> None:
+    rows = store.query(PREFIXES + "SELECT ?c WHERE { ?c a owl:Class }")
+    found = {r["c"] for r in rows}
+    assert EXPECTED_CLASSES <= found
+
+
+def test_marker_class_present(store: GraphStore) -> None:
+    assert store.ask(PREFIXES + "ASK { db:Case a owl:Class }")
```

## Anhang B — Verifikation (reproduzierte Ausgaben)

### B.1 Komponentengrenze: keine Änderungen an mediator/ oder wrappers/
```text
$ git diff --name-only fc73f56 HEAD | grep -E "^(mediator|wrappers)/" || echo "(leer)"
(leer -> keine Verletzung)
```

### B.2 Dateien in den drei Commits (git diff --stat fc73f56 HEAD)
```text
 .env.example                                  |  11 ++
 docker-compose.yml                            |   6 +
 graph-db/README.md                            |  40 +++++-
 wissensnetz/CLAUDE.md                         |  56 +++++++++
 wissensnetz/README.md                         | 130 ++++++++++++++++++++
 wissensnetz/TASKS_wissensnetz.md              |  72 +++++++++++
 wissensnetz/data/sample/cases_brca_sample.ttl |  86 +++++++++++++
 wissensnetz/pyproject.toml                    |  28 +++++
 wissensnetz/requirements.txt                  |   8 ++
 wissensnetz/src/wissensnetz/__init__.py       |  15 +++
 wissensnetz/src/wissensnetz/cli.py            | 131 ++++++++++++++++++++
 wissensnetz/src/wissensnetz/config.py         |  85 +++++++++++++
 wissensnetz/src/wissensnetz/graphstore.py     | 169 ++++++++++++++++++++++++++
 wissensnetz/src/wissensnetz/init.py           |  68 +++++++++++
 wissensnetz/tests/conftest.py                 |  38 ++++++
 wissensnetz/tests/test_graphstore.py          |  85 +++++++++++++
 wissensnetz/tests/test_init.py                |  36 ++++++
 17 files changed, 1063 insertions(+), 1 deletion(-)
```

### B.3 Pytest gegen laufendes Fuseki — zweimal in Folge gegen denselben persistenten Store
(beweist die in §5.1 beschriebene Test-Isolation)
```text
$ pytest -q      # Lauf 1
.........                                                                [100%]
9 passed in 1.67s
$ pytest -q      # Lauf 2 (identischer Store)
.........                                                                [100%]
9 passed in 1.53s
```

### B.4 Tests skippen ohne erreichbares Fuseki
```text
$ GRAPH_DB_URL=http://localhost:3999 pytest -q
sssssssss                                                                [100%]
9 skipped in 4.09s
```

### B.5 End-to-End auf frischem Volume (Definition of Done)
Reihenfolge: `docker compose down -v` → `up graph-db` → `init` → `load` → `query`.
```text
# 1) status direkt nach `up` — Dataset via FUSEKI_DATASET_1 bereits da, TBox noch nicht
Dataset: vorhanden
TBox:    nicht geladen (init ausfuehren)

# 2) wissensnetz init
Dataset 'databridge': bereits vorhanden
TBox:    loaded
Klassen: 4 owl:Class im Store

# 3) wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl
Geladen: ... -> Default-Graph

# 4) wissensnetz query "SELECT (COUNT(DISTINCT ?c) AS ?cases) WHERE { ?c a db:Case }"
cases
-----
4
```

### B.6 TBox-Klassen abfragbar (Aufgabe-1-Abnahme, Live-Ausgabe)
```text
$ wissensnetz query "SELECT ?c WHERE { ?c a owl:Class } ORDER BY ?c"
c                                     
--------------------------------------
http://databridge.hka/onto#Case       
http://databridge.hka/onto#Demographic
http://databridge.hka/onto#Diagnosis  
http://databridge.hka/onto#Project    

4 Zeile(n)
```

_Verifiziert am 2026-08-21 gegen Fuseki 5.1.0 (stain/jena-fuseki, Jena TDB2), Python 3.14._
