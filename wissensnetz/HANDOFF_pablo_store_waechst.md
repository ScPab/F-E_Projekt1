# Hand-off an Pablo: Der Store wächst mit den Aufrufen

**Von:** Marcel (Wissensnetz)
**Datum:** 2026-09-17
**Bezug:** `wissensnetz/HANDOFF_review_selection.md`, Befunde B1 und B2
**Status dieses Dokuments:** ersetzt die Lösungsvorschläge zu B1 und B2. Die Befunde selbst
bleiben gültig, der Weg dorthin ändert sich.

---

## Die Festlegung

Der Store ist **nicht** global vorbefüllt und enthält nicht alles. Er ist leer, wenn das
System startet, und **wächst mit den Aufrufen**. Jeder `/selection/*`-Aufruf schreibt seinen
Wissensbestand hinein. Danach ist der Store die Quelle für `obs`, aber immer nur im Umfang
der jeweiligen Auswahl.

Damit ist die Richtung wieder die aus dem Konzept: der Mediator **lädt in den Store hinein**
und liest anschließend zurück, was er selbst geschrieben hat. Er liest nicht mehr aus einem
Bestand, der auf einem anderen Weg entstanden sein muss.

Das ist der Unterschied zu meinem ersten Vorschlag in B2. Dort hatte ich empfohlen, die
Cases am Store vorbei direkt an `build_obs` zu geben. Das wäre kürzer, aber falsch: dann
gäbe es zwei Wahrheiten über dieselben Daten, und das Wissensnetz wäre für das `.h5ad`
bedeutungslos. Bitte den Weg unten nehmen.

## Zwei Ebenen im Store

| Ebene | Inhalt | Ort | Lebensdauer |
|---|---|---|---|
| Wissensbestand | Case, Demographic, Diagnosis, Sample, dynamische Properties | **Default-Graph** | wächst, bleibt |
| Auswahl-Manifest | welche Proben und Fälle zu einer Auswahl gehören, plus die Auswahlparameter | **Named Graph** `http://databridge.hka/graph/selection/<recipe_key>` | je Aufruf, verwerfbar |

Warum getrennt: läge der Wissensbestand je Auswahl in einem eigenen Named Graph, stünden
dieselben Case-Tripel als Quads mehrfach im Store, und ein `DROP GRAPH` einer Auswahl würde
Wissen löschen, das eine andere Auswahl noch braucht. So bleibt der Bestand gemeinsam und
die Zugehörigkeit trotzdem nachvollziehbar.

Der Bestand ist dabei von selbst dedupliziert, weil die Instanz-IRIs in deinem Mapping
deterministisch aus `case_id` gebildet werden (`INSTANCE_BASE + "case/" + _slug(...)`) und
RDF eine Menge ist: dieselbe Aussage zweimal zu laden ändert nichts.

## Die neue Reihenfolge

Heute baut `_build_anndata_from_hits` die `obs`, bevor irgendetwas geladen wurde, und
geladen wird auf diesem Pfad ohnehin nie. Neu:

```
Abruf (fetch_selection_files)
  → Übersetzung (cases_to_graph)
  → LADEN in den Default-Graph                 ← neu
  → Auswahl-Manifest in den Named Graph        ← neu
  → obs aus dem Store, begrenzt auf die Auswahl ← geändert
  → Matrix, .h5ad
```

**Laden kommt vor `obs`.** Das ist die eigentliche Änderung.

## P1 · Vorschau schreibt auch

`POST /selection/preview` lädt seinen Wissensbestand ebenfalls in den Store. Das klingt
zunächst gegen die Regel "Vorschau ist billig", ist aber genau richtig: es sind nur
Metadaten, keine Matrizen, und die Vorschau-Darstellung soll ja aus dem Wissensnetz kommen.
Wenn die Vorschau nichts schreibt, hat die Darstellung keine Quelle.

Damit ist die offene Entscheidung 7.3 aus dem Umsetzungsplan beantwortet:

- `preview` = Abruf, Übersetzung, Laden. Keine Rohdaten, keine Matrix.
- `generate` = dasselbe, plus Download und `.h5ad`. Das Laden ist idempotent, eine vorher
  angezeigte Auswahl wird also nicht doppelt geschrieben.

Ein `load: bool = True` in `SelectionRequest` ist sinnvoll, damit man das im Test abschalten
kann. Standard bleibt an.

## P2 · Manifest über die Funktion aus dem Wissensnetz schreiben

Das Vokabular für Auswahlen gehört mir, damit wir nicht zwei Varianten davon bekommen. Ich
liefere dir dafür eine Funktion, du brauchst kein Turtle selbst zu bauen:

```python
from wissensnetz.selection import write_selection

graph_iri = write_selection(
    store,
    selection_id=recipe_key,
    source=level.source,
    cohorts=level.cohorts,
    modality=level.modality,
    attributes=level.attributes,
    submitter_ids=[...],   # aus dem geteilten Abruf
    sample_ids=[...],      # aus dem geteilten Abruf
)
```

Die Signatur ist die Naht. Ich ändere sie nach der Übergabe nicht mehr ohne Absprache.
Beides, `submitter_ids` und `sample_ids`, hast du in `_build_anndata_from_hits` bereits in
`sample_case_map` vorliegen.

Die Sample-IRIs bilde ich nach derselben Regel wie dein Mapping
(`INSTANCE_BASE + "sample/" + _slug(sample_id)`). Falls du die Regel änderst, sag es mir,
sonst zeigt das Manifest ins Leere. Ich nagle sie bei mir in einem Test fest.

## P3 · `obs` auf die Auswahl begrenzen

`main.py` Zeile 824 wird ersetzt:

```python
# vorher
cases_by_submitter = {c["submitter_id"]: c for c in all_cases(store) if c.get("submitter_id")}

# nachher
from wissensnetz import cases_for_selection
cases_by_submitter = {
    c["submitter_id"]: c for c in cases_for_selection(store, selection_id) if c.get("submitter_id")
}
```

Gleiche Rückgabeform wie `all_cases()`, deshalb bleibt `build_obs` unverändert und
`_OBS_CASE_FIELDS` passt weiter.

**Übergangslösung, falls du nicht auf mich warten willst:** `all_cases(store)` behalten und
das Ergebnis auf die `submitter_ids` filtern, die du aus dem Abruf ohnehin hast. Das ist
eine Zeile, liefert dasselbe Ergebnis für den Moment, und lässt sich später gegen
`cases_for_selection` tauschen. Nicht schön, aber unblockiert.

## P4 · Entscheidung: ersetzen oder anhäufen

Wächst der Store, tritt ein Fall auf, den es vorher nicht gab: dieselbe Fall-IRI wird ein
zweites Mal geladen, und GDC hat den Wert inzwischen geändert. Identische Tripel kollabieren,
**unterschiedliche nicht**. Dann hängen an `db:gender` zwei Werte, und `build_obs` sowie
MP-Lite erwarten einen.

Zwei Möglichkeiten:

- **Ersetzen je Fall.** Vor dem Laden ein `DELETE WHERE` auf das Subgraph des Falls. Sauber,
  kostet je Auswahl eine Update-Abfrage.
- **Anhäufen und in Kauf nehmen.** Billiger, aber der Fehler tritt später und unerklärlich
  auf, nämlich als doppelte Zeile in der `obs`.

Mein Vorschlag: ersetzen, und zwar von Anfang an, weil der Fehler sonst erst in der
Auswertung auffällt. Wenn du das aufschieben willst, dann bitte mit einem Kommentar an der
Ladestelle, damit wir wissen, dass es eine bewusste Schuld ist. Sag mir Bescheid, wenn das
Löschen auf meiner Seite liegen soll, dann liefere ich es mit dem Rest.

## P5 · Cache-Treffer nachziehen (unverändert aus N3)

`wrapper.cache.materialized` wird bisher nur in `/export/anndata` genutzt. Mit dem
wachsenden Store lohnt es doppelt: eine wiederholte Auswahl soll weder erneut herunterladen
noch erneut in den Store schreiben. Prüfung vor dem Download, `set` danach, Schlüssel ist
der vorhandene `recipe_key`.

## Was das für die Blocker bedeutet

- **B1** ist mit P1 und P2 erledigt: das Turtle erreicht den Store, und die Zugehörigkeit
  ist festgehalten.
- **B2** ist mit P3 erledigt, aber auf dem anderen Weg als zuerst vorgeschlagen: nicht am
  Store vorbei, sondern durch ihn hindurch.

## Abnahmetest, angepasst

Der Test aus dem Umsetzungsplan wird dadurch strenger und aussagekräftiger. Voraussetzung:
**leerer Store**, also `docker compose down -v` für `graph-db`, dann `wissensnetz init`.

1. Auswahl A: Kohorte `TCGA-BRCA`, Attribute `gender`, `tumor_stage`, an
   `POST /selection/generate`.
2. `wissensnetz selection <recipe_key_A>` zeigt die Fälle der Auswahl.
3. Die `obs` des `.h5ad` hat `gender` und `tumor_stage` gefüllt, **ohne** dass vorher ein
   `/transform`-Lauf stattgefunden hat. Das ist der Kern.
4. Auswahl B: Kohorte `TCGA-KIRC`, an `POST /selection/preview`.
5. `wissensnetz selections` zeigt jetzt zwei Auswahlen. Der Store ist gewachsen.
6. `wissensnetz selection <recipe_key_A>` zeigt weiterhin **nur** BRCA-Fälle, obwohl KIRC
   inzwischen im Store liegt. Das ist der Beweis, dass die Begrenzung greift.

Schritt 6 ist der, der heute nicht funktionieren kann, weil `all_cases(store)` nicht
zwischen Auswahlen unterscheidet.

## Reihenfolge

P3 hängt an meiner Lieferung, alles andere nicht. Sinnvoll:

1. P1, Laden einbauen, mit `load: bool` im Request.
2. P4 entscheiden, am besten gleich mit P1 umsetzen.
3. P5, Cache-Treffer.
4. P2 und P3, sobald `wissensnetz.selection` von mir da ist. Ich melde mich, sobald die
   Funktionen stehen und die Tests grün sind.

Bis dahin kannst du mit der Übergangslösung aus P3 arbeiten, dann ist der Abnahmetest bis
Schritt 5 schon durchspielbar.
