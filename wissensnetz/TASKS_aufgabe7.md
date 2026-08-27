# Aufgabe 7 (nur): Alle Oviedo-Krebsarten über das eigene Backend laden & anzeigen

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md` (dauerhafte Regeln/Komponentengrenze).
Setze **ausschließlich diese Aufgabe** um. Erlaubte Bereiche (Marcels Komponenten):
`wissensnetz/` und `scripts/`. **NICHT** `mediator/`, **NICHT** `wrappers/` editieren;
Fixture `data/sample/cases_brca_sample.ttl` nicht von Hand ändern. Keine Krebs-/
Klinikdaten erfinden — sie kommen ausschließlich echt über den bestehenden Pfad
GDC-Wrapper → Mediator `/transform` → Fuseki. Branch `Wissensnetz`, kleine Commits.
Aufgabe 5 (Hover) und 6 (Morph-Engine) sind umgesetzt; du baust darauf auf.

## Ziel
MP-Lite soll dieselben Krebsarten (TCGA-Kohorten) enthalten und farbig anzeigen wie
das Original von Oviedo — aber befüllt über euer eigenes Backend statt über Xena.
Zwei Teile:
- **Teil A (Daten):** alle 32 Oviedo-Kohorten über `scripts/load_gdc.py` ins
  Wissensnetz laden.
- **Teil B (Anzeige):** MP-Lite liest die echten Fälle aus dem Graphen (statt der
  4 fest verdrahteten Barcodes + 20 synthetischen Punkte) und färbt nach Krebsart
  mit stabiler Palette + Legende.

## Oviedo-Kohorten (kanonische Reihenfolge — für Loader UND Farb-/Legendenordnung)
GDC-project_id = `TCGA-<code>`. Reihenfolge exakt wie bei Oviedo (bestimmt die Farbe):
  ACC, CHOL, BLCA, BRCA, CESC, COAD, UCEC, ESCA, GBM, HNSC, KICH, KIRC, KIRP, DLBC,
  LIHC, LGG, LUAD, LUSC, SKCM, MESO, UVM, OV, PAAD, PCPG, PRAD, READ, SARC, STAD,
  TGCT, THYM, THCA, UCS
Diese Liste als eine Konstante an EINER Stelle definieren (z. B.
`wissensnetz/prototype/mp_lite/cohorts.py` -> `OVIEDO_COHORTS`) und in Teil A und B
wiederverwenden (Single Source of Truth).

## Worauf du aufbaust (vorhandener Code, nicht neu erfinden)
- `scripts/load_gdc.py` — lädt AKTUELL genau ein Projekt: POST `<mediator>/transform`
  `{source:"gdc", project_id, access, size}` -> `turtle` -> `GraphStore.load_turtle`.
  Mehrfachaufrufe akkumulieren im Default-Graph. CLI: `--project --size --access
  --mediator-url --graph`.
- `wissensnetz/prototype/mp_lite/app.py` — nutzt aktuell `IN_GRAPH` (4 Barcodes) +
  `SYNTHETIC` (20), `case_context()` je Barcode, Farb-Logik `color=[...]`,
  Morph-Engine + Slider (Aufgabe 6), Hover (Aufgabe 5).
- `wissensnetz/src/wissensnetz/enrichment.py` — `case_context(store, barcode)`
  (Einzelfall). Für viele Fälle brauchst du eine neue Sammel-Leseabfrage (s. u.).
- `wissensnetz/prototype/mp_lite/encodings.py` — `circular_encoding`, `is_encodable`.

## Teil A — Deliverables (Daten laden, in `scripts/`)

### 1) `scripts/load_gdc.py` um Multi-Projekt/Pancancer erweitern
- `--project` weiterhin unterstützen (Einzelprojekt, rückwärtskompatibel).
- NEU `--pancancer`: lädt alle `OVIEDO_COHORTS` nacheinander (je ein
  `/transform`-Aufruf pro Projekt, Ergebnisse akkumulieren im Default-Graph).
  Alternativ `--projects TCGA-ACC,TCGA-BRCA,…` für eine explizite Liste.
- `--size` gilt pro Projekt (Default 50; für Pancancer bewusst moderat halten,
  32×50 = ~1600 Fälle — reicht für den Prototyp).
- Robust: schlägt ein einzelnes Projekt fehl (leeres Ergebnis/HTTP-Fehler),
  Warnung ausgeben und mit dem nächsten weitermachen, NICHT abbrechen. Am Ende
  Zusammenfassung: geladen/übersprungen je Projekt + Gesamt-Case-Count aus dem
  Store.
- Die Kohorten-Konstante aus `prototype/mp_lite/cohorts.py` importieren (oder,
  falls das aus `scripts/` unpraktisch ist, die Liste in einem kleinen gemeinsamen
  Modul `wissensnetz/src/wissensnetz/cohorts.py` halten und von beiden Seiten
  importieren — dann ist es Teil des Pakets, sauberer). Entscheide dich für EINE
  Quelle und dokumentiere sie.
- `start_all.ps1` NICHT zwingend anfassen; optional einen Hinweis in `RUNBOOK.md`
  ergänzen, wie man Pancancer lädt (`python scripts\load_gdc.py --pancancer`).

## Teil B — Deliverables (Anzeige, in `wissensnetz/`)

### 2) Sammel-Leseabfrage — `src/wissensnetz/enrichment.py`
Neue Funktion `all_cases(store, *, limit: int | None = None) -> list[dict]`:
- EINE SPARQL-SELECT über alle `?c a db:Case` (nicht 1600× `case_context`!),
  die pro Fall zurückgibt: `submitter_id`, `project_id` (über
  `db:belongsToProject`/`db:projectId`), `gender`, und — sofern vorhanden — die in
  Aufgabe 5 ergänzten Felder (race, ethnicity, vital_status; erste Diagnose:
  primary_diagnosis-Label, tumor_stage, morphology, site, has_metastasis).
- Fehlende Werte als `None`. Tolerant/robust wie die bestehenden
  enrichment-Funktionen (gebundene Muster, keine ungebundenen `SELECT *`).
- Kurzer Docstring + Test (s. Verifikation).

### 3) MP-Lite auf echte Fälle umstellen — `prototype/mp_lite/app.py`
- Statt `IN_GRAPH`/`SYNTHETIC`: beim Start `all_cases(store)` aufrufen und die
  `ColumnDataSource` daraus bauen (`tumor` = submitter_id, plus die Oviedo-
  Hover-Spalten aus Aufgabe 5, `cancer` aus project_id abgeleitet wie gehabt).
- **Fallback:** ist der Store leer/nicht erreichbar (`all_cases` liefert nichts),
  auf die bisherige Beispiel-/Synthetik-Logik zurückfallen, damit die App
  standalone lauffähig bleibt. Die Fixture-Autoladung als Fallback behalten.
- **Coloring nach Krebsart:** stabile Farbe je Kohorte über `OVIEDO_COHORTS`
  (Index in der Liste -> Farbe aus einer spektralen Colormap, z. B. matplotlib
  `nipy_spectral`, wie im Original). Unbekannte/fehlende Kohorte -> neutrales Grau.
  Farbe je Fall in eine CDS-Spalte `color` schreiben.
- **Legende:** eine nach Krebsart gruppierte Legende zeigen (Bokeh
  `legend_field`/`legend_group` auf der `cancer`-Spalte, oder eine kompakte
  Farb-Legenden-Liste als `Div` in der Seitenspalte in `OVIEDO_COHORTS`-Reihenfolge).
  Ergebnis soll der Oviedo-Legende (Screenshot) entsprechen.
- Morph-Engine (Aufgabe 6) unverändert weiternutzen: die Encodings jetzt über die
  echten Fälle rechnen — insbesondere wird die `cancer`-Kreis-Encodierung mit 32
  echten Kohorten aussagekräftig (der „cancer"-Slider trennt die Kohorten sichtbar).
  Basis-Views „genes"/„miRNA" bleiben bis zur Expressionsdaten-Integration
  synthetisch (siehe HANDOFF_morphing_daten.md), Punktzahl an die echte Fallzahl
  anpassen.
- Hover (Aufgabe 5) und Rückkanal ③ bleiben funktionsfähig.

## Verifikation
- Teil A trocken prüfbar ohne Vollastlauf: `python scripts/load_gdc.py --pancancer
  --size 3` gegen laufenden Mediator+Fuseki lädt ≥ mehrere Kohorten; Fehlschlag
  einzelner Projekte bricht den Lauf nicht ab; Abschluss-Summary erscheint.
  (Falls Mediator/Fuseki im Dev nicht laufen: zumindest `--help` und der
  Projekt-Loop-Code per Lesen/Unit-Test der Projektliste prüfen.)
- `all_cases`: Unit-/Integrationstest in `tests/` (mit `loaded_store`-Fixture,
  Skip ohne Fuseki): liefert für die BRCA-Fixture die 4 Fälle mit `submitter_id`
  und `project_id="TCGA-BRCA"`; neue Felder dürfen `None` sein; keine Exception.
- `bokeh serve --show wissensnetz/prototype/mp_lite/app.py`: nach einem
  Pancancer-Load sind Punkte mehrerer Kohorten sichtbar, je Krebsart eingefärbt,
  Legende entspricht `OVIEDO_COHORTS`; „cancer"-Slider trennt die Kohorten.
  Bei leerem Store startet die App weiterhin (Fallback).
- Bestehende Tests bleiben grün: `pytest wissensnetz/tests -q`.

## Grenzen / Hand-off
- Kein Fremd-Code: Wrapper (Julian) und Mediator (Pablo) bleiben unberührt — sie
  liefern die Kohorten bereits über den bestehenden `/transform`-Pfad; wenn ein
  Feld/Projekt fehlt, ist das ein Daten-/Backend-Thema für den jeweiligen
  Verantwortlichen, nicht hier zu „reparieren".
- Expressionsbasierte Ansichten (genes/miRNA-tSNE) bleiben offen -> weiterhin in
  `HANDOFF_morphing_daten.md` (Aufgabe 6). Diese Aufgabe bringt die Krebsarten &
  ihre Färbung, nicht die Expressions-Landkarte.
