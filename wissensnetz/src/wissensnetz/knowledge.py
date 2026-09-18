"""Wachsender Wissensbestand (Aufgabe 14): Upsert **je Property**.

Der Mediator lädt bei jedem ``/selection/*``-Aufruf Wissensbestand in den
Default-Graph (P1, ``mediator/app/main.py::_load_selection_knowledge``). Reines
Anhängen genügt nicht: ändert GDC zwischen zwei Aufrufen einen Wert, hängen
danach zwei Werte an derselben Property, und ``build_obs`` wie MP-Lite erwarten
einen.

**Nicht "Fall ersetzen".** Verschiedene Auswahlen fragen verschiedene
Attributmengen ab. Ein Aufruf mit weniger Attributen würde sonst löschen, was
ein früherer, reicherer Aufruf beigetragen hat — der Store würde je nach letzter
Anfrage schrumpfen statt zu wachsen (siehe ``HANDOFF_pablo_P4_ersetzen.md``).

**Sondern Upsert je Property:** gelöscht wird nur, was die aktuelle Nutzlast
auch schreibt. ``sex_at_birth`` wird geliefert, also fällt ``db:sexAtBirth`` an diesen
Fällen vorher weg; ``tumor_stage`` wird nicht geliefert, also bleibt es stehen.
Der Store wächst damit monoton, außer in den Werten, die tatsächlich neu
geliefert werden.

Die Zuordnung *Attributname → ``db:``-Property* bleibt beim Mediator
(``resolve_attribute``) und kommt als Parameter herein — hier entsteht bewusst
keine zweite Tabelle davon (CLAUDE.md: das GDC→RDF-Mapping nicht nachbauen).

**Naht zum Mediator:** :func:`load_knowledge` ersetzt dort den
``store.load_turtle(turtle)``-Aufruf. Die Signatur ändert sich nach der
Übergabe nicht mehr ohne Absprache.

Was **nicht** gelöscht wird, und warum:

* **Die TBox.** Sie liegt laut ``init.py`` bewusst im selben Default-Graph wie
  die ABox. Das Löschen ist über ``VALUES ?case`` auf Instanz-IRIs verankert und
  trifft deshalb keine Klassendefinition.
* **Projekt-Knoten.** Sie sind kohortenweit geteilt, ``db:belongsToProject``
  steht deshalb nicht im Pfad unten.
* **Named Graphs.** Auswahl-Manifeste (Aufgabe 13) und die Nutzer-Graphen des
  Rückkanals (Aufgabe 4). Ein Update ohne ``GRAPH``-Klausel trifft nur den
  Default-Graph — für unser Fuseki verifiziert in
  ``tests/test_knowledge.py::test_feedback_named_graph_survives_upsert``.
"""

from __future__ import annotations

from .config import DB, PREFIXES
from .graphstore import GraphStore
from .selection import is_iri, resolve_case_iris

# Verknüpfung Fall -> Unterknoten (ontology/databridge-core.ttl, Object
# Properties). Die Klinikfelder hängen laut TBox nicht am Case selbst, sondern
# am Demographic/Diagnosis/Sample. Die Inversen (db:isDemographicOf,
# db:describesCase, db:isSampleOf) erzeugt das Mediator-Mapping ebenfalls, beim
# Löschen von Datatype-Properties sind sie aber nicht betroffen.
_SUBNODE_PATH = "(db:hasDemographic|db:hasDiagnosis|db:hasSample)?"

# Sonderfall NCIt-Alignment: `primary_diagnosis` ist im Mediator-Mapping auf
# db:primaryDiagnosisLabel abgebildet, das Alignment schreibt zusätzlich
# db:primaryDiagnosis (Objekt-Property auf das NCIt-Konzept) plus eine
# RDF-star-Annotation. Die Property-Liste des Mediators enthält nur das Label,
# deshalb behandeln wir das Alignment als dessen Anhang.
PRIMARY_DIAGNOSIS_LABEL = f"{DB}primaryDiagnosisLabel"
PRIMARY_DIAGNOSIS = f"{DB}primaryDiagnosis"

# Fälle je Update-Abfrage. Eine Auswahl-Ebene hat höchstens 200 Proben
# (SelectionRequest.size), die Aufteilung ist also eher Vorsorge als Nötigung.
_CHUNK = 100


def _property_term(ref: str) -> str:
    """SPARQL-Term für eine Property: volle IRI in spitzen Klammern, CURIE mit
    bekanntem Präfix unverändert (die Standard-``PREFIXES`` lösen sie auf)."""
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return r
    if is_iri(r):
        return f"<{r}>"
    return r  # CURIE, z. B. db:sexAtBirth


def _normalize_property(ref: str) -> str:
    """Volle IRI einer Property — nur für den ``db:``-Präfixvergleich."""
    r = ref.strip().strip("<>")
    return f"{DB}{r[3:]}" if r.startswith("db:") else r


def _expand_properties(properties: list[str]) -> list[str]:
    """Property-Liste um die Anhänge des NCIt-Alignments ergänzen.

    Enthält sie ``db:primaryDiagnosisLabel``, kommt ``db:primaryDiagnosis``
    dazu — sonst bliebe der NCIt-Link einer Diagnose stehen, die gerade neu
    geschrieben wird.
    """
    out: list[str] = []
    seen: set[str] = set()
    for p in properties:
        p = (p or "").strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    normalized = {_normalize_property(p) for p in out}
    if PRIMARY_DIAGNOSIS_LABEL in normalized and PRIMARY_DIAGNOSIS not in normalized:
        out.append(PRIMARY_DIAGNOSIS)
    return out


def _chunks(values: list[str], size: int = _CHUNK) -> list[list[str]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def replace_case_properties(
    store: GraphStore, *, case_iris: list[str], properties: list[str]
) -> int:
    """Löscht genau die genannten Properties an genau den genannten Fällen
    (und an ihren Unterknoten Demographic/Diagnosis/Sample).

    Gibt die Anzahl der ausgeführten Update-Abfragen zurück (0, wenn nichts zu
    tun war). Leere ``case_iris`` oder ``properties`` sind kein Fehler — beim
    ersten Laden eines Falls gibt es nichts zu ersetzen.

    Die Eingrenzung geschieht über einen Property-Pfad mit ``?``
    (null-oder-einmal) ab dem über ``VALUES`` gebundenen Fall: null Schritte
    trifft den Fall selbst, ein Schritt seine Unterknoten.

    .. warning::
       Die naheliegende Variante, ``BIND(?case AS ?s)`` in einem ``UNION``-Zweig
       zu verwenden, während ``VALUES ?case`` außerhalb des ``UNION`` steht, ist
       **falsch**: im Zweig ist ``?case`` noch ungebunden, ``?s`` bleibt damit
       frei, und das ``DELETE`` trifft die Property an *allen* Subjekten. Gegen
       unser Fuseki nachgestellt; deshalb der Pfad statt der Union.
    """
    cases = [c for c in dict.fromkeys(c.strip() for c in case_iris) if c]
    props = _expand_properties(properties)
    if not cases or not props:
        return 0

    property_values = " ".join(_property_term(p) for p in props)
    delete_star = any(_normalize_property(p) == PRIMARY_DIAGNOSIS for p in props)

    executed = 0
    for chunk in _chunks(cases):
        case_values = " ".join(f"<{c}>" for c in chunk)

        # Zuerst die RDF-star-Annotationen des Alignments, solange die Diagnose
        # noch über db:hasDiagnosis erreichbar ist. Quoted Triples sind von der
        # behaupteten Aussage unabhängig — ohne diesen Schritt bliebe Provenienz
        # über eine Aussage stehen, die es nicht mehr gibt.
        if delete_star:
            store.update(PREFIXES + f"""
            DELETE {{ << ?diag db:primaryDiagnosis ?concept >> ?annoP ?annoV }}
            WHERE {{
              VALUES ?case {{ {case_values} }}
              ?case db:hasDiagnosis ?diag .
              << ?diag db:primaryDiagnosis ?concept >> ?annoP ?annoV .
            }}
            """)
            executed += 1

        store.update(PREFIXES + f"""
        DELETE {{ ?s ?p ?o }}
        WHERE {{
          VALUES ?case {{ {case_values} }}
          VALUES ?p {{ {property_values} }}
          ?case {_SUBNODE_PATH} ?s .
          ?s ?p ?o .
        }}
        """)
        executed += 1

    return executed


def load_knowledge(
    store: GraphStore,
    turtle: str,
    *,
    submitter_ids: list[str],
    properties: list[str] | None = None,
) -> None:
    """Naht zum Mediator: Upsert je Property, dann das Turtle **roh** laden.

    Aufruf im Mediator (ersetzt ``store.load_turtle(turtle)``)::

        load_knowledge(
            store, turtle,
            submitter_ids=[...],        # aus dem geteilten Abruf
            properties=[                # eine Zeile: resolve_attribute bleibt dort
                str(semantic_mapping.resolve_attribute(a).property_uri)
                for a in level.attributes
            ],
        )

    ``submitter_ids`` statt Case-IRIs, weil der Mediator die IRI aus ``case_id``
    bildet, uns aber den Barcode übergibt: nachschlagen statt nachrechnen, über
    :func:`wissensnetz.selection.resolve_case_iris`. Fälle, die dort nicht
    gefunden werden, sind der Normalfall beim **ersten** Ladevorgang — für sie
    wird nichts gelöscht, und das ist kein Fehler.

    Ohne ``properties`` verhält sich die Funktion wie ``store.load_turtle`` —
    reines Anhängen, also genau das bisherige Verhalten.

    Der Turtle-Text geht unverändert an Fuseki (kein rdflib-Roundtrip), damit
    die angehängten RDF-star-Blöcke erhalten bleiben (CLAUDE.md,
    „RDF-star-Falle"; ADR-0002).
    """
    if properties:
        resolved = [c for c in resolve_case_iris(store, submitter_ids or []) if is_iri(c)]
        replace_case_properties(store, case_iris=resolved, properties=properties)
    store.load_turtle(turtle)
