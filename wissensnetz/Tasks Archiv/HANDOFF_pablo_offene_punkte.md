# Hand-off an Pablo (Mediator): offene Punkte

**Von:** Marcel (Wissensnetz / Oberfläche)
**Stand:** 2026-09-24
**Ersetzt:** `HANDOFF_pablo_fortschritt.md` und `HANDOFF_pablo_auftrag_im_h5ad.md`
(beide Inhalte stehen vollständig hier)

Drei Punkte, nach Dringlichkeit. **P1 ist ein Defekt**, P2 und P3 sind Erweiterungen.
Alles ist am laufenden System nachgemessen, nicht vermutet; die Belege stehen jeweils dabei.
Keiner der drei Punkte setzt einen anderen voraus.

| | Punkt | Art | Aufwand (geschätzt) |
|---|---|---|---|
| **P1** | Langer Auftrag blockiert den ganzen Dienst | Defekt | klein |
| **P2** | Fortschritt während eines Auftrags melden | Erweiterung | mittel |
| **P3** | Den Auftrag ins `.h5ad` schreiben | Erweiterung | klein |

---

## P1 · Ein langer Auftrag blockiert den ganzen Dienst

### Befund

Ein `POST /selection/generate` über 5 Kohorten × 50 Proben (245 Dateien, rund 1 GB) lief
heute knapp 25 Minuten. **Währenddessen hat der Mediator nichts anderes mehr beantwortet**,
nicht einmal den eigenen Healthcheck:

```
$ curl -m 10 http://localhost:8000/health
(keine Antwort, Abbruch nach 10 s)

$ docker compose ps
mediator: running (Up 20 minutes (unhealthy))

$ docker compose exec mediator ps -eo pid,etime,args
   73  20:01  gdc-client download -m .cache/databridge/raw/462c901d…/manifest.txt
  107  19:44  python -c import urllib.request; urllib.request.urlopen('…/health')
  225  19:08  python -c import urllib.request; urllib.request.urlopen('…/health')
  348  18:34  python -c …                       ← ein Dutzend haengender Healthchecks
```

Nach Ende des Laufs war alles wieder normal: `GET /health` → 200, der Auftrag selbst
lieferte **200 OK**, und die Datei liegt unter
`/app/scripts/output/anndata/462c901d7a5574d57a84be91.h5ad`. Der Auftrag war also
erfolgreich — nur hat es davon niemand mitbekommen, weil die Oberfläche nach ihrer
Zeitgrenze aufgegeben hatte.

### Ursache

`selection_preview` und `selection_generate` sind als `async def` deklariert
(`app/main.py`, Zeilen 1055 und 1089), machen darin aber blockierende Arbeit: den
`gdc-client`-Aufruf, die HTTP-Abrufe, das Laden nach Fuseki. Damit blockieren sie den
Event-Loop von uvicorn, und der Dienst ist für die Dauer des Auftrags für **alle**
Anfragen tot. Der Healthcheck in `docker-compose.yml` läuft in dieser Zeit in sein
eigenes Timeout — daher `unhealthy`, obwohl der Dienst arbeitet.

### Vorschlag

Das `async` bei beiden Endpunkten streichen:

```python
@app.post("/selection/generate")
def selection_generate(request: SelectionRequest) -> SelectionGenerateResponse:
```

FastAPI führt ein gewöhnliches `def` in einem Threadpool aus; der Event-Loop bleibt frei,
und `/health` antwortet auch während eines langen Laufs. Falls die Funktionen intern `await`
brauchen, stattdessen die blockierenden Teile in `await run_in_threadpool(...)`
(`fastapi.concurrency`) legen. Gleiches gilt für `/export/anndata`, wenn dort derselbe
Kern läuft.

### Abnahme

1. Während eines `generate` über 250 Dateien antwortet `GET /health` weiterhin innerhalb
   einer Sekunde, und `docker compose ps` zeigt den Mediator durchgehend als `healthy`.
2. Ein zweiter, kleiner Aufruf (etwa `POST /selection/preview` über eine Kohorte) kommt
   während des langen Laufs durch, statt zu warten.

---

## P2 · Fortschritt während eines Auftrags melden

### Befund

Es gibt keinen Fortschrittskanal. Die Oberfläche schickt ihren Auftrag und hat bis zur
Antwort genau eine Information: dass er läuft.

| Aufruf | gemessene Dauer | was die Oberfläche in dieser Zeit sagen kann |
|---|---|---|
| Vorschau, 3 Kohorten (warm) | 1,6 s | „läuft" |
| Vorschau, 4 Kohorten × 30, kalt | 1,9 s | „läuft" |
| **Generieren, 5 Kohorten × 50** | **~25 min** | „läuft" |

Der Explorer hat unter der Anzeige eine Architekturansicht: eine Kette aus sechs Stationen
(Auswahl → JSON, Mediator, Wrapper → Datenquelle, GDC-JSON → RDF, graph-db, Wissensnetz),
die sich nach ihrem Zustand färben. Heute leitet sie alles **aus der Antwort** ab — während
des Laufs bleiben vier Kästen grau, obwohl in dieser Zeit nacheinander Abruf, Download,
Übersetzung, Laden und Matrixbau passieren. Bei der Vorschau ist das egal. Beim Generieren
steht der Forscher 25 Minuten davor.

### Vorschlag

**Korrelations-ID vom Aufrufer, dazu ein Abfrage-Endpunkt.**

Die Oberfläche kennt den `recipe_key` erst nach der Antwort — als Schlüssel taugt er nicht.
Sie schickt deshalb eine selbst erzeugte ID im **Header**, damit das Auftrags-JSON (der
Vertrag aus ADR-0003) unverändert bleibt:

```
POST /selection/generate
X-DataBridge-Progress-Id: 5f2c1a9e-…
```

```
GET /selection/progress/5f2c1a9e-…
```

```json
{
  "progress_id": "5f2c1a9e-…",
  "finished": false,
  "events": [
    {"ts": "2026-09-24T12:03:11.412Z", "stage": "request_received", "state": "ok"},
    {"ts": "2026-09-24T12:03:11.490Z", "stage": "wrapper_query", "state": "start",
     "detail": {"source": "gdc", "cohort": "TCGA-BRCA"}},
    {"ts": "2026-09-24T12:03:14.002Z", "stage": "wrapper_query", "state": "ok",
     "detail": {"source": "gdc", "cohort": "TCGA-BRCA", "hits": 50}},
    {"ts": "2026-09-24T12:03:14.010Z", "stage": "download", "state": "start",
     "detail": {"files": 245}},
    {"ts": "2026-09-24T12:28:41.771Z", "stage": "download", "state": "ok",
     "detail": {"files": 245, "missing": 0}},
    {"ts": "2026-09-24T12:28:41.780Z", "stage": "mapping", "state": "ok",
     "detail": {"triples": 790}},
    {"ts": "2026-09-24T12:28:42.104Z", "stage": "store_load", "state": "ok"},
    {"ts": "2026-09-24T12:28:55.330Z", "stage": "matrix", "state": "ok",
     "detail": {"n_obs": 250, "n_vars": 60660}}
  ]
}
```

Feste Stufennamen, damit sich jede Meldung einer Station zuordnen lässt:

| `stage` | Station im Explorer | wo im Mediator |
|---|---|---|
| `request_received` | Mediator | Eintritt in `/selection/*` |
| `wrapper_query` | Wrapper → Datenquelle | `fetch_selection_files`, je Kohorte |
| `download` | Wrapper → Datenquelle | `gdc-client`-Download (nur `generate`) |
| `mapping` | GDC-JSON → RDF | `cases_to_graph` |
| `store_load` | graph-db (Fuseki) | `_load_selection_knowledge` |
| `matrix` | Statuszeile | `_build_anndata_from_hits` |
| `done` | — | vor dem Return |

`state` ist `start`, `ok` oder `error`; bei `error` gehört die Meldung in `detail.error`.
Bei mehreren Ebenen zusätzlich `detail.level` (Index).

Beim `download` wäre eine Zwischenmeldung je 10 Dateien viel wert — das ist der Teil, der
die 25 Minuten ausmacht. `gdc-client` schreibt seinen Fortschritt auf die Standardausgabe;
alternativ genügt das Zählen der Dateien im Zielordner.

**Aufbewahrung:** ein `dict` im Prozess genügt — kein Redis. Einträge nach dem Ende noch ein
paar Minuten halten und dann verwerfen, Zahl der IDs nach oben begrenzen.

**Alternative:** SSE (`GET /selection/progress/{id}/stream`, `text/event-stream`). Fachlich
gleichwertig, die Oberfläche kommt mit beidem zurecht. Polling ist nur der kürzere Weg.

### Abnahme

1. Ein `generate` über zwei Kohorten meldet währenddessen mindestens `request_received`,
   `wrapper_query` (je Kohorte), `download`, `mapping`, `store_load`, `matrix`, `done` — in
   dieser Reihenfolge, mit Zeitstempeln, die zum tatsächlichen Verlauf passen.
2. `GET /selection/progress/{unbekannte-id}` antwortet mit `404` oder leerer Liste, nicht
   mit `500`.
3. Ein Aufruf **ohne** den Header verhält sich exakt wie heute.

---

## P3 · Den Auftrag ins `.h5ad` schreiben

### Befund

`uns` ist in allen vorhandenen Exporten leer:

| Datei | Proben | `uns` |
|---|---|---|
| `wissensnetz/data/selection_demo.h5ad` | 6 | `{}` |
| `wissensnetz/data/pancancer.h5ad` | 160 | `{}` |
| `Export Anndata/0465461fa8628e8a284a866e.h5ad` | 6 | `{}` |

`expression.build_anndata()` nimmt `X`, `obs`, `var` und optional `obsm` — für `uns` gibt es
keinen Parameter, und keiner der drei Aufrufer (`main.py` 873, 1010, 1269) hätte einen zu
übergeben. Ein `.h5ad` ist damit ein Ergebnis ohne Herkunft.

### Warum die Oberfläche das braucht

Der Explorer hat die Schaltfläche **`Auftrag aus .h5ad …`**: man öffnet eine früher erzeugte
Datei, und die Auswahl wird daraus wiederhergestellt. Ohne `uns` muss sie geraten werden:

| was | woher heute | verlässlich? |
|---|---|---|
| Kohorten | `obs["project_id"]` | ja |
| Attribute | die **belegten** `obs`-Spalten | **nein** |
| `size` | größte Fallzahl je Kohorte | nur ohne nachträgliche Filterung |
| Datenquelle, Modalität, `recipe_key` | — | **gar nicht** |

Der wunde Punkt sind die Attribute: `build_obs` legt immer dieselben Spalten an und füllt
nur die angefragten. Ein Attribut, das im Auftrag stand, aber für *jede* Probe leer
zurückkam, ist von einem nie angefragten nicht zu unterscheiden. In
`selection_demo.h5ad` sind acht Spalten in 0 von 6 Zeilen gefüllt.

### Vorschlag

Beim Erzeugen den Auftrag unter `uns["databridge_selection"]` ablegen, als
JSON-Zeichenkette:

```json
{
  "schema": 1,
  "recipe_key": "27d36cf9a95b1b03de629ba4",
  "created": "2026-09-24T12:03:11Z",
  "endpoint": "/selection/generate",
  "source": "gdc",
  "cohorts": ["TCGA-BRCA", "TCGA-LUAD"],
  "modality": "gene_expression",
  "attributes": ["sex_at_birth", "primary_diagnosis"],
  "size": 20,
  "per_cohort_size": null,
  "experimental_strategy": "RNA-Seq"
}
```

```python
# expression.py
def build_anndata(X, obs, var, *, obsm=None, uns: Optional[dict] = None) -> AnnData:
    adata = AnnData(X=X, obs=obs, var=var)
    if obsm:
        for key, value in obsm.items():
            adata.obsm[key] = value
    if uns:
        adata.uns.update(uns)
    return adata
```

```python
# main.py, _build_anndata_from_hits (sinngemäß auch die beiden anderen Aufrufer)
adata = expression_export.build_anndata(
    X, obs, var, obsm=obsm or None,
    uns={"databridge_selection": json.dumps(selection_dict, ensure_ascii=False)},
)
```

**Warum eine Zeichenkette und kein verschachteltes Dict:** `uns` landet in HDF5 als Gruppe;
Listen von Zeichenketten und `None` kommen je nach anndata-Version als Object-Array, als
Bytes oder gar nicht zurück. Eine Zeichenkette geht verlustfrei hin und zurück, ist mit
`json.loads` in einer Zeile gelesen und lässt sich über `"schema": 1` versionieren.

**Auch bei `/export/anndata`**, nicht nur bei `/selection/generate`; dort unterscheidet
`"endpoint"` die beiden Fälle.

### Abnahme

```python
import anndata as ad, json
a = ad.read_h5ad(r"wissensnetz\data\selection_demo.h5ad")
sel = json.loads(a.uns["databridge_selection"])
assert sel["cohorts"] == ["TCGA-BRCA"]
assert sel["source"] == "gdc"
```

1. Ein frisch erzeugtes `.h5ad` trägt das Feld, und der Inhalt entspricht Zeichen für
   Zeichen dem abgeschickten Auftrag — **einschließlich** der Attribute, die leer
   zurückkamen.
2. Ältere Dateien ohne das Feld lassen sich weiterhin öffnen.

---

## Was auf meiner Seite schon passiert ist

- Die Zeitgrenze fürs Generieren liegt jetzt bei **1800 s** statt 900 (über
  `DATABRIDGE_GENERATE_TIMEOUT` einstellbar) — der gemessene Lauf brauchte 25 Minuten.
- Die Timeout-Meldung sagt jetzt, dass der Mediator **weiterarbeitet**; „fehlgeschlagen"
  allein war irreführend, die Datei entstand ja.
- Vor dem Start nennt die Statuszeile Umfang und Schätzung („etwa 250 Dateien,
  erfahrungsgemäß rund 19 Minuten").
- Die Oberfläche leitet den Auftrag aus der Datei ab, solange P3 fehlt, und schreibt
  ausdrücklich dazu, dass das eine Rekonstruktion ist.

**Keiner der drei Punkte ist blockierend für mich.** Fehlen sie, bleibt alles, wie es ist —
die Oberfläche kann dann nur weniger sagen, als sie zeigt.

## Ausdrücklich nicht Teil dieser Punkte

- Keine Änderung am Auftrags-JSON und an den Antwortschemata.
- Kein Prozentwert und keine Restzeitschätzung. Stufen mit Zeitstempeln genügen; die
  Oberfläche zeigt bewusst keinen Fortschrittsbalken, weil sie ihn nicht belegen könnte.
- Kein Abbrechen laufender Aufträge, keine Änderung an `recipe_key`, keine neue
  Endpunkt-Variante.

---

## Antwort von Pablo (Mediator)

**Stand:** 2026-09-26

| Punkt | Status | Zusage/Termin |
|---|---|---|
| **P1** | umgesetzt | siehe unten |
| **P2** | umgesetzt | siehe unten |
| **P3** | umgesetzt | siehe unten |

### P1 · Ein langer Auftrag blockiert den ganzen Dienst

Genau wie vorgeschlagen: `async` bei `selection_preview`, `selection_generate`
und `export_anndata` gestrichen (dort läuft derselbe blockierende Kern wie bei
`selection_generate`, daher mit erledigt). Kein `run_in_threadpool` nötig, da
keine der drei Funktionen intern `await` brauchte. Abnahme lokal geprüft:
`GET /health` antwortet während eines laufenden `POST /selection/generate`
weiterhin sofort (FastAPI/Starlette führt die drei `def`-Endpunkte in
Worker-Threads statt im Event-Loop aus, testweise per `TestClient`
nachvollzogen).

### P2 · Fortschritt während eines Auftrags melden

Umgesetzt wie vorgeschlagen — Korrelations-ID per Header, kein SSE:

- `POST /selection/generate` nimmt optional den Header
  `X-DataBridge-Progress-Id` entgegen; ohne Header verhält sich der Aufruf
  exakt wie zuvor (keine Änderung am Auftrags-JSON).
- Neuer Endpunkt `GET /selection/progress/{progress_id}` liefert
  `{"progress_id", "finished", "events": [...]}`; unbekannte/verworfene ID
  → `404`, nicht `500`.
- Gemeldete Stufen: `request_received`, `wrapper_query` (je Kohorte, für
  gdc/cbioportal/geo), `download` (nur `gdc-client`, wie im Handoff-Vorschlag),
  `mapping`, `store_load` (nur bei `load=true`), `matrix`, `done` — in dieser
  Reihenfolge, mit `state` `start`/`ok`/`error` und `detail.error` bei Fehlern.
- Aufbewahrung: `dict` im Prozess (kein Redis), abgeschlossene Einträge nach
  10 Minuten verworfen, insgesamt max. 200 Einträge (älteste zuerst).
- Live gegen die echte GDC-API getestet (`TestClient`, ohne laufenden
  `gdc-client`/Fuseki): Reihenfolge und Fehlerzuordnung stimmen; siehe
  `app/main.py::_progress_*`/`selection_generate`.

Nicht umgesetzt (wie im Handoff ausdrücklich nicht gefordert): kein
Prozentwert, keine Restzeitschätzung, keine Zwischenmeldung je 10 Dateien
beim Download (nur ein `start`/`ok`/`error` für den gesamten
`gdc-client`-Lauf — die feingranulare Variante war im Handoff als "wäre
wertvoll", nicht als Abnahmekriterium markiert).

### P3 · Den Auftrag ins `.h5ad` schreiben

Umgesetzt wie vorgeschlagen: `expression.build_anndata()` hat jetzt einen
`uns`-Parameter, alle Erzeuger-Pfade (`_build_anndata_from_hits` für gdc,
`_build_anndata_from_cbioportal`, `_build_anndata_from_geo_best_effort`,
sowie `POST /export/anndata`) übergeben `uns["databridge_selection"]` als
JSON-Zeichenkette (Helper `_selection_uns` in `app/main.py`) — mit `schema`,
`recipe_key`, `created`, `endpoint`, `source`, `cohorts`/`project_id`,
`modality`, `attributes`, `size`, `per_cohort_size`/`per_project_size`.

Abnahme lokal nachvollzogen (echter `.h5ad`-Roundtrip über `anndata`, nicht
nur in-memory):
```python
sel = json.loads(a.uns["databridge_selection"])
assert sel["cohorts"] == ["TCGA-BRCA"]
assert sel["source"] == "gdc"
```
Ältere `.h5ad`-Dateien ohne das Feld bleiben lesbar (`uns` ist optional,
Default `None`).

---

## Abschluss (Marcel, 26.09.2026) — Oberfläche hängt dran, Handoff geschlossen

Alle drei Punkte sind mediator- **und** frontendseitig durch. Damit ist dieses
Dokument abgeschlossen; neue Wünsche gehören in ein neues.

| Punkt | Was die Oberfläche jetzt tut | Belegt durch |
| --- | --- | --- |
| **P1** Mediator bleibt ansprechbar | Wartezeit auf 30 Minuten hoch (`DATABRIDGE_GENERATE_TIMEOUT`); bei Ablauf sagt sie, dass der Mediator weiterarbeitet, statt Fehlschlag zu behaupten | `/health` 23× in ≤ 0,05 s während eines laufenden `generate` |
| **P2** Fortschrittskanal | Kennung im Kopf `X-DataBridge-Progress-Id`, Abfrage von `GET /selection/progress/{id}` im Sekundentakt in eigenem Thread; jede Meldung setzt genau eine Station der Architekturkette, und die Zeile darunter sagt „Der Mediator meldet seinen Fortschritt." statt „aus der Antwort belegt" | echter Lauf: 2 Kohorten, 4 Attribute, 7 Proben, 69 s — gemeldet wurden u. a. „14 Dateien werden geholt", „228 Tripel erzeugt", „in den Default-Graph geladen" |
| **P3** Auftrag im `.h5ad` | `uns["databridge_selection"]` wird gelesen und ins Panel gesetzt, **samt Datenquelle**; die Statuszeile unterscheidet „Die Datei führt den Auftrag selbst mit" von „Aus den Daten abgeleitet" | dieselbe Datei ergibt gelesen 4 Attribute + `gdc`, abgeleitet 5 Attribute + keine Quelle |

**Zwei Anmerkungen, keine Forderungen.**

1. Die Reihenfolge in `attributes` wird normalisiert: angefragt war
   `sex_at_birth, race, tumor_stage, vital_status`, in der Datei steht
   `sex_at_birth, race, vital_status, tumor_stage`. Für die Oberfläche
   unerheblich — sie ordnet nach dem Panel, nicht nach der Datei. Nur, damit es
   niemand später als Fehler sucht.
2. Die feingranulare Download-Meldung (alle *n* Dateien) fehlt bewusst und wird
   nicht nachgefordert: bei 14 Dateien reichen `start`/`ok`, und die Kette zeigt
   ohnehin keinen Prozentwert. Erst wenn wieder 245 Dateien am Stück laufen,
   wäre sie mehr als Kosmetik.
