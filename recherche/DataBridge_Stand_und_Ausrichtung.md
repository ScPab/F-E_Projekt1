# DataBridge: Stand und Ausrichtung

**Projekt:** 26ss_CB_DataBridge, Master-FuE-Projekt-1, HS Karlsruhe in Kooperation mit der Universität Oviedo
**Team:** Marcel Thiel (Wissensnetz), Julian Lanfermann (Wrapper), Pablo Scherer (Mediator)
**Stand:** 2026-09-10

Dieses Dokument fasst zusammen, was gebaut ist, was es technisch tut und wohin das Projekt ausgerichtet wird. Es ersetzt die bisherigen Einzeldokumente in `recherche/`, die nach `recherche/_archiv/` wandern. Eine Zuordnung alt zu neu steht in Teil C.

Alle Code-Ausschnitte sind gekürzt und mit Datei und Zeilennummer belegt. Sie geben den Stand vom 2026-09-10 wieder.

---

## Teil A: Was bereits umgesetzt ist

### A.0 Die Kette in einem Absatz

Die Architektur folgt dem Mediator-Wrapper-Muster. Pro Quelle gibt es einen Wrapper als Python-Paket im Mediator-Container (ADR-0001), der Mediator übersetzt die Rohtreffer nach RDF/Turtle und baut auf einem Seitenkanal anndata-Matrizen, das Wissensnetz besitzt den RDF-Store samt Lese- und Schreiboberfläche, und ein Bokeh-Prototyp zeigt das Ergebnis als Cancer Map. Die Naht zwischen Mediator und Wissensnetz ist bewusst RDF/Turtle über HTTP und SPARQL, es gibt keine Code-Kopplung.

```
GDC / GEO / ENA / cBioPortal
        │  wrappers/<quelle>/client.py          Metadaten, Schema, Bulk
        ▼
   mediator/app/main.py                          REST, Orchestrierung
        │  app/semantic/mapping*.py  → Turtle
        │  app/semantic/expression.py → .h5ad
        ▼
   wissensnetz/  (Fuseki + SPARQL + Rückkanal)
        ▼
   prototype/mp_lite/app.py                      Cancer Map
```

### A.1 Wrapper: Zugriff auf die Quellen (Julian)

Vier Quellen sind angebunden: `gdc`, `geo`, `ena`, `cbioportal`, jede als eigenständiges Unterpaket mit `client.py`, `cache.py`, README und einem `scripts/check_connection.py`. Alle vier sind live gegen die echten APIs verifiziert.

Die Filter werden aus vereinfachten Suchparametern gebaut, bewusst nur mit den Operatoren `and` und `in`, alles Weitere über `extra`:

```python
# wrappers/gdc/client.py, ab Zeile 45
def build_filters(*, project_id=None, experimental_strategy=None,
                  data_type=None, access="open", extra=None) -> Optional[dict]:
    content: list[dict] = []
    def _in(field: str, value: StrOrList) -> None:
        values = [value] if isinstance(value, str) else list(value)
        content.append({"op": "in", "content": {"field": field, "value": values}})
    if project_id:             _in("cases.project.project_id", project_id)
    if experimental_strategy:  _in("files.experimental_strategy", experimental_strategy)
    if data_type:              _in("files.data_type", data_type)
    if access:                 _in("files.access", access)
```

Jede Abfrage legt ihre Spezifikation als Cache-Eintrag ab, das sogenannte Recipe. Dieser Schlüssel wird im Konzept in Teil B wieder auftauchen:

```python
# wrappers/gdc/client.py, ab Zeile 234
recipe = {"endpoint": endpoint, "filters": filters, "fields": fields,
          "size": size, "from": from_, "sort": sort}
recipe_key = self.cache.recipes.key_for(recipe)
self.cache.recipes.set(recipe_key, recipe)
```

Die Abfrage läuft per POST statt GET. Das war eine Fehlerbehebung: bei Multi-Kohorten-Exports landeten mehrere hundert `file_id`-Werte im Query-String, und GDC lehnte die URL mit HTTP 414 ab.

```python
# wrappers/gdc/client.py, ab Zeile 244 (Kommentar gekürzt)
# POST statt GET: bei umfangreichen Filtern ... wird die GET-Query-String-Länge
# von GDCs Server abgelehnt (HTTP 414, live reproduziert bei ~320 IDs / ~13 KB).
body: dict[str, Any] = {"from": from_, "size": size, "format": "json"}
if filters: body["filters"] = filters
if fields:  body["fields"] = ",".join(fields)
response = self.session.post(f"{self.base_url}/{endpoint}", json=body, timeout=self.timeout)
```

Die Rohfeldnamen bleiben unverändert, die Übersetzung ist ausdrücklich Aufgabe der Mapping-Schicht. Getestet ist der GDC-Wrapper mit 21 Unit-Tests gegen ein gemocktes `requests` (`wrappers/tests/test_gdc_client.py`).

### A.2 Mediator: REST, Semantik und anndata (Pablo)

`mediator/app/main.py` exponiert die Kette über REST: `/health`, `/query`, `/schema/{endpoint}`, `/manifest`, quellenspezifische Rohendpunkte für GEO, ENA und cBioPortal, sowie die beiden semantischen Endpunkte `/transform` und `/ontology` und den Export `/export/anndata`.

**Welche Felder überhaupt geholt werden**, steht an einer Stelle:

```python
# mediator/app/main.py, ab Zeile 59
TRANSFORM_CASE_FIELDS = [
    "case_id", "submitter_id", "project.project_id",
    "demographic.gender", "demographic.race", "demographic.ethnicity",
    "demographic.vital_status",
    "diagnoses.primary_diagnosis", "diagnoses.age_at_diagnosis",
    "diagnoses.morphology", "diagnoses.site_of_resection_or_biopsy",
    "diagnoses.ajcc_pathologic_stage", "diagnoses.metastasis_at_diagnosis",
    "samples.sample_id", "samples.sample_type",
]
```

**Das Mapping nach RDF** erzeugt pro GDC-Node eine eigene Klasse, statt zu abstrahieren. Ein Case wird zum `db:Case`, das Projekt zum `db:Project`, verlinkt über ein Property-Paar mit `owl:inverseOf`:

```python
# mediator/app/semantic/mapping.py, ab Zeile 90
case_iri = URIRef(f"{INSTANCE_BASE}case/{_slug(case_id)}")
graph.add((case_iri, RDF.type, DB.Case))
graph.add((case_iri, DB.caseId, Literal(case_id, datatype=XSD.string)))
...
graph.add((case_iri, DB.belongsToProject, project_iri))
graph.add((project_iri, DB.hasCase, case_iri))
```

**Provenienz** hängt nicht am Knoten, sondern an der Aussage. Erfolgreiche NCIt-Alignments werden als RDF-star angehängt, bewusst als Text und nicht über eine rdflib-API, weil deren Turtle-star-Unterstützung je Version schwankt:

```python
# mediator/app/semantic/mapping.py, ab Zeile 185
def serialize_with_provenance(graph, star_annotations) -> str:
    turtle = graph.serialize(format="turtle")
    ...
# erzeugt Blöcke der Form:
#   << <sample> <db:reclassifiedAs> <ncit:...> >>
#       prov:wasDerivedFrom gdc:submission ; db:confidence 1.0 .
```

**`/transform`** ist der Übergabepunkt an das Wissensnetz. Ohne `load` ist es eine reine Textsenke, mit `load: true` schreibt der Mediator direkt in Fuseki, und zwar über den GraphStore des Wissensnetz-Pakets:

```python
# mediator/app/main.py, ab Zeile 493
turtle = semantic_mapping.serialize_with_provenance(graph, star_annotations)
response = {"format": "turtle", "triple_count": len(graph), "turtle": turtle, "loaded": False}
if request.load:
    store = get_graph_store()
    store.load_turtle(turtle, graph=request.graph)
    response["loaded"] = True
```

Die Abhängigkeitsrichtung ist damit Mediator zu Wissensnetz und nie umgekehrt.

**Der anndata-Export** liegt in `app/semantic/expression.py` mit den Schritten `parse_gdc_quantification_file`, `assemble_matrix`, `build_obs`, `build_var`, `compute_tsne`, `build_anndata`, `write_h5ad`. Ein Multi-Kohorten-Export holt die Dateien seit dem Stratifizierungs-Fix pro Projekt einzeln, sonst lieferte GDCs Default-Reihenfolge de facto nur eine einzige Kohorte:

```python
# mediator/app/main.py, ab Zeile 570
projects = request.project_id if isinstance(request.project_id, list) else [request.project_id]
n_each = request.per_project_size or request.size
for project in projects:
    file_filters = build_filters(project_id=project, ..., access="open", extra=[...])
    try:
        result = wrapper.query("files", filters=file_filters, fields=file_fields, size=n_each)
    except RequestException:
        failed_projects.append(project)   # eine kaputte Kohorte killt nicht den Export
        continue
    hits.extend(result["results"])
```

`per_project_size` ist Teil des Recipe-Schlüssels, damit stratifizierte Anfragen einen eigenen Cache-Eintrag bekommen.

### A.3 Wissensnetz: Store, Ontologie, Anreicherung, Rückkanal (Marcel)

Eigenständiges, installierbares Paket unter `wissensnetz/src/wissensnetz/` mit sechs Modulen und einer CLI. Alle drei Richtungen des Netzes sind implementiert.

**Ontologie (TBox).** Quellenunabhängig gehalten, Namensraum `db:` gleich `http://databridge.hka/onto#`. Die Mapping-Regel ist im Kopf der Datei dokumentiert:

```turtle
# wissensnetz/ontology/databridge-core.ttl, Kopf
#   node                  -> owl:Class
#   property + type       -> owl:DatatypeProperty (xsd-Range)
#   link + target_type    -> owl:ObjectProperty
#   backref               -> owl:inverseOf
#   enum-Werte            -> Alignment auf externe Bio-Ontologien (hier: NCIt)
#   required: [...]       -> owl:minCardinality 1 + rdfs:domain

db:Case a owl:Class ;
    rdfs:label "Case" ;
    rdfs:comment "Entspricht GDC-Node 'case': ein einzelner Patient/Fall ..." .

db:belongsToProject a owl:ObjectProperty ;
    rdfs:domain db:Case ; rdfs:range db:Project ;
    owl:inverseOf db:hasCase .
```

Enthalten sind heute `db:Project`, `db:Case`, `db:Demographic`, `db:Diagnosis`, `db:Sample` sowie `db:Series` (GEO) und `db:Study` (ENA) mit gemeinsam genutztem `db:Run`. cBioPortal verwendet bewusst die GDC-Klassen weiter, statt Duplikate anzulegen.

**Initialisierung.** `wissensnetz init` ist idempotent und prüft über Marker-Abfragen, ob TBox und Rückkanal-Vokabular schon liegen:

```python
# wissensnetz/src/wissensnetz/init.py, ab Zeile 30
_TBOX_PRESENT     = PREFIXES + "ASK { db:Case a owl:Class }"
_FEEDBACK_PRESENT = PREFIXES + "ASK { db:ExpertFinding a owl:Class }"
```

**Store-Client.** Dünner Fuseki-Client über SPARQL Query, SPARQL Update und Graph Store Protocol. Entscheidend ist, dass Turtle roh übertragen wird:

```python
# wissensnetz/src/wissensnetz/graphstore.py, ab Zeile 98
def load_turtle(self, text_or_path, graph: str | None = None) -> None:
    """... Der Turtle-Text wird unverändert übertragen (kein rdflib-Roundtrip),
    damit RDF-star erhalten bleibt."""
    turtle = self._resolve_turtle(text_or_path)
    params = {"graph": graph} if graph else {"default": ""}
    resp = self._session.post(self.settings.gsp_url, params=params,
                              data=turtle.encode("utf-8"),
                              headers={"Content-Type": _TURTLE}, auth=self._admin_auth(), ...)
```

**Anreicherung, das Lesen.** Die Klassenhierarchie läuft transitiv über `rdfs:subClassOf*`, sowohl im Default-Graph als auch in Named Graphs, und filtert anonyme Restriktionsknoten heraus:

```python
# wissensnetz/src/wissensnetz/enrichment.py, ab Zeile 78
pattern = f"{var} rdfs:subClassOf* {term} ."          # bzw. umgekehrt bei up=True
sparql = (PREFIXES + f"SELECT DISTINCT {var} WHERE {{\n"
          f"  {{ {pattern} }}\n  UNION\n  {{ GRAPH ?g {{ {pattern} }} }}\n"
          f"  FILTER(isIRI({var}))\n}} ORDER BY {var}")
```

Dazu `case_context()` und `diagnosis_context()`, beide bewusst tolerant: fehlt ein Wert im Graphen, steht `None` statt einer Exception. Genau deshalb konnte MP-lite die klinischen Felder anzeigen, bevor der Mediator sie lieferte.

**Rückkanal, das Schreiben.** Ein Selektions-Event aus dem Visualisierungswerkzeug wird zu einer `oa:Annotation` mit PROV-O-Provenienz, und die eigentliche Kernaussage je Probe als RDF-star:

```python
# wissensnetz/src/wissensnetz/feedback.py, ab Zeile 168 und 191
lines = [f"{anno} a oa:Annotation , db:ExpertFinding ;",
         f"    prov:wasAttributedTo {_user_iri(event.user)} ;",
         f'    prov:generatedAtTime "{ts}"^^xsd:dateTime ;']
...
star = [f"    << {s} db:reclassifiedAs {to_term} >> "
        f"prov:wasDerivedFrom {anno} ; db:confidence {conf} ." for s in samples]
```

Geschrieben wird in einen Named Graph pro Nutzer, damit Kern-TBox und ABox unberührt bleiben und eine Erkenntnis per `DROP GRAPH` widerrufbar ist:

```python
# wissensnetz/src/wissensnetz/feedback.py, ab Zeile 124
def graph_iri_for(user: str) -> str:
    return f"{GRAPH_USER_BASE}{_slug(user)}"      # .../graph/user/<id>
```

**CLI.** `wissensnetz status | init | load | query | hierarchy | context | feedback | findings`.

**Tests.** `wissensnetz/tests/` mit sechs Modulen. Sie laufen gegen ein echtes Fuseki und werden übersprungen, wenn keines erreichbar ist, was CI ohne Store möglich macht.

### A.4 Prototyp MP-lite

`wissensnetz/prototype/mp_lite/app.py` ist eine Bokeh-Server-App, die Oviedos Morphing Projections nachbaut: Scatter mit Box- und Lasso-Auswahl, 15 Slider in Oviedos Reihenfolge, Kohorten-Legende, Hover mit der vollen Feldliste, darunter Kontextpanel und Rückkanal-Formular. Die Morph-Mechanik ist die gewichtete Summe der Encodings, `Σ aᵢ·E[i]` mit `a = softmax(10·slider)`, und läuft clientseitig.

Das für Teil B wichtigste Detail ist, wie ein Slider aktiv wird. Er aktiviert sich nicht durch Konfiguration, sondern durch Daten:

```python
# wissensnetz/prototype/mp_lite/app.py, ab Zeile 401
for _title, _E, _init in _SLIDER_SPECS:
    if _E is not None:
        sl = Slider(start=0.0, end=1.0, value=_init, step=0.01, width=200, title=_title)
        morph_sliders.append(sl); E_arrays.append(np.asarray(_E, dtype=float))
    else:
        sl = Slider(..., disabled=True, title=f"{_title}  (keine Daten)")
    display_sliders.append(sl)
```

Ein Encoding entsteht nur, wenn die Variable mindestens zwei verschiedene Werte hat (`is_encodable`). Fehlende Daten erscheinen also als ehrliche Lücke im UI statt als leerer Regler. Diese Regel wird in Teil B zum Kern der Navigation.

Die 32 TCGA-Kohorten liegen an einer Stelle und werden von Ladeskript und Prototyp gemeinsam importiert:

```python
# wissensnetz/src/wissensnetz/cohorts.py
OVIEDO_COHORTS: tuple[str, ...] = ("ACC", "CHOL", "BLCA", "BRCA", ... , "UCS")
COHORT_PROJECT_IDS = tuple(f"TCGA-{code}" for code in OVIEDO_COHORTS)
```

### A.5 Was nachweislich noch nicht steht

| Lücke | Beleg |
|---|---|
| NCIt-Alignment fast leer | `ontology/alignment/ncit_primary_diagnosis.json` enthält genau drei Codes: C4194, C7950, C7688 |
| Nur eine Modalität | Der Export kennt Genexpression; Methylierung und Mutationen sind nirgends implementiert |
| Kein Cross-Source-Abgleich | Kein `owl:sameAs` zwischen GDC- und cBioPortal-Cases derselben Person, unterschiedliche IDs |
| Frontend offen | `frontend/` enthält nur `.gitkeep` und ein README, kein Compose-Service |
| Bekannte Inkonsistenz | cBioPortal-`db:Diagnosis`-Knoten erfüllen die `owl:minCardinality` auf `db:primaryDiagnosisLabel` nicht, dokumentiert, nur bei aktivem Reasoning relevant |

---

## Teil B: Die Ausrichtung, die wir umsetzen wollen

### B.1 Das Problem

Die Kette lädt heute erst und filtert danach. Das ist an mehreren Stellen sichtbar:

- `scripts/load_gdc.py --pancancer` zieht alle 32 Kohorten in den Store, unabhängig von der Fragestellung.
- Das Ergebnis liegt als `wissensnetz/data/pancancer.h5ad` mit 45 MB im Repo.
- Der Recipe-Cache des Mediators hat rund 150 Einträge, weil jede Variante der Gesamtanfrage einen eigenen Schlüssel erzeugt.
- Der 414-Fehler aus Teil A.1 war ein Symptom desselben Musters, 320 Datei-IDs in einem Aufruf, weil vorne keine Einschränkung stand.
- MP-lite liest über `all_cases()` alles, was im Graph liegt. Die Sicht ergibt sich damit aus dem, was zufällig geladen wurde, nicht aus dem, was gefragt wurde.

Das Kernproblem ist nicht Performance, sondern die fehlende Kopplung zwischen Fragestellung und geladener Menge. Dazu kommt, dass der Zugriff über die GDC-API im Vergleich zur klaren Form der Daten unübersichtlich ist: der Datenkörper ist ein mehrschichtiger Würfel mit gemeinsamer `obs`-Achse und je Modalität eigener `var`-Achse.

### B.2 Zielbild

Am Anfang steht nicht der Datenbestand, sondern die Auswahl. Der Forscher legt maximal drei Felder fest, und daraus wird der Ladeauftrag für die gesamte Kette abgeleitet.

Das Auswahl-Tripel ist **Kohorte × Modalität × Klinikvariable**, und die drei Felder sind nicht willkürlich, sondern entsprechen den drei Freiheitsgraden des Würfels:

| Achse | Feld | Bezug | Wirkung |
|---|---|---|---|
| 1 | Kohorte | `obs`-Zeilen | welche Proben in Frage kommen |
| 2 | Modalität | `var`-Spalten, Layer | welche Matrix und wie breit |
| 3 | Klinikvariable | `obs`-Spalte plus Graphkante | Stratifizierung und semantischer Fokus |

Jede weitere Einschränkung ist eine Verfeinerung innerhalb einer Achse, kein viertes Feld. Die Drei ist damit eine Tiefenbegrenzung, kein Kompromiss der Oberfläche.

### B.3 Gruppen statt Filter

Jedes Element des Würfels ist eine **Gruppe**, und eine Gruppe ist nicht eine Liste von Proben, sondern ein Pfad im Netz:

| anndata-Element | Graph-Entsprechung |
|---|---|
| `obs`-Zeile | `db:Sample`, Gruppe der Größe 1 |
| `obs`-Spaltenwert | Kante plus Zielknoten, etwa `db:tumorStage "Stage III"` |
| Kohorte | `db:Project` |
| `var`-Spalte | Merkmal auf der Merkmalsachse |
| Layer | Modalität |

Eine Gruppe wird intensional definiert, durch ihren Pfad, nicht extensional durch aufgezählte IDs. Damit ist sie benennbar, wiederholbar und zitierbar, bevor eine einzige Zahl geladen wurde:

```
/TCGA-KIRC/clear-cell/stage-III   +   modality=expression
```

Dieser Pfad ist gleichzeitig die Scope-ID. Vorschlag für die TBox:

```turtle
db:Group        a owl:Class .
db:selector     a owl:DatatypeProperty ; rdfs:domain db:Group .   # SPARQL-Pfad
db:parentGroup  a owl:ObjectProperty   ; rdfs:domain db:Group ; rdfs:range db:Group .
db:partitionBy  a owl:ObjectProperty   ; rdfs:domain db:Group ; rdfs:range rdf:Property .
db:memberCount  a owl:DatatypeProperty ; rdfs:domain db:Group ; rdfs:range xsd:integer .
db:onAxis       a owl:DatatypeProperty ; rdfs:domain db:Group .   # obs | var | layer
```

### B.4 Die Drill-down-Regel

> Biete an einem Knoten genau die Relationen an, die die aktuelle Gruppe in mindestens zwei nichtleere Untergruppen zerlegen.

Drei Eigenschaften folgen daraus. Es gibt keine Sackgassen, weil eine Relation ohne Varianz gar nicht erscheint. Es ist rein datengetrieben und damit robust gegen wechselnde Quellen. Und es ist exakt dieselbe Logik, die MP-lite heute schon für die Slider verwendet (siehe A.4, `is_encodable`). Die Regel wird also nicht erfunden, sie wird nur vom Ende der Kette an ihren Anfang verschoben.

Umgesetzt ist sie eine SPARQL-Abfrage gegen die Katalogschicht, technisch verwandt mit `_hierarchy()` aus `enrichment.py`.

### B.5 Beide Achsen sind hierarchisch

Wenn jedes anndata-Element eine Gruppe ist, gilt das für beide Achsen, und das Wissensnetz kann beide hierarchisieren:

- **obs-Achse:** NCIt für Diagnosen, Anatomie über `site_of_resection_or_biopsy`, Stadien über `tumor_stage`. Werkzeug ist `rdfs:subClassOf*`, das bereits implementiert ist.
- **var-Achse:** Gen zu Pathway zu GO-Term. Aus 20.531 Spalten wird ein navigierbarer Baum, und der Forscher wählt einen Signalweg statt 40 Gensymbole zu tippen.
- **Modalität:** bleibt flach, sie wählt nur die Matrix.

Damit bekommt die Literaturrecherche zu GO und SO einen konkreten Zweck im System, statt nur Ausblick zu bleiben. Die Achsensymmetrie ist außerdem das stärkste Argument für RDF gegenüber einem Katalog in SQL: dieselbe Traversierungsoperation trägt beide Achsen.

### B.6 Zwei Schichten im Store

| Schicht | Inhalt | Größe | Lebensdauer |
|---|---|---|---|
| Katalogschicht | `db:Group`-Baum mit `memberCount`, NCIt- und GO-Hierarchien, Drill-down-Regel | klein, dauerhaft geladen | permanent |
| Detailschicht | ABox je Scope plus zugehöriges `.h5ad` | groß | pro Scope, per `DROP GRAPH` verwerfbar |

Das löst das Henne-Ei-Problem: navigieren kann man nur, was man schon kennt. Die Katalogschicht kennt Struktur und Anzahl, ohne die Daten zu haben. Materialisiert wird erst am Blatt.

Beide Schichten liegen im selben Fuseki, getrennt über Named Graphs. ADR-0002 bleibt unverändert gültig, es gibt keinen Infrastrukturwechsel. Der Named Graph pro Scope, `.../graph/scope/<id>`, folgt dem Muster, das der Rückkanal mit `.../graph/user/<id>` bereits verwendet (siehe A.3).

### B.7 Was der Forscher am Ende sieht

Nicht das Nicht-Gewählte wird ausgeblendet, es ist gar nicht erst da. Innerhalb eines Scopes werden drei Relationsklassen sichtbar:

1. **Struktur:** `db:Project → db:Case → db:Sample`, immer, weil sie die Identität der Punkte trägt.
2. **Merkmal:** die gewählte Klinikvariable, ihr Alignment-Ziel und dessen Oberklassen über `rdfs:subClassOf*`.
3. **Rückkanal:** Findings, die an derselben Gruppe hängen.

Formal ist die Sicht ein SPARQL `CONSTRUCT` mit begrenztem Relevanzhorizont gegen den Scope-Graph.

Dazu kommen Dinge, die ein Filtermenü nie liefern würde: Quergänge, wenn dieselbe NCIt-Diagnose in einer anderen Kohorte auftaucht, Geschwisterknoten und Oberbegriffe als einfache Abfrage, und ein Rückkanal, der an `db:Group` hängt statt an einer flüchtigen Lasso-Auswahl. Zwei Forscher, die denselben Pfad gehen, sehen die Erkenntnisse des jeweils anderen.

### B.8 Verteilung auf die Komponenten

| Baustein | Owner | Was neu ist |
|---|---|---|
| Katalog- und Facettenzählungen je Quelle | Julian | Zählabfragen ohne Nutzdaten, je Quelle ein `facets()`-Äquivalent |
| Scope-Auflösung, Transform und Export je Scope | Pablo | Scope-ID als Cache-Schlüssel, Zielgraph und Ziel-`.h5ad` aus dem Scope |
| Scope-Vokabular, Scope-Graphen, Sichtabfragen | Marcel | `db:Group` in der TBox, Laden in Named Graph, `CONSTRUCT`-Sichten, CLI `scope` |
| Auswahlmaske vor der Karte | Marcel | drei Auswahlfelder als Einstieg, danach erst der Plot |

Die Komponentengrenze bleibt unverändert, die Naht ist weiterhin RDF/Turtle über HTTP und SPARQL.

### B.9 Auswirkung auf den Bestand

- **Bleibt:** Mediator-Wrapper-Muster, RDF/OWL auf Fuseki nach ADR-0002, anndata als Seitenkanal, der Rückkanal.
- **Ändert sich:** `load_gdc.py --pancancer` wird scope-basiert, `/export/anndata` bekommt einen Scope statt einer Projektliste, MP-lite bekommt einen Auswahlschritt davor.
- **Entfällt:** `pancancer.h5ad` als Standardweg. Als Demofixture kann es bleiben.

### B.10 Offene Entscheidungen

1. **Quelle für Modalität 2 und 3.** Methylierung und Mutationen sind über die GDC-API teuer zu beziehen, UCSC Xena liefert vorharmonisierte Matrizen. Ohne diese Entscheidung hat Achse 2 nur einen Wert, und das Tripel ist nur zu zwei Dritteln real. Dringlichste Frage, weil sie entscheidet, ob das Konzept vorführbar wird.
2. **Reichweite eines Findings.** Gilt eine Erkenntnis nur im Scope, in dem sie entstand, oder global.
3. **Obergrenzen und Invalidierung.** Wie viele Proben darf ein Scope materialisieren, wann wird er neu gezogen.
4. **Herkunft der Counts** in der Katalogschicht: Facetten je Wrapper oder ein einmaliger Metadaten-Import ohne Matrizen.

### B.11 Nächste Schritte

1. `ontology/alignment/ncit_primary_diagnosis.json` füllen. Bisher ein Schönheitsfehler, jetzt blockierend: ohne NCIt-Hierarchie hat die Navigation ab Ebene 2 keine Semantik. Liegt vollständig im Wissensnetz-Teil und hängt an niemandem sonst.
2. Punkt B.10.1 im Team entscheiden.
3. Das Konzept als **ADR-0003 "Scope-basierte Datenakquise"** festhalten, damit die Neuausrichtung im Bericht als bewusste Entscheidung mit Alternativen dasteht.
4. Hand-offs an Julian (Katalog und Facetten) und Pablo (Scope-Auflösung) schreiben.

### B.12 Abbildungen

| Datei | Inhalt |
|---|---|
| `Konzept_Wissensnetz-Navigation.drawio` | Quelldatei, zwei Seiten: Gesamtbild der Kette und Gruppen-Modell |
| `Konzept_Gesamtbild_S1.png` | Rendering von Seite 1, die drei Flüsse Navigation, Materialisierung, Rückkanal |
| `Konzept_Gruppenmodell_S2.png` | Rendering von Seite 2, `db:Group`, Drill-down-Regel, beide Achsen |
| `Konzept_Navigation_Ebene1.png` | Oberflächenskizze Ebene 1, Kohortenwahl, nichts geladen |
| `Konzept_Navigation_Ebene2.png` | Ebene 2, Partition von TCGA-KIRC, verworfene Relationen ohne Varianz |
| `Konzept_Navigation_Ebene3.png` | Ebene 3, beide Achsen am Blatt, Materialisierung |

Zahlen in den Abbildungen sind beispielhaft, NCIt-Codes stehen dort als Platzhalter.

---

## Teil C: Zuordnung zu den archivierten Dokumenten

Die folgenden Dateien liegen in `recherche/_archiv/`. Ihr Inhalt ist entweder in dieses Dokument eingeflossen, in Code übergegangen oder durch eine neuere Entscheidung ersetzt.

| Archiviertes Dokument | Wo der Inhalt heute lebt |
|---|---|
| `Wissensnetz_Konzept-Entwurf` | Teil A.3 dieses Dokuments, umgesetzt in `wissensnetz/src/wissensnetz/` |
| `Wissensnetz_Gesamtueberblick` | Teil A.0 und A.3 |
| `Mapping-Konzept_GDC-zu-RDF-OWL` (inkl. der Kopie) | Umgesetzt in `mediator/app/semantic/mapping.py` und im Kopf von `databridge-core.ttl`; Label-Tabellen je Quelle stehen aktuell in `mediator/app/semantic/README.md` |
| `Rueckkanal-Konzept_MP-zu-RDF` | Umgesetzt in `wissensnetz/src/wissensnetz/feedback.py` und `ontology/feedback.ttl`, zusammengefasst in Teil A.3 |
| `Globale_eindeutige_Zuordnung` | IRI-Bildung und Alignment-Prinzip, jetzt in Teil A.2 und in der offenen Frage `owl:sameAs` in Teil A.5 |
| `DataBridge_Architektur_und_Skriptkette` | Teil A.0, dazu die Diagramme unter `docs/*.drawio` |
| `DataBridge_Literaturrecherche` | Grundlage von ADR-0002, dort zitiert; der GO-Teil wird in Teil B.5 wieder aufgegriffen |

**Hinweis zu Verweisen:** `README.md` im Wurzelverzeichnis und `wissensnetz/CLAUDE.md` verlinken einige dieser Dateien noch unter ihrem alten Pfad. Diese Verweise sollten auf `recherche/_archiv/` oder auf dieses Dokument umgebogen werden.
