# Aufgabe 14 (nur): Upsert je Property für den wachsenden Wissensbestand

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um,
**ausschließlich unter `wissensnetz/`**. NICHT `mediator/`, NICHT `wrappers/`. Kleine
Commits.

Kontext: `wissensnetz/HANDOFF_pablo_P4_ersetzen.md` (Antwort auf Pablos Rückfrage zu P4),
ADR-0003, und die bereits umgesetzte Aufgabe 13 (`src/wissensnetz/selection.py`,
`ontology/selection.ttl`, `enrichment.cases_for_selection`).

## Ziel

Der Mediator lädt bei jedem `/selection/*`-Aufruf Wissensbestand in den Default-Graph
(P1, umgesetzt in `mediator/app/main.py::_load_selection_knowledge`). Heute wird reines
Anhängen gemacht. Ändert GDC zwischen zwei Aufrufen einen Wert, hängen danach zwei Werte an
derselben Property, und `build_obs` sowie MP-Lite erwarten einen.

**Nicht lösen durch "Fall ersetzen".** Verschiedene Auswahlen fragen verschiedene
Attributmengen ab. Ein Aufruf mit weniger Attributen würde sonst löschen, was ein früherer,
reicherer Aufruf beigetragen hat, und der Store würde je nach letzter Anfrage schrumpfen
statt zu wachsen.

**Zu lösen als Upsert je Property:** gelöscht wird nur, was die aktuelle Nutzlast auch
schreibt. Alles, was frühere Aufrufe zusätzlich beigetragen haben, bleibt stehen.

## Deliverables

### 1) Neues Modul `src/wissensnetz/knowledge.py`

```python
def replace_case_properties(
    store: GraphStore, *, case_iris: list[str], properties: list[str]
) -> int:
    """Löscht genau die genannten Properties an genau den genannten Fällen
    (und an ihren Unterknoten Demographic/Diagnosis/Sample). Gibt die Anzahl
    der ausgeführten Update-Abfragen oder betroffenen Fälle zurück."""

def load_knowledge(
    store: GraphStore,
    turtle: str,
    *,
    submitter_ids: list[str],
    properties: list[str] | None = None,
) -> None:
    """Naht zum Mediator: Case-IRIs auflösen, betroffene Properties löschen,
    danach das Turtle ROH laden (kein rdflib-Roundtrip, RDF-star bleibt
    erhalten). Ohne `properties` verhält sich die Funktion wie
    `store.load_turtle(turtle)`, also reines Anhängen."""
```

`submitter_ids` zu Case-IRIs auflösen über das vorhandene
`selection.resolve_case_iris(store, ...)`. Findet sie einen Fall nicht (erster Ladevorgang),
wird für diesen Fall nichts gelöscht. Das ist der Normalfall beim ersten Aufruf und darf
keinen Fehler auslösen.

### 2) Das Löschen richtig eingrenzen

Für jede Property `?p` aus `properties` und jeden Fall `?case` aus `case_iris` müssen die
Aussagen am Fall **und an seinen Unterknoten** verschwinden, denn die Klinikfelder hängen
laut TBox nicht am Case selbst:

```sparql
DELETE { ?s ?p ?o } WHERE {
  VALUES ?case { <...> ... }
  VALUES ?p { db:gender db:tumorStage ... }
  {
    BIND(?case AS ?s) ?s ?p ?o .
  } UNION {
    ?case db:hasDemographic ?s . ?s ?p ?o .
  } UNION {
    ?case db:hasDiagnosis ?s . ?s ?p ?o .
  } UNION {
    ?case db:hasSample ?s . ?s ?p ?o .
  }
}
```

Die Property-Namen der Verknüpfung sind `db:hasDemographic`, `db:hasDiagnosis`,
`db:hasSample` (siehe `ontology/databridge-core.ttl`, Abschnitt Object Properties). Die
Inversen (`db:isDemographicOf`, `db:describesCase`, `db:isSampleOf`) erzeugt das
Mediator-Mapping ebenfalls, beim Löschen von Datatype-Properties sind sie aber nicht
betroffen.

**Nicht löschen, in dieser Reihenfolge prüfen:**

- Die **TBox**. Sie liegt laut `init.py` bewusst im selben Default-Graph wie die ABox. Das
  Löschen ist über `VALUES ?case` auf Instanz-IRIs verankert, trifft also keine
  Klassendefinition. In einem Test festnageln: nach einem Upsert muss
  `ASK { db:Case a owl:Class }` weiterhin true sein.
- **Projekt-Knoten.** Sie sind kohortenweit geteilt. Die Abfrage oben berührt sie nicht,
  weil `db:belongsToProject` nicht in der UNION steht. Nicht ergänzen.
- **Named Graphs.** Auswahl-Manifeste und die Nutzer-Graphen des Rückkanals. Ein Update ohne
  `GRAPH`-Klausel darf nur den Default-Graph treffen. **Prüfen**, ob das für unser Fuseki
  gilt (Union-Default-Graph ist in der Standardkonfiguration aus, aber verifizieren, nicht
  annehmen): einen Finding in einen Nutzer-Graphen schreiben, Upsert ausführen, Finding muss
  noch da sein.

### 3) Sonderfall NCIt-Alignment

`primary_diagnosis` ist im Mediator-Mapping auf `db:primaryDiagnosisLabel` abgebildet. Das
Alignment schreibt zusätzlich `db:primaryDiagnosis` (Objekt-Property auf das NCIt-Konzept)
und dazu eine RDF-star-Annotation der Form

```turtle
<< <diag> <db:primaryDiagnosis> <ncit:Cxxxx> >> prov:wasDerivedFrom gdc:submission ; db:confidence 1.0 .
```

Die Property-Liste des Mediators enthält nur das Label. Deshalb:

- Enthält `properties` `db:primaryDiagnosisLabel`, dann zusätzlich `db:primaryDiagnosis`
  mitlöschen.
- Die zugehörige Stern-Annotation ebenfalls entfernen, sonst bleibt Provenienz über eine
  Aussage stehen, die es nicht mehr gibt. Das braucht ein SPARQL-star-Update, etwa
  `DELETE { << ?s ?p ?o >> ?ap ?av } WHERE { ... }`.
- **Vorsicht, RDF-star-Falle** (siehe `CLAUDE.md`): rdflib parst das nicht zuverlässig,
  Fuseki kann es nativ. Die Abfrage also gegen das laufende Fuseki verifizieren, nicht gegen
  rdflib, und wenn sie dort nicht trägt, das Verhalten dokumentieren statt es zu erzwingen.

### 4) Export in `__init__.py`
`load_knowledge` und `replace_case_properties` in die öffentliche API und in `__all__`,
plus eine Zeile im Modul-Docstring unter "Naht zum Mediator".

### 5) Dokumentation
Kurzer Abschnitt in `wissensnetz/README.md` neben der Auswahl-Dokumentation: was Upsert je
Property bedeutet, und der Hinweis, dass ein Aufruf mit weniger Attributen nichts löscht,
was ein früherer beigetragen hat.

### 6) Tests `tests/test_knowledge.py`
Muster wie `test_selection.py`, self-isolating, Skip ohne erreichbares Fuseki.

- **Der entscheidende Test:** Fall mit `gender` und `tumor_stage` laden, dann denselben Fall
  nur mit `gender` und geändertem Wert laden. Danach muss `db:gender` **genau einen** Wert
  haben, und zwar den neuen, und `db:tumorStage` muss **noch vorhanden** sein. Dieser Test
  ist der Grund für die Aufgabe.
- Erster Ladevorgang ohne vorhandenen Fall löscht nichts und wirft nicht.
- `properties=None` verhält sich wie `load_turtle`.
- TBox überlebt (`ASK { db:Case a owl:Class }`).
- Ein Rückkanal-Finding in einem Nutzer-Graphen überlebt ein Upsert.
- Projekt-Knoten überlebt, auch wenn alle seine Fälle geupsertet werden.

## Verifikation

```bash
docker compose up -d graph-db
wissensnetz init
pytest wissensnetz/tests -q          # alle bisherigen Tests bleiben grün
```

Danach von Hand gegen den Store: einen Fall zweimal mit unterschiedlichen Attributmengen
laden und prüfen, dass

```bash
wissensnetz query "SELECT ?g (COUNT(?g) AS ?n) WHERE {
  ?c a db:Case ; db:submitterId 'TCGA-A1-A0SB' ; db:hasDemographic ?d . ?d db:gender ?g
} GROUP BY ?g"
```

genau eine Zeile mit `?n = 1` liefert.

## Grenze

Nur `wissensnetz/`. Keine Änderung an `mediator/` oder `wrappers/`. Das GDC→RDF-Mapping
NICHT nachbauen, insbesondere keine zweite Tabelle Attribut zu `db:`-Property anlegen: die
Property-Liste kommt als Parameter vom Mediator. Kein GDC-Zugriff.
