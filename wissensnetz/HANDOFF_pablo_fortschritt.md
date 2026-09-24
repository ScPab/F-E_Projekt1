# Hand-off an Pablo (Mediator): Fortschritt während eines Auftrags melden

**Von:** Marcel (Wissensnetz / Oberfläche)
**Datum:** 2026-09-24
**Bezug:** `mediator/app/main.py` (`_fetch_selection_level`, `_load_selection_knowledge`,
`_build_anndata_from_hits`), `frontend/ablauf.py`, ADR-0003
**Status:** Anforderung, noch nicht umgesetzt. Die Oberfläche funktioniert ohne sie — sie
kann während eines Aufrufs nur weniger sagen, als sie zeigt.

---

## 1 Worum es geht

Der Explorer hat unter der Anzeige eine **Architekturansicht**: eine Kette aus sechs
Stationen — Auswahl → JSON, Mediator, Wrapper → Datenquelle, GDC-JSON → RDF, graph-db
(Fuseki), Wissensnetz. Jede färbt sich nach ihrem Zustand, an einer laufenden wandert eine
Leuchtlinie am Rand entlang.

Was dort steht, ist heute **aus der Antwort abgeleitet, nicht mitgehört**. Ich bitte um
einen Kanal, über den der Mediator während der Arbeit melden kann, wo er gerade steht.

## 2 Befund

Es gibt keinen Fortschrittskanal. Die Oberfläche schickt `POST /selection/preview` bzw.
`/selection/generate` und hat bis zur Antwort genau eine Information: dass der Aufruf
läuft. Alles Weitere steht erst danach in der Antwort (`status`, `triple_count`,
`failed_cohorts`, `anndata`).

Gemessen an diesem Stand:

| Aufruf | Dauer | was die Oberfläche in dieser Zeit sagen kann |
|---|---|---|
| Vorschau, 3 Kohorten (warm) | 1,6 s | „läuft" |
| Vorschau, 4 Kohorten × 30, kalt | 1,9 s | „läuft" |
| **Generieren** | **Minuten** (`GENERATE_TIMEOUT = 900 s` in `frontend/mediator_client.py`) | „läuft" |

Bei der Vorschau ist das verschmerzbar. Beim **Generieren** steht der Forscher minutenlang
vor einer Kette, in der zwei Kästen blau blinken und vier grau bleiben — obwohl in dieser
Zeit nacheinander der GDC-Abruf, der Download über `gdc-client`, die Übersetzung nach RDF,
das Laden in Fuseki und der Matrixbau passieren. **Genau dort liegt der Nutzen.**

## 3 Die Anforderung

**Ein Fortschrittskanal, den die Oberfläche neben dem laufenden Aufruf abfragen kann.**

### 3.1 Korrelations-ID vom Aufrufer

Die Oberfläche kennt den `recipe_key` erst nach der Antwort — als Schlüssel taugt er
deshalb nicht. Stattdessen schickt sie eine selbst erzeugte ID **im Header** mit:

```
POST /selection/generate
X-DataBridge-Progress-Id: 5f2c1a9e-…
```

Ein Header und kein Feld im Body, damit das Auftrags-JSON — der Vertrag aus ADR-0003 —
unverändert bleibt. Fehlt der Header, verhält sich alles wie heute.

### 3.2 Abfrage-Endpunkt

```
GET /selection/progress/{progress_id}
```

```json
{
  "progress_id": "5f2c1a9e-…",
  "finished": false,
  "events": [
    {"ts": "2026-09-24T12:03:11.412Z", "stage": "request_received", "state": "ok"},
    {"ts": "2026-09-24T12:03:11.բ90Z", "stage": "wrapper_query", "state": "start",
     "detail": {"source": "gdc", "cohort": "TCGA-BRCA"}},
    {"ts": "2026-09-24T12:03:14.002Z", "stage": "wrapper_query", "state": "ok",
     "detail": {"source": "gdc", "cohort": "TCGA-BRCA", "hits": 20}},
    {"ts": "2026-09-24T12:03:14.010Z", "stage": "download", "state": "start",
     "detail": {"files": 20}},
    {"ts": "2026-09-24T12:05:41.771Z", "stage": "download", "state": "ok",
     "detail": {"files": 20, "missing": 0}},
    {"ts": "2026-09-24T12:05:41.780Z", "stage": "mapping", "state": "ok",
     "detail": {"triples": 790}},
    {"ts": "2026-09-24T12:05:42.104Z", "stage": "store_load", "state": "ok"},
    {"ts": "2026-09-24T12:05:55.330Z", "stage": "matrix", "state": "ok",
     "detail": {"n_obs": 40, "n_vars": 60660}}
  ]
}
```

**Feste Stufennamen** (`stage`), damit die Oberfläche sie einer Station zuordnen kann:

| `stage` | Station im Explorer | wo im Mediator |
|---|---|---|
| `request_received` | Mediator | Eintritt in `/selection/*` |
| `wrapper_query` | Wrapper → Datenquelle | `fetch_selection_files` je Kohorte |
| `download` | Wrapper → Datenquelle | `gdc-client`-Download (nur `generate`) |
| `mapping` | GDC-JSON → RDF | `cases_to_graph` |
| `store_load` | graph-db (Fuseki) | `_load_selection_knowledge` |
| `matrix` | (nur Statuszeile) | `_build_anndata_from_hits` |
| `done` | — | vor dem Return |

`state` ist `start`, `ok` oder `error`; bei `error` gehört die Meldung in `detail.error`.
Bei mehreren Ebenen zusätzlich `detail.level` (Index), damit sich die Meldungen zuordnen
lassen.

### 3.3 Aufbewahrung

Ein `dict` im Prozess genügt — kein Redis, keine Datenbank. Einträge nach dem Ende des
Aufrufs noch ein paar Minuten halten (damit ein letzter Abruf sie sieht) und dann
verwerfen; die Zahl der IDs nach oben begrenzen, damit ein Dauerlauf den Speicher nicht
füllt.

### 3.4 Alternative, falls dir lieber ist

Statt Polling ein **SSE-Stream** (`GET /selection/progress/{id}/stream`,
`text/event-stream`). FastAPI kann das mit `StreamingResponse`, und `requests` liest es mit
`stream=True`. Fachlich gleichwertig — die Oberfläche kommt mit beidem zurecht. Polling ist
nur der kürzere Weg: kein offener zweiter Socket, kein Timeout-Verhalten, das man testen
muss.

## 4 Was ich auf meiner Seite mache

Sobald der Kanal steht, fragt die Oberfläche ihn neben dem laufenden Aufruf ab (eigener
Worker, etwa alle 500 ms) und setzt die Stationen **auf das, was gemeldet wurde**, statt es
aus der Antwort abzuleiten. Die Zeile unter der Kette — „Die Zwischenschritte sind aus der
Antwort belegt, nicht mitgehört" — verschwindet dann, weil sie nicht mehr stimmt.

**Ohne den Kanal bleibt alles, wie es ist.** Fehlt der Endpunkt, fragt die Oberfläche ihn
nicht; es gibt keinen Fehlerfall, den man abfangen müsste.

## 5 Abnahme

1. Ein `generate` über zwei Kohorten meldet währenddessen mindestens
   `request_received`, `wrapper_query` (je Kohorte), `download`, `mapping`, `store_load`,
   `matrix`, `done` — in dieser Reihenfolge und mit Zeitstempeln, die zum tatsächlichen
   Verlauf passen.
2. `GET /selection/progress/{unbekannte-id}` antwortet mit `404` oder einer leeren
   Ereignisliste, nicht mit einem Fehler 500.
3. Ein Aufruf **ohne** den Header verhält sich exakt wie heute.
4. Ein fehlgeschlagener Abruf erzeugt ein Ereignis mit `state: "error"` und einer Meldung
   in `detail.error` — dieselbe, die auch in der Antwort steht.

## 6 Ausdrücklich **nicht** Teil dieser Anforderung

- Keine Änderung am Auftrags-JSON und an den Antwortschemata.
- Kein Prozentwert und keine Restzeitschätzung. Stufen mit Zeitstempeln genügen; ein
  Prozentbalken wäre geraten, und die Oberfläche zeigt bewusst keinen.
- Kein Abbrechen laufender Aufträge. Das wäre eine eigene Anforderung.

## 7 Zusammenhang

Diese Anforderung und `HANDOFF_pablo_auftrag_im_h5ad.md` (Auftrag in `uns`) sind
unabhängig voneinander; beide betreffen dieselbe Stelle im Ablauf, aber keine setzt die
andere voraus.
