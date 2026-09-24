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

English: Growing knowledge base (task 14): upsert **per property**.

The mediator loads knowledge into the default graph on every
``/selection/*`` call (P1,
``mediator/app/main.py::_load_selection_knowledge``). Plain appending is not
enough: if GDC changes a value between two calls, two values then hang off
the same property, and both ``build_obs`` and MP-Lite expect one.

**Not "replace the case".** Different selections query different attribute
sets. A call with fewer attributes would otherwise delete what an earlier,
richer call contributed — the store would shrink depending on the last
request instead of growing (see ``HANDOFF_pablo_P4_ersetzen.md``).

**Instead, upsert per property:** only what the current payload also writes
is deleted. ``sex_at_birth`` is delivered, so ``db:sexAtBirth`` is dropped
beforehand for those cases; ``tumor_stage`` is not delivered, so it stays.
The store thus grows monotonically, except in the values that are actually
newly delivered.

The mapping *attribute name → ``db:`` property* stays with the mediator
(``resolve_attribute``) and comes in as a parameter — deliberately no
second table of it is created here (CLAUDE.md: don't rebuild the GDC→RDF
mapping).

**Seam to the mediator:** :func:`load_knowledge` replaces the
``store.load_turtle(turtle)`` call there. The signature no longer changes
without agreement once handed over.

What is **not** deleted, and why:

* **The TBox.** Per ``init.py`` it deliberately lives in the same default
  graph as the ABox. The deletion is anchored via ``VALUES ?case`` on
  instance IRIs and therefore never hits a class definition.
* **Project nodes.** They are shared cohort-wide, so
  ``db:belongsToProject`` is not in the path below.
* **Named graphs.** Selection manifests (task 13) and the feedback
  channel's user graphs (task 4). An update without a ``GRAPH`` clause only
  hits the default graph — verified for our Fuseki in
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
# EN: Link case -> sub-node (ontology/databridge-core.ttl, object
# properties). Per the TBox, the clinical fields do not hang off the case
# itself, but off the demographic/diagnosis/sample. The mediator mapping
# also generates the inverses (db:isDemographicOf, db:describesCase,
# db:isSampleOf), but they are unaffected when deleting datatype properties.
_SUBNODE_PATH = "(db:hasDemographic|db:hasDiagnosis|db:hasSample)?"

# Sonderfall NCIt-Alignment: `primary_diagnosis` ist im Mediator-Mapping auf
# db:primaryDiagnosisLabel abgebildet, das Alignment schreibt zusätzlich
# db:primaryDiagnosis (Objekt-Property auf das NCIt-Konzept) plus eine
# RDF-star-Annotation. Die Property-Liste des Mediators enthält nur das Label,
# deshalb behandeln wir das Alignment als dessen Anhang.
# EN: Special case NCIt alignment: in the mediator mapping,
# `primary_diagnosis` maps to db:primaryDiagnosisLabel; the alignment
# additionally writes db:primaryDiagnosis (an object property to the NCIt
# concept) plus an RDF-star annotation. The mediator's property list
# contains only the label, so we treat the alignment as its attachment.
PRIMARY_DIAGNOSIS_LABEL = f"{DB}primaryDiagnosisLabel"
PRIMARY_DIAGNOSIS = f"{DB}primaryDiagnosis"

# Fälle je Update-Abfrage. Eine Auswahl-Ebene hat höchstens 200 Proben
# (SelectionRequest.size), die Aufteilung ist also eher Vorsorge als Nötigung.
# EN: Cases per update query. A selection level has at most 200 samples
# (SelectionRequest.size), so the chunking is precautionary rather than
# strictly necessary.
_CHUNK = 100


def _property_term(ref: str) -> str:
    """SPARQL-Term für eine Property: volle IRI in spitzen Klammern, CURIE mit
    bekanntem Präfix unverändert (die Standard-``PREFIXES`` lösen sie auf).

    English: SPARQL term for a property: full IRI in angle brackets, CURIE
    with a known prefix unchanged (the standard ``PREFIXES`` resolve it).
    """
    r = ref.strip()
    if r.startswith("<") and r.endswith(">"):
        return r
    if is_iri(r):
        return f"<{r}>"
    return r  # CURIE, z. B. db:sexAtBirth / EN: CURIE, e.g. db:sexAtBirth


def _normalize_property(ref: str) -> str:
    """Volle IRI einer Property — nur für den ``db:``-Präfixvergleich.

    English: Full IRI of a property — only for the ``db:`` prefix comparison.
    """
    r = ref.strip().strip("<>")
    return f"{DB}{r[3:]}" if r.startswith("db:") else r


def _expand_properties(properties: list[str]) -> list[str]:
    """Property-Liste um die Anhänge des NCIt-Alignments ergänzen.

    Enthält sie ``db:primaryDiagnosisLabel``, kommt ``db:primaryDiagnosis``
    dazu — sonst bliebe der NCIt-Link einer Diagnose stehen, die gerade neu
    geschrieben wird.

    English: Extends the property list with the NCIt alignment's
    attachments.

    If it contains ``db:primaryDiagnosisLabel``, ``db:primaryDiagnosis`` is
    added — otherwise the NCIt link of a diagnosis that is just being
    rewritten would stay stale.
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

    English: Deletes exactly the named properties on exactly the named
    cases (and on their demographic/diagnosis/sample sub-nodes).

    Returns the number of update queries executed (0 if there was nothing
    to do). Empty ``case_iris`` or ``properties`` are not an error — on the
    first load of a case there is nothing to replace.

    The scoping happens via a property path with ``?`` (zero-or-once) from
    the case bound via ``VALUES``: zero steps hits the case itself, one
    step its sub-nodes.

    .. warning::
       The obvious variant of using ``BIND(?case AS ?s)`` in a ``UNION``
       branch while ``VALUES ?case`` sits outside the ``UNION`` is
       **wrong**: inside the branch ``?case`` is still unbound, so ``?s``
       stays free, and the ``DELETE`` hits the property on *all* subjects.
       Reproduced against our Fuseki; hence the path instead of the union.
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
        # EN: First the RDF-star annotations of the alignment, while the
        # diagnosis is still reachable via db:hasDiagnosis. Quoted triples
        # are independent of the asserted statement — without this step,
        # provenance would remain on a statement that no longer exists.
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

    English: Seam to the mediator: upsert per property, then load the
    Turtle **raw**.

    Call in the mediator (replaces ``store.load_turtle(turtle)``)::

        load_knowledge(
            store, turtle,
            submitter_ids=[...],        # from the shared fetch
            properties=[                # one line: resolve_attribute stays there
                str(semantic_mapping.resolve_attribute(a).property_uri)
                for a in level.attributes
            ],
        )

    ``submitter_ids`` instead of case IRIs, because the mediator forms the
    IRI from ``case_id`` but hands us the barcode: look up instead of
    recompute, via :func:`wissensnetz.selection.resolve_case_iris`. Cases
    not found there are the normal case on the **first** load — nothing is
    deleted for them, and that is not an error.

    Without ``properties`` the function behaves like ``store.load_turtle``
    — plain appending, i.e. exactly the previous behavior.

    The Turtle text goes to Fuseki unchanged (no rdflib round-trip), so the
    appended RDF-star blocks survive (CLAUDE.md, "RDF-star trap"; ADR-0002).
    """
    if properties:
        resolved = [c for c in resolve_case_iris(store, submitter_ids or []) if is_iri(c)]
        replace_case_properties(store, case_iris=resolved, properties=properties)
    store.load_turtle(turtle)
