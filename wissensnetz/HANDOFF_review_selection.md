# Review: Auswahl-Endpunkte und gemeinsamer Abrufschritt

**An:** Pablo (Mediator), Julian (Wrapper)
**Von:** Marcel (Wissensnetz)
**Datum:** 2026-09-17
**Gegenstand:** Umsetzung von M1 bis M7 aus `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md`
**Geprüfte Fassung:** `mediator/app/main.py` (40.586 B), `mediator/app/schemas.py` (14.406 B),
`mediator/app/semantic/mapping.py` (15.940 B), `wrappers/gdc/client.py` (20.654 B),
`wrappers/tests/test_gdc_client.py` (14.557 B). Alle vier syntaktisch geprüft.

---

## Zusammenfassung

Der schwierige Teil ist gelungen, die letzte Meile fehlt. M3 bis M5 sind sauber gelöst,
teils besser als im Plan skizziert. Offen sind zwei Punkte, die zusammen dazu führen, dass
Punkt 8 des Konzepts ("der Mediator gibt das Ergebnis an das Wissensnetz") noch nicht
erfüllt ist, obwohl die gesamte Vorarbeit dafür vorliegt.

Zwei Blocker, drei wichtige Punkte, eine Doku-Sammelposition, eine Rückfrage.

## Was gut gelöst ist

**Der gemeinsame Abrufschritt.** `fetch_selection_files()` (`main.py` ab Zeile 85) fragt pro
Kohorte einmal den Files-Endpunkt ab und lässt sich die Case-Objekte über `cases.<feld>`
gleich mitliefern, dedupliziert nach `case_id` und gibt sie direkt
`cases_to_graph`-kompatibel zurück, ohne Umformung. Ein Abruf, zwei Verwendungen. Das ist
eleganter als der Vorschlag im Plan, der noch von zwei Schritten ausging.

**Der Altpfad wurde mitgezogen.** `/export/anndata` nutzt denselben Abrufschritt, und
`TRANSFORM_CASE_FIELDS = resolve_case_fields(DEFAULT_ATTRIBUTES)` deckt exakt dieselben elf
Attribute ab wie die frühere Konstante. Kein zweiter Codepfad, kein Verhaltensbruch für
`/transform`.

**Die Trigger-Idee ist vollständig durchgezogen.** `KNOWN_ATTRIBUTES`, `resolve_attribute()`
und `_apply_attributes()` ersetzen die if-Kaskade pro Feld. Die offene Entscheidung zu
undeklarierten Properties ist mit `_declare_dynamic_property()` besser beantwortet als in
beiden Optionen, die der Plan angeboten hat: die Property wird inline im Ausgabegraphen
deklariert, die kuratierte TBox bleibt unberührt. Danke, das respektiert die
Komponentengrenze genau.

**Vorschau und Generieren sind echt getrennt**, und eine fehlschlagende Ebene setzt
`status="error"` statt die ganze Anfrage abzubrechen.

---

## B1 · Blocker · Das Turtle erreicht den Store nicht

**Befund.** `load_turtle` kommt in `main.py` genau einmal vor, in Zeile 567, also im alten
`/transform`. `/selection/preview` und `/selection/generate` setzen `result.turtle` und
geben den Text zurück, schreiben ihn aber in keinen Store.

**Warum das zählt.** Damit ist der rechte Zweig der Verzweigung aus dem Konzept nicht
angeschlossen. Die Oberfläche müsste das Turtle selbst nehmen und laden, was der Variante
widerspricht: die Oberfläche soll nur auswählen und anzeigen.

**Vorschlag.** `SelectionRequest` um `load: bool = True` erweitern und in beiden Endpunkten
nach der Serialisierung in einen Named Graph je Auswahl schreiben. Die Konvention dafür
liefere ich (siehe "Was bei mir liegt"), Muster ist `graph_iri_for()` aus
`wissensnetz/src/wissensnetz/feedback.py` Zeile 124. `GraphStore.load_turtle(turtle,
graph=...)` kann das bereits, es fehlt nur der Aufruf.

**Owner:** Pablo, nach meiner Zusage der Graph-IRI-Konvention.

## B2 · Blocker · Die Klinikfelder landen nicht im `.h5ad`

**Befund.** `main.py` Zeile 824:

```python
cases_by_submitter = {c["submitter_id"]: c for c in all_cases(store) if c.get("submitter_id")}
```

Die `obs`-Klinikfelder kommen aus dem **globalen Store**, nicht aus den Cases, die
`_selection_fetch()` im selben Aufruf gerade geholt hat. `build_obs` dokumentiert die Folge
selbst: "Reichere Klinikfelder bleiben nur dort gefuellt, wo der Case im Graphen ist."

**Warum das zählt.** Wählt der Forscher `gender` und `tumor_stage`, stehen die Werte im
Turtle, aber im `.h5ad` bleiben die Spalten leer, solange dieselben Fälle nicht durch einen
früheren `/transform`-Lauf im Store liegen. Bei einem frischen Dataset ist die `obs` bis auf
`cancer` aus dem Projekt-Fallback leer. Der Datenfluss ist an dieser Stelle invertiert: der
Mediator liest aus dem Wissensnetz, statt hineinzuschreiben. Zusammen mit B1 heißt das: er
liest etwas, das er selbst nie geschrieben hat.

Nebenwirkung: `/selection/generate` bricht mit 503 ab, wenn Fuseki nicht erreichbar ist,
obwohl das Generieren den Store konzeptuell nicht braucht.

**Vorschlag.** `cases` an `_build_anndata_from_hits()` durchreichen und
`cases_by_submitter` daraus bauen, den Store höchstens als Ergänzung behalten. Das ist kein
Einzeiler, weil `build_obs` flache Schlüssel erwartet (`_OBS_CASE_FIELDS` in
`semantic/expression.py` Zeile 43: `gender`, `race`, `tumor_stage`, `primary_diagnosis`, …),
GDC-Cases aber verschachtelt sind (`demographic.gender`, `diagnoses[].primary_diagnosis`).

Die Abbildung ist aber schon vorhanden: die Schlüssel von `_OBS_CASE_FIELDS` sind genau die
Oviedo-Attributnamen aus `KNOWN_ATTRIBUTES`, und `resolve_attribute(attr).gdc_field` liefert
den zugehörigen Pfad. Eine generische Flatten-Funktion über `KNOWN_ATTRIBUTES` bedient
`build_obs` also ohne eine zweite Feldtabelle. Damit fällt der GDC-Fallback (M8) von selbst
weg.

**Owner:** Pablo.

## N3 · Wichtig · Kein Cache-Treffer auf dem neuen Pfad

`wrapper.cache.materialized` wird nur in `/export/anndata` benutzt (Zeilen 888 und 935).
`/selection/generate` lädt dieselbe Auswahl beim zweiten Aufruf komplett neu herunter. Der
`recipe_key` ist vorhanden und identisch zwischen Vorschau und Generieren, es fehlt nur die
Prüfung vor dem Download und das `set` danach. M7 verspricht "derselbe Pfad, kein
API-Aufruf", das gilt momentan nur für den Altpfad.

**Owner:** Pablo.

## N4 · Wichtig · Zwei Implementierungen derselben Zuordnung

`extract_sample_case_rows()` (`wrappers/gdc/client.py` Zeile 163) ist um `project_id`
erweitert und mit zwei neuen Tests abgedeckt, genau wie in W2 gewünscht. Benutzt wird die
Funktion aber nur wrapper-intern in `download_expression_files` (Zeile 436).
`_build_anndata_from_hits` baut die Zuordnung ein zweites Mal inline, und die Regeln
unterscheiden sich:

| | `extract_sample_case_rows` | Inline in `_build_anndata_from_hits` |
|---|---|---|
| Cases je Treffer | alle | nur `cases[0]` |
| Samples je Case | alle | nur `samples[0]` |
| fehlende `sample_id` | Zeile wird übersprungen | Fallback auf `file_id` |

Für TCGA-Quantifizierungsdateien ist das heute deckungsgleich, weil dort praktisch ein Case
und eine Probe je Datei stehen. Es ist aber genau die Doppelung, die die Variante beseitigen
sollte, und Julians Arbeit an W2 liegt momentan brach. Entweder der Mediator nutzt die
Wrapper-Funktion, oder die Wrapper-Funktion verschwindet aus dem Expressions-Pfad. Beides
ist besser als zwei Regeln.

**Owner:** Pablo und Julian gemeinsam, kurz abstimmen wer.

## N5 · Wichtig · Die neuen Endpunkte sind untestet

Für den Mediator gibt es weiterhin keine Testsuite, und `scripts/check_mediator.py` ist
unverändert vom 2026-08-19, kennt die neuen Endpunkte also nicht. Die 21 Wrapper-Tests sind
grün und in guter Qualität, aber der gesamte neue Pfad ist nur manuell geprüft.

Mit Blick auf die Berichtsabgabe am 30.9. reicht wenig: ein Test, der
`/selection/preview` mit einem gemockten `wrapper.query` gegen zwei Kohorten laufen lässt
und prüft, dass `requested_fields` die gewählten Attribute enthält und `triple_count > 0`
ist. Dazu eine Zeile in `check_mediator.py` je neuem Endpunkt.

**Owner:** Pablo.

## D6 · Doku · Verweise zeigen ins Leere

Sammelposition, alles kleine Korrekturen, aber sie stehen in frischem Code:

- Viele Docstrings verweisen auf `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf`. Im
  Repo liegt nur die `.md`, eine PDF gibt es nicht.
- `main.py` und `mapping.py` verweisen auf `wissensnetz/HANDOFF_anndata.md`. Die Datei
  existiert nicht mehr.
- Verweise auf `wissensnetz/HANDOFF_export_stratified.md` und `HANDOFF_obs_fallback.md`
  stimmen im Pfad nicht mehr, die Dateien liegen jetzt unter `wissensnetz/Tasks Archiv/`.
- Die Entscheidungsnummern sind teils vertauscht: die parallelen Ebenen sind Entscheidung
  7.2, nicht 7.5. In `schemas.py` steht beides in einem Satz.

**Owner:** Pablo, beim nächsten Durchgang mitnehmen.

## F7 · Rückfrage · Eine Entscheidung ist im Code gefallen

`levels` ist als Liste gleichrangiger, paralleler Auswahlen implementiert, ausdrücklich
nicht als UND-Verfeinerung. Das ist eine legitime Lesart der gestapelten Panels in der
Skizze, sie schließt aber die Drill-down-Variante aus dem früheren Konzept
(`docs/Konzept_Wissensnetz-Navigation.drawio`) für den ersten Durchgang aus.

Bitte einmal explizit bestätigen, bevor das Frontend darauf aufbaut. Es entscheidet, ob das
Panel Vergleich kann oder Vertiefung. Ich habe es so in ADR-0003 aufgenommen, als
Entscheidung mit der Drill-down-Variante als zurückgestellte Alternative.

---

## Was bei mir liegt

Damit B1 auflösbar ist, liefere ich zu:

1. Konvention und Anlage des Named Graph je Auswahl,
   `http://databridge.hka/graph/selection/<recipe_key>`, plus Aufräumen per `DROP GRAPH`.
2. Vorschau-Lesefunktion, die auf einen Auswahl-Graphen begrenzt ist, als Variante von
   `all_cases()`.
3. CLI-Befehl `wissensnetz preview <selection.json>`, damit die Kette ohne Oberfläche
   testbar ist.

Offen und nicht Teil dieses Durchgangs bleiben Facetten und Zählungen (W3), der
Attributkatalog aus der TBox (K5) und die weiteren Modalitäten (W6).

## Abnahmetest

Wenn B1 und B2 erledigt sind, ist der Test aus dem Umsetzungsplan erstmals durchführbar:

1. Ein Auswahl-JSON mit zwei Kohorten und den Attributen `gender` und `tumor_stage` an
   `POST /selection/generate` schicken.
2. `wissensnetz query` gegen den Auswahl-Graphen: Liste der `db:submitterId`.
3. `obs` des erzeugten `.h5ad`: Spalte `submitter_id`.
4. Beide Listen müssen übereinstimmen, und `gender` sowie `tumor_stage` müssen in der `obs`
   gefüllt sein, ohne dass vorher ein `/transform`-Lauf stattgefunden hat.

Punkt 4 ist der eigentliche Beweis, dass "ein Abruf, zwei Serialisierungen" trägt. Heute
kann der Test nicht bestehen.
