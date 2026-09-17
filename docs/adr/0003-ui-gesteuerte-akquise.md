# ADR-0003: UI-gesteuerte Akquise mit einem gemeinsamen Abrufschritt

**Status:** Angenommen
**Datum:** 2026-09-17

## Kontext

Bis Anfang September folgte die Kette dem Muster "erst laden, dann filtern".
`scripts/load_gdc.py --pancancer` zog alle 32 TCGA-Kohorten in den Store, das Ergebnis lag
als 45 MB großes `wissensnetz/data/pancancer.h5ad` im Repo, der Recipe-Cache des Mediators
hatte rund 150 Einträge, und MP-Lite las über `all_cases()` alles, was im Graphen stand. Die
angezeigte Sicht ergab sich damit aus dem, was zufällig geladen war, nicht aus der
Fragestellung. Der HTTP-414-Fehler bei `build_manifest()` (320 Datei-IDs in einem Aufruf)
war ein Symptom desselben Musters.

Verschärfend kam hinzu, dass die beiden Ausgabeformen aus **zwei unabhängigen Abrufen**
entstanden: `POST /transform` holte `search("cases", …)` und baute daraus die Tripel,
`POST /export/anndata` holte `query("files", …)` mit einer anderen Feldliste und baute
daraus die Matrix. Zwei Abrufe, zwei unabhängig gezogene Stichproben, die auseinanderlaufen
können. Daher stammten zwei Notlösungen: der GDC-Fallback in `build_obs()` (siehe
`wissensnetz/Tasks Archiv/HANDOFF_obs_fallback.md`) und das stratifizierte Sampling über
`per_project_size` (siehe `wissensnetz/Tasks Archiv/HANDOFF_export_stratified.md`).

Zugleich fehlte die Vorderkante vollständig: kein Endpunkt nahm eine fachliche Auswahl an,
`TRANSFORM_CASE_FIELDS` war eine feste Liste mit 15 Einträgen, und es gab keinen
Unterschied zwischen einer billigen und einer teuren Anfrage.

Das Team hat mehrere Konzepte erarbeitet und sich für die Variante "die Oberfläche treibt,
der Mediator übersetzt und verzweigt" entschieden. Grundlage sind die Handskizze vom
2026-09-17 und `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md`.

## Entscheidung

1. **Die Auswahl in der Oberfläche ist der Auftrag.** Sie wird als JSON übergeben und ist
   der Vertrag zwischen Oberfläche und Kette (`SelectionRequest` in
   `mediator/app/schemas.py`). Das Panel hat vier Zeilen: Kohorte, Modalität, klinische
   Attribute, Datenquelle.

2. **Die Kette ist linear.** Auswahl, JSON, Wrapper, Mediator, dann zwei Senken:

   ```
   Auswahl → JSON → Wrapper (API) → Mediator (Übersetzung) → ┬→ Wissensnetz
                                                             └→ anndata
   ```

   Der Mediator entscheidet dabei **nicht** über Inhalte. Er ist Übersetzer und Verzweigung,
   nicht Dirigent. Insbesondere befragt er das Wissensnetz nicht, um die Oberfläche zu
   befüllen.

3. **Ein Abruf, ein Proben-Set, zwei Serialisierungen.** Die Probenmenge wird einmal
   bestimmt (`fetch_selection_files()` in `mediator/app/main.py`), danach wird dieselbe
   Menge zweimal weggeschrieben, einmal als RDF, einmal als `.h5ad`. Technisch möglich, weil
   GDC bei `cases.<feld>`-Feldern die verschachtelte Case-Struktur mit den Datei-Treffern
   mitliefert.

4. **Klinische Attribute sind Trigger, keine Filter.** Ein gewähltes Attribut erweitert den
   Auftrag. Die bei der Quelle angefragten Felder werden daraus abgeleitet
   (`resolve_case_fields()`), sie sind keine Konstante mehr.

5. **Unbekannte Attribute werden dynamisch abgebildet.** Bekannte Attribute nutzen ihre in
   `databridge-core.ttl` deklarierte `db:`-Property (`KNOWN_ATTRIBUTES`), unbekannte werden
   über `resolve_attribute()` auf eine neue Property abgebildet und per
   `_declare_dynamic_property()` **inline im Ausgabegraphen** deklariert. Die kuratierte
   Basis-Ontologie bleibt im Besitz des Wissensnetz-Teilbereichs und wird nicht automatisch
   ergänzt.

6. **Zwei Aktionen mit unterschiedlichen Kosten.** `POST /selection/preview` macht den
   geteilten Abruf ohne Messmatrizen, `POST /selection/generate` zusätzlich das `.h5ad`. Die
   Vorschau lädt keine Rohdaten herunter.

7. **Auswahl-Ebenen sind parallel und gleichrangig.** Die gestapelten Panelkopien ("weitere
   Ebene") sind mehrere eigenständige Auswahlen zum Vergleich, keine UND-verknüpfte
   Verfeinerung. Jede Ebene bekommt ihr eigenes Proben-Set und ihre eigene Serialisierung.

8. **Zwei Identitäten, klar getrennt.** Der Recipe-Schlüssel
   (`wrapper.cache.recipes.key_for`) ist die Identität der **Anfrage** und trägt Named Graph
   und Dateinamen. Der fachliche Join-Schlüssel über beide Senken hinweg ist
   `db:submitterId`, in MP-Lite die Spalte `tumor`.

9. **ADR-0001 bleibt unberührt.** Die Wrapper bleiben Python-Pakete im Mediator-Container.
   Fachlich geht der Auftrag an den Wrapper, technisch nimmt der Mediator ihn an und reicht
   ihn durch. Die Oberfläche spricht ausschließlich mit dem Mediator.

10. **Rückwärtskompatibilität.** `POST /transform` und `POST /export/anndata` bleiben in
    Signatur und Verhalten erhalten und nutzen intern denselben Abrufschritt.
    `TRANSFORM_CASE_FIELDS` wird aus `DEFAULT_ATTRIBUTES` abgeleitet und deckt exakt
    denselben Feldumfang ab wie die frühere Konstante.

## Betrachtete Alternativen

- **Voll-Ladung mit Filterung in der Oberfläche** (bisheriger Zustand). Verworfen: die
  geladene Menge ist von der Fragestellung entkoppelt, der Speicher- und Zeitbedarf wächst
  mit dem Bestand statt mit der Frage, und die Divergenz zwischen Graph und Matrix bleibt.

- **Drill-down über das Wissensnetz als Navigationsstruktur** (Gruppen-/Scope-Modell, siehe
  `docs/Konzept_Wissensnetz-Navigation.drawio`). **Zurückgestellt, nicht verworfen.** Der
  Ansatz ist inhaltlich stärker, weil er beide Achsen des Datenwürfels über NCIt und GO
  hierarchisiert und Sackgassen datengetrieben ausschließt. Er setzt aber zwei Dinge voraus,
  die es noch nicht gibt: eine gefüllte NCIt-Alignment-Tabelle mit geladener Hierarchie
  (siehe `wissensnetz/ontology/alignment/KANDIDATEN.md`) und Facetten-Zählungen im Wrapper.
  Entscheidung 7 schließt den Weg nicht aus, erfordert dann aber eine Erweiterung von
  `SelectionRequest` um eine Eltern-Beziehung zwischen Ebenen.

- **Mediator als Dirigent**, der anhand der Auswahl entscheidet, wo das Wissensnetz für die
  Oberfläche gebraucht wird, und dessen Labels und Wertelisten in das Panel einspeist.
  Zurückgestellt: für den ersten Durchgang beziehen die Auswahlfelder ihre Werte aus
  vorgespeicherten Attributen. Die Ausbaustufe ist im Umsetzungsplan als M10 und K5
  festgehalten.

- **Getrennte Abrufe je Senke beibehalten** und die Divergenz weiter über Fallbacks
  abfedern. Verworfen: die Fallbacks behandeln Symptome, und jeder neue Consumer bringt
  einen neuen Fallback mit.

- **Eigener Wrapper-Service, damit die Oberfläche direkt beim Wrapper anfragt.** Verworfen,
  weil es ADR-0001 aufheben würde, ohne dass ein Bedarf dafür belegt ist.

## Konsequenzen

**Positiv**

- Die geladene Menge folgt der Fragestellung. Die 414-Fehlerklasse entfällt, weil die
  Filtermengen klein bleiben.
- Graph und Matrix beschreiben dieselbe Probenmenge. `obs` kann direkt aus dem Abruf kommen,
  der GDC-Fallback in `build_obs()` wird damit überflüssig.
- Die Stratifizierung über `per_project_size` wird trivial, weil die Kohortenliste explizit
  aus der Auswahl kommt.
- Neue klinische Attribute brauchen keine Codeänderung mehr, nur einen Eintrag im Panel.
- Bestehende Endpunkte und Skripte laufen unverändert weiter.

**Zu tragen**

- Der Mediator wird komplexer. Er hält jetzt den gemeinsamen Abrufschritt, der vorher
  zweimal implizit in zwei Endpunkten steckte.
- Dynamisch erzeugte Properties stehen nicht in der kuratierten TBox. Bei aktivem
  OWL-Reasoning sind sie nur über die inline-Deklaration im jeweiligen Graphen bekannt.
- Die Panelzeile Modalität hat vorläufig einen wählbaren Wert, weil DNA-Methylierung und
  Mutationen nicht angebunden sind. Die Panelzeile Datenquelle hat vorläufig nur `gdc`.
- Parallele Ebenen können dieselbe Kohorte mehrfach abrufen. Ein Cache-Treffer je Ebene
  mildert das, sobald er greift.
- Die Frontend-Technologie ist noch nicht entschieden.

**Umsetzungsstand am 2026-09-17**

Umgesetzt: die Entscheidungen 1 bis 10 in Code, konkret `SelectionRequest`,
`POST /selection/preview`, `POST /selection/generate`, `fetch_selection_files()`,
`resolve_case_fields()`, `resolve_attribute()`, `_apply_attributes()`,
`_declare_dynamic_property()`.

Offen: das erzeugte Turtle wird noch nicht in den Store geladen, `obs` liest die
Klinikfelder weiterhin aus dem globalen Store statt aus dem Abruf, der Cache-Treffer fehlt
auf dem neuen Pfad, die neuen Endpunkte sind untestet, und die Oberfläche existiert nicht.
Einzelbefunde und Zuständigkeiten: `wissensnetz/HANDOFF_review_selection.md`.

**Revidieren, falls**

- die Drill-down-Variante gebraucht wird, weil die parallelen Ebenen für die Fragestellungen
  der Uni Oviedo nicht ausreichen,
- die Oberfläche Wertelisten samt Anzahl anbieten muss, statt mit vorgespeicherten
  Attributen auszukommen (dann werden Facetten im Wrapper und der Attributkatalog aus der
  TBox Teil der Entscheidung),
- oder eine Quelle hinzukommt, die die Probenzuordnung nicht mit den Datei-Treffern
  mitliefert, sodass Entscheidung 3 für sie nicht umsetzbar ist.

## Quellen

- `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md` (Abschnitte 1, 1b, 3 bis 8)
- Handskizze vom 2026-09-17 (Fensterlayout, Auswahlpanel, Ablaufkette)
- `docs/Konzept_Wissensnetz-Navigation.drawio` (zurückgestellte Alternative)
- `wissensnetz/Tasks Archiv/HANDOFF_export_stratified.md`,
  `wissensnetz/Tasks Archiv/HANDOFF_obs_fallback.md`
- `wissensnetz/ontology/alignment/KANDIDATEN.md`
- ADR-0001 (Wrapper als Python-Package), ADR-0002 (Graph-Speicherung)
