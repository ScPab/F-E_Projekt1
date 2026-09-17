# Antwort an Pablo (P4): Ersetzungslogik, und eine Korrektur meiner Empfehlung

**Von:** Marcel (Wissensnetz)
**Datum:** 2026-09-17
**Bezug:** deine Rückfrage zu P4 in `wissensnetz/HANDOFF_pablo_store_waechst.md`

---

## Kurz: du hast richtig gehandelt

Die Begründung stimmt, und sie deckt sich mit dem, was ich in P4 selbst angeboten hatte
("Sag mir Bescheid, wenn das Löschen auf meiner Seite liegen soll, dann liefere ich es mit
dem Rest"). Store-Semantik und Vokabular gehören ins Wissensnetz, sonst haben wir zwei
Varianten davon. Dass du es als bewusste Schuld im Docstring von
`_load_selection_knowledge` dokumentiert hast, statt es stillschweigend offen zu lassen, ist
genau die richtige Form. Daran ist nichts zu ändern.

**Der Rest von P1, P2, P3 und P5 ist bei mir angekommen und sieht gut aus.** Besonders die
Übergangslösung in Zeile 880 mit dem Filter auf `selected_submitters` plus dem Kommentar,
der auf `cases_for_selection` verweist. `wissensnetz.selection` und
`enrichment.cases_for_selection` stehen inzwischen, du kannst also von der
Übergangslösung auf die echte Funktion wechseln.

## Aber: meine P4-Empfehlung war zu grob

Ich hatte "ersetzen je Fall" empfohlen, also ein `DELETE WHERE` über das Subgraph des
Falls vor dem Laden. Beim Ausformulieren ist mir aufgefallen, dass das einen schlimmeren
Fehler erzeugt als den, den es behebt.

Der Store wächst mit den Aufrufen, und verschiedene Auswahlen fragen **verschiedene
Attributmengen** ab. Fall:

1. Auswahl A holt für `TCGA-BRCA` die Attribute `gender` und `tumor_stage`. Beide landen
   im Store.
2. Auswahl B holt dieselben Fälle, aber nur `gender`.

Mit "ersetzen je Fall" würde Schritt 2 das `tumor_stage` aus Schritt 1 **löschen**. Die
Vorschau von Auswahl A zeigt danach weniger als vorher, und niemand versteht, warum. Der
Store würde also nicht wachsen, sondern je nach letzter Anfrage schrumpfen. Das widerspricht
genau der Festlegung, um die es in dem Hand-off ging.

## Die richtige Semantik: ersetzen je Property, nicht je Fall

Gelöscht wird nur, was die aktuelle Nutzlast auch schreibt. Alles, was frühere Aufrufe
zusätzlich beigetragen haben, bleibt stehen.

- `gender` wird geschrieben, also wird vorher `db:gender` an diesem Fall gelöscht. Kein
  Doppelwert.
- `tumor_stage` wird nicht geschrieben, also wird es nicht angetastet. Kein Verlust.

Damit ist es ein echtes Upsert auf Property-Ebene, und der Store wächst monoton, außer in
den Werten, die tatsächlich neu geliefert werden.

## Was ich liefere, und wie du es aufrufst

Neues Modul `wissensnetz/src/wissensnetz/knowledge.py`, eine Funktion ersetzt deinen
`store.load_turtle(turtle)`-Aufruf in `_load_selection_knowledge`:

```python
from wissensnetz import load_knowledge

load_knowledge(
    store,
    turtle,
    submitter_ids=[...],                      # hast du aus dem geteilten Abruf
    properties=[                              # eine Zeile bei dir
        str(semantic_mapping.resolve_attribute(a).property_uri) for a in level.attributes
    ],
)
```

Warum `submitter_ids` und nicht die Case-IRIs: die IRI bildest du aus `case_id`, ich
bekomme von dir aber den Barcode. Nachschlagen statt nachrechnen, dafür gibt es
`selection.resolve_case_iris()` schon. Beim ersten Laden eines Falls findet sie nichts, dann
wird auch nichts gelöscht, und das Verhalten ist identisch zu heute.

Warum `properties` als Parameter und nicht von mir abgeleitet: die Zuordnung Attribut zu
`db:`-Property ist dein `resolve_attribute`, und die soll die einzige Wahrheit bleiben. Ich
würde sie sonst nachbauen, und genau das wollen wir beide nicht. Die Liste ist bei dir eine
Zeile, bei mir wäre es eine zweite Tabelle.

`load_knowledge` macht dann: Case-IRIs auflösen, die genannten Properties an genau diesen
Fällen löschen, danach dein Turtle unverändert und roh laden. Reihenfolge und Rohübertragung
bleiben wie bei `load_turtle`, die RDF-star-Blöcke gehen also nicht verloren.

## Zwei Feinheiten, die ich bei mir abfange

**Die Alignment-Aussage hängt an einer zweiten Property.** `primary_diagnosis` ist in
`KNOWN_ATTRIBUTES` auf `db:primaryDiagnosisLabel` abgebildet, das NCIt-Alignment schreibt
zusätzlich `db:primaryDiagnosis` (`mapping.py` Zeile 308) und dazu eine RDF-star-Annotation.
Deine Property-Liste enthält also nur das Label. Ich behandle `db:primaryDiagnosis` und die
zugehörige Stern-Annotation als Anhang von `db:primaryDiagnosisLabel` und räume beides mit
ab. Du musst dafür nichts ergänzen.

**Was nicht gelöscht wird.** Projekt-Knoten (die sind kohortenweit geteilt), die TBox, die
Named Graphs der Auswahlen und die Nutzer-Graphen des Rückkanals. Letztere zeigen über
`oa:hasTarget` auf Proben-IRIs, und weil die IRIs deterministisch sind, bleiben die Verweise
nach einem Upsert gültig.

## Zeitplan und was bis dahin gilt

Die Aufgabe liegt als `wissensnetz/TASKS_aufgabe14.md` bereit und ist klein. Ich melde mich,
sobald `load_knowledge` steht und die Tests grün sind, insbesondere der entscheidende: zwei
Auswahlen mit unterschiedlichen Attributmengen auf denselben Fällen, danach muss das
Attribut aus dem ersten Aufruf noch da sein und keine Property zwei Werte haben.

**Bis dahin bitte nichts ändern.** Reines Anhängen ist der richtige Zwischenzustand: es
verliert nichts und der Doppelwert tritt nur auf, wenn GDC zwischen zwei Aufrufen einen Wert
ändert, was in unserem Testzeitraum unwahrscheinlich ist. Wenn `load_knowledge` da ist,
tauschst du eine Zeile und kannst den Schuld-Absatz aus dem Docstring streichen.

## Eine Bitte für den Bericht

Der Fall, den ich oben beschrieben habe, ist ein gutes Beispiel für die Konsequenzen des
wachsenden Stores und gehört in ADR-0003 unter "Zu tragen". Ich ergänze das dort, sobald
`load_knowledge` steht, damit die Entscheidung mit ihrer tatsächlichen Semantik im Bericht
steht und nicht mit meiner ersten, groben Fassung.
