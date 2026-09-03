# Neue Datenquellen anbinden und pflegen

Dieses Dokument beschreibt, wie eine neue Datenquelle an die
Mediator/Mapping-Ebene angebunden wird — nach demselben regelbasierten
Muster wie der GDC-Ausschnitt (siehe
[`wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL`](../wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL%20-%20Kopie.pdf),
Ontologie unter [`wissensnetz/ontology/`](../wissensnetz/ontology/), Mapping-Code
unter [`mediator/app/semantic/`](../mediator/app/semantic/)).

GEO, ENA und cBioPortal sind bereits nach genau diesem Muster umgesetzt —
als konkrete Referenz für den nächsten neuen Quellen-Fall siehe
[`mediator/app/semantic/README.md`](../mediator/app/semantic/README.md)
(vollständige Label-Tabellen je Quelle, Wiederverwendungsprinzip, bekannte
Grenzen) sowie `mapping_geo.py`/`mapping_ena.py`/`mapping_cbioportal.py`.

**Dieser Prozess ist bewusst manuell.** Es gibt keine automatische Erkennung
neuer Schemata — jemand muss für jede neue Quelle festlegen, welches
Quellfeld welchem Ontologie-Begriff entspricht. Ziel der Architektur ist,
diesen Aufwand auf "eine neue Ontologie-Ergänzung plus ein neues
Mapping-Modul" zu minimieren, nicht ihn zu automatisieren.

## 1. Prüfen: sind die neuen Konzepte schon in der Basis-Ontologie abgedeckt?

Vor dem Schreiben von Code die TBox durchsehen:
[`wissensnetz/ontology/databridge-core.ttl`](../wissensnetz/ontology/databridge-core.ttl)
(oder über den laufenden Mediator: `GET /ontology`). Passt ein GDC-artiges
Konzept aus der neuen Quelle bereits auf eine bestehende Klasse/Property
(z. B. liefert auch GEO etwas wie "Case"/"Sample"), diese wiederverwenden statt
zu duplizieren.

## 2. Ontologie bei Bedarf erweitern

Neue Klassen/Properties folgen der Konstrukt-für-Konstrukt-Tabelle aus dem
Mapping-Konzept:

| Quell-Konstrukt          | RDF/OWL-Gegenstück                          |
|---------------------------|----------------------------------------------|
| node / Entität             | `owl:Class`                                   |
| property + type            | `owl:DatatypeProperty` (xsd-Range)            |
| link + target_type         | `owl:ObjectProperty`                          |
| backref                    | `owl:inverseOf`                               |
| enum-Werte                 | Alignment auf externe Bio-Ontologie (optional, mit Literal-Fallback) |
| required: [...]            | `owl:minCardinality 1` + `rdfs:domain`        |
| title / description        | `rdfs:label` / `rdfs:comment`                 |

Beispiel-Snippet für eine neue Klasse mit einer Property:

```turtle
db:Sample a owl:Class ;
    rdfs:label "Sample" ;
    rdfs:comment "<Quelle>-Entität <node-name>: <Kurzbeschreibung>." .

db:describesSample a owl:ObjectProperty ;
    rdfs:label "describesSample" ;
    rdfs:domain db:SomeChildEntity ;
    rdfs:range db:Sample ;
    owl:inverseOf db:hasSample .
```

Namespace bleibt `db:` = `http://databridge.hka/onto#` — quellen-unabhängig,
damit dieselbe Klasse von mehreren Quellen befüllt werden kann.

Bei enum-Feldern mit Bezug zu Bio-Ontologien (Diagnosen, Genfunktionen,
Sequenztypen …): eine neue Alignment-Tabelle unter
`wissensnetz/ontology/alignment/<quelle>_<feld>.json` anlegen, Format wie
[`ncit_primary_diagnosis.json`](../wissensnetz/ontology/alignment/ncit_primary_diagnosis.json)
(`{"<Quelltext>": "<voller Ontologie-Concept-IRI>"}`). Nicht gelistete Werte
fallen im Mapping-Code auf ein Literal-Feld zurück statt eine ungeprüfte
Zuordnung zu erzwingen — Codes nur eintragen, wenn sie über OLS/BioPortal
verifiziert sind.

## 3. Neues Mapping-Modul anlegen

Ein Modul `mediator/app/semantic/mapping_<quelle>.py` nach dem Muster von
[`mapping.py`](../mediator/app/semantic/mapping.py) (GDC):

- Eine Funktion `<entität>_to_graph(records, *, alignment=None) -> tuple[Graph, list[StarAnnotation]]`,
  die aus den Rohdatensätzen der Quelle die Konstrukt-Regeln aus Schritt 2
  anwendet (rdflib, kein RML/Java nötig — reines Python passt zum
  bestehenden `mediator/environment.yml`).
- Kanten mit Provenienz/Konfidenz (z. B. Alignment-Aussagen) werden wie im
  GDC-Modul über `serialize_with_provenance` als RDF-star angehängt
  (`<< s p o >> prov:wasDerivedFrom ... ; db:confidence ... .`, siehe
  ADR-0002).
- Aktuell Global-as-View (eine Quelle je Modul, direkt gegen die
  DataBridge-Ontologie). Wächst die Zahl der Quellen deutlich, ist laut
  Mapping-Konzept eine Local-as-View-Formalisierung zu prüfen — bislang
  offener Punkt, keine akute Notwendigkeit.
- Neuer Endpunkt oder erweiterter `source`-Parameter in
  `POST /transform` (`mediator/app/main.py`), der bei `source="<quelle>"`
  an das neue Modul delegiert.

## 4. Ergebnis testen/validieren

- Kleine Beispieldatei anlegen (`sample_data/<quelle>_sample.json`) und ein
  Skript nach dem Muster von
  [`scripts/example_gdc_to_rdf.py`](../mediator/scripts/example_gdc_to_rdf.py)
  laufen lassen — es druckt die erzeugten Tripel und schreibt eine `.ttl`-Datei.
- Die erzeugte Turtle-Datei mit `rdflib` parsen lassen (z. B.
  `rdflib.Graph().parse(path, format="turtle")`), um Syntaxfehler früh zu
  erkennen. Die angehängten RDF-star-Blöcke sind kein gültiges Turtle 1.1 —
  sie folgen der RDF-star-Grammatik (RDF 1.2), die aktuelle
  `rdflib.Graph().parse()`-Turtle-Implementierung akzeptiert `<<>>` je nach
  Version ggf. nicht; für eine belastbare Prüfung dieses Teils die Datei
  gegen Apache Jena/Fuseki laden (nativer RDF-star-Support laut ADR-0002).
- Über `POST /transform` gegen den laufenden Mediator testen (`docker compose
  up mediator` bzw. lokal `uvicorn app.main:app --reload`).

## 5. Hinweis zur Grenze des Verfahrens

Dieses Mapping führt nur bereits definierte Regeln aus — es erzeugt oder
erschließt sie nicht selbstständig. Ändert sich das Quellschema (z. B. neue
GDC-Felder), muss die Ontologie/das Mapping-Modul manuell nachgeführt werden
(Ontology-Evolution, siehe Mapping-Konzept Abschnitt 5). Es gibt bewusst
keinen automatisierten Schema-Diff oder Auto-Mapping-Mechanismus.
