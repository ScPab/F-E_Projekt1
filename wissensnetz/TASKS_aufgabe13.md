# Aufgabe 13 (nur): Auswahl-Graphen im Wissensnetz, wachsender Store

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um,
**ausschließlich unter `wissensnetz/`** (Ausnahme: Deliverable 6, siehe dort). NICHT
`mediator/`, NICHT `wrappers/`. Kleine Commits.

Kontext: ADR-0003 (`docs/adr/0003-ui-gesteuerte-akquise.md`) und der Review
`wissensnetz/HANDOFF_review_selection.md`, Abschnitt "Was bei mir liegt". Die
Gegenstücke im Mediator sind in `wissensnetz/HANDOFF_pablo_store_waechst.md`
beschrieben und werden von Pablo umgesetzt, **nicht** hier.

## Ziel

Der Store ist **nicht** global vorbefüllt, sondern wächst mit den Aufrufen. Jeder
`/selection/*`-Aufruf des Mediators schreibt seinen Wissensbestand hinein. Diese Aufgabe
liefert die Wissensnetz-Seite dafür: das Vokabular und die Ablage für eine Auswahl, eine
auf die Auswahl begrenzte Lesefunktion, und die CLI, um beides ohne Oberfläche zu prüfen.

Zwei Ebenen, bewusst getrennt:

- **Wissensbestand** (Case, Demographic, Diagnosis, Sample und die dynamisch erzeugten
  Properties) liegt im **Default-Graph** und wächst dort. Die Instanz-IRIs sind
  deterministisch (`http://databridge.hka/instance/case/<slug>`, siehe
  `mediator/app/semantic/mapping.py`), identische Tripel kollabieren also von selbst.
- **Auswahl-Manifest** je Aufruf liegt in einem **Named Graph** und hält nur, welche Proben
  und Fälle zu dieser Auswahl gehören, plus die Auswahlparameter.

Warum getrennt: läge der Wissensbestand je Auswahl in einem eigenen Named Graph, stünden
dieselben Case-Tripel als Quads mehrfach im Store, und ein `DROP GRAPH` würde Wissen
löschen, das eine andere Auswahl noch braucht.

## Deliverables

### 1) Vokabular `ontology/selection.ttl`
Eigene Datei neben `feedback.ttl`, damit die Kern-TBox sauber bleibt. Terme (Namensraum
`db:`), `prov:`- und `rdfs:`-Terme wiederverwenden statt neu definieren:

- `db:Selection` (owl:Class)
- `db:selectionId` (xsd:string, der Recipe-Key des Mediators)
- `db:hasMember` (ObjectProperty, `db:Selection` → `db:Sample`)
- `db:hasCase` ist belegt, deshalb für den Fallbezug `db:selectionCase`
  (ObjectProperty, `db:Selection` → `db:Case`)
- `db:selectedCohort`, `db:selectedModality`, `db:selectedAttribute` (xsd:string, mehrfach)
- `db:source` (xsd:string, z. B. "gdc")
- Provenienz über `prov:generatedAtTime` (xsd:dateTime)

### 2) Neues Modul `src/wissensnetz/selection.py`
Muster und Stil wie `feedback.py`.

```python
SELECTION_GRAPH_BASE = "http://databridge.hka/graph/selection/"

def graph_iri_for_selection(selection_id: str) -> str: ...

def selection_manifest(
    selection_id: str, *, source: str, cohorts: list[str], modality: str,
    attributes: list[str], submitter_ids: list[str], sample_ids: list[str],
    timestamp: str | None = None,
) -> str:
    """Baut das Auswahl-Manifest als Turtle (für den Named Graph)."""

def write_selection(store: GraphStore, selection_id: str, **kwargs) -> str:
    """Manifest bauen und in den Named Graph laden; gibt die Graph-IRI zurück."""

def drop_selection(store: GraphStore, selection_id: str) -> None:
    """DROP GRAPH für eine Auswahl. Löscht NUR das Manifest, nicht den Wissensbestand."""

def list_selections(store: GraphStore) -> list[dict]:
    """Alle Auswahlen mit id, Kohorten, Modalität, Attributen, Zeit, Mitgliederzahl."""
```

`write_selection` ist die Funktion, die Pablo aufruft. Die Signatur ist damit Teil der
Naht: **sie darf sich nach der Übergabe nicht mehr ändern**, ohne Pablo zu informieren.
Die Sample-IRIs müssen dieselbe Bildungsregel nutzen wie das Mediator-Mapping
(`INSTANCE_BASE + "sample/" + _slug(sample_id)`), sonst zeigt das Manifest ins Leere. Regel
aus `mediator/app/semantic/mapping.py` ablesen, nicht raten, und in einem Test festnageln.

### 3) `init.py` lädt das neue Vokabular mit
Analog zu `feedback.ttl`: Pfadkonstante, Marker-Abfrage
(`ASK { db:Selection a owl:Class }`), idempotent, `--force` lädt neu.

### 4) `enrichment.cases_for_selection(store, selection_id)`
Gleiche Rückgabeform wie `all_cases()` (Zeile 197), aber begrenzt auf die Mitglieder einer
Auswahl. Muss über die Grenze zwischen Named Graph (Manifest) und Default-Graph
(Wissensbestand) hinweg joinen:

```sparql
SELECT ?submitterId ?sampleId ?gender ... WHERE {
  GRAPH <.../graph/selection/ID> { ?sel db:hasMember ?sample ; db:selectionCase ?case }
  ?case db:submitterId ?submitterId .
  OPTIONAL { ?case db:hasDemographic ?d . ?d db:gender ?gender }
  ...
}
```

Tolerant bleiben wie `case_context()`: fehlt ein Wert, steht `None`, keine Exception. Diese
Funktion ist das Gegenstück zu `all_cases(store)` in `_build_anndata_from_hits` und der
Grund, warum die `obs` nicht mehr den ganzen Store sieht.

### 5) CLI erweitern (`cli.py`)
- `wissensnetz selections` listet alle Auswahlen (aus `list_selections`).
- `wissensnetz selection <id>` zeigt eine Auswahl samt ihrer Fälle
  (`cases_for_selection`), Ausgabe im Stil von `wissensnetz context`.
- `wissensnetz drop-selection <id>` mit Sicherheitsabfrage, ruft `drop_selection`.

### 6) Optional, Projektskript `scripts/run_selection.py`
**Außerhalb von `wissensnetz/`, deshalb optional und als letzter Commit.** Muster:
`scripts/load_gdc.py`. Nimmt eine `selection.json`, schickt sie an
`POST <mediator>/selection/preview` bzw. `--generate`, und gibt danach
`wissensnetz selection <recipe_key>` aus. Damit ist die Kette ohne Oberfläche
durchspielbar. Kein GDC-Zugriff, nur HTTP gegen den Mediator.

### 7) Tests `tests/test_selection.py`
Muster wie `test_feedback.py`: self-isolating, Skip ohne erreichbares Fuseki.

- Manifest parst als Turtle und enthält die erwarteten Tripel.
- `write_selection` dann `list_selections` findet die Auswahl wieder.
- `cases_for_selection` liefert genau die Mitglieder, nicht mehr: dazu zwei Auswahlen mit
  überlappenden Fällen schreiben und prüfen, dass jede nur ihre eigenen sieht. **Das ist
  der wichtigste Test der Aufgabe.**
- `drop_selection` entfernt das Manifest, der Wissensbestand im Default-Graph bleibt.
- Sample-IRI-Bildung stimmt mit der Regel aus dem Mediator-Mapping überein.

## Verifikation

```bash
docker compose up -d graph-db
wissensnetz init                 # lädt selection.ttl mit
wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl   # Wissensbestand
# Auswahl von Hand schreiben (Python-Einzeiler oder Test-Fixture), dann:
wissensnetz selections
wissensnetz selection <id>
pytest wissensnetz/tests -q      # alle bisherigen Tests bleiben grün
```

Erwartung: `wissensnetz selection <id>` zeigt nur die Fälle der Auswahl, während
`wissensnetz query` weiterhin den gesamten Store sehen kann. Genau dieser Unterschied ist
das Ergebnis der Aufgabe.

## Grenze

Nur `wissensnetz/`, Deliverable 6 zusätzlich `scripts/`. Keine Änderung an `mediator/` oder
`wrappers/`. Das GDC→RDF-Mapping NICHT nachbauen. Kein GDC-Zugriff. Das Kernpaket bleibt
anndata-frei.
