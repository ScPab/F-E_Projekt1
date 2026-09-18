# Aufgabe 15 (nur): Startskript auf ADR-0003 umstellen, kein Vorladen mehr

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.
Betroffen sind `start_all.ps1` (Projekt-Wurzel), `scripts/run_selection.py`,
`scripts/load_gdc.py`, `scripts/fetch_pancancer_h5ad.py` und `RUNBOOK.md`. **NICHT**
`mediator/`, **NICHT** `wrappers/`. Kleine Commits, die Änderung an `RUNBOOK.md` als letzter.

`start_all.ps1` und `RUNBOOK.md` nutzen Pablo und Julian ebenfalls. Alle bisherigen
Parameter müssen weiter akzeptiert werden, siehe Abschnitt Grenze.

Kontext: `docs/adr/0003-ui-gesteuerte-akquise.md`,
`wissensnetz/HANDOFF_pablo_store_waechst.md`.

## Befund

`.\start_all.ps1` lädt beim Start immer noch den gesamten Bestand vor. Beobachtet:

```
=== Zusammenfassung ===
Geladen:      32/32  (58141 Tripel gesamt)
Cases im Store gesamt: 5387
   OK: GDC-Daten geladen (alle Kohorten).
-> Rufe Pancancer-Expressions-.h5ad ab (fetch_pancancer_h5ad.py --size 5) ...
Export: 32 Kohorte(n) in EINEM Aufruf (size=5, compute_tsne=true) über .../export/anndata …
```

Verursacher sind zwei Schritte im Skript:

- Schritt 6, Zeile 179: `python scripts\load_gdc.py --pancancer --size $Size ...` zieht alle
  32 Kohorten in den Store.
- Schritt 6c, Zeile 193: `python scripts\fetch_pancancer_h5ad.py --size $PancancerSize ...`
  ruft `POST /export/anndata` mit allen 32 Kohorten in einem Aufruf auf und legt das
  globale `wissensnetz/data/pancancer.h5ad` an.

Das ist genau der Zustand, den ADR-0003 ablöst: der Store soll leer starten und mit den
Aufrufen wachsen, und das globale `pancancer.h5ad` ist als Standardweg entfallen. Solange
das Startskript so bleibt, ist die ganze Umstellung im Betrieb nicht sichtbar, und der
Abnahmetest aus `HANDOFF_pablo_store_waechst.md` (Schritt 6: Auswahl A zeigt nur ihre
eigenen Fälle) kann nicht bestehen, weil schon alles im Store liegt.

## Ziel

Der Standardstart lädt **einen** Scope über `POST /selection/preview`, nicht 32 Kohorten.
Der alte Vollweg bleibt erhalten, aber nur auf ausdrückliche Anforderung.

## Deliverables

### 1) `scripts/run_selection.py` um `--out` erweitern
Das Skript gibt heute nur die `download_url` aus (Zeile 84), lädt die Datei aber nicht
herunter. Damit landet ein `.h5ad` aus `/selection/generate` nur im Mediator-Container und
MP-Lite findet es nicht.

Neuer Parameter `--out <pfad>`: nach erfolgreichem `--generate` die Datei über
`GET <mediator><download_url>` streamen und nach `<pfad>` schreiben. Muster übernehmen von
`_download()` in `scripts/fetch_pancancer_h5ad.py` (Zeile 99), inklusive Streaming und
Timeout. Ohne `--out` bleibt das Verhalten unverändert. Bei mehreren Ebenen die Datei der
**ersten** Ebene mit `status="ok"` nehmen und das in der Hilfe sagen.

Am Ende den Zielpfad ausgeben, damit das Startskript ihn weiterverwenden kann.

### 2) Demo-Auswahl als versionierte Datei
Neu: `scripts/selection_demo.json`, ein gültiger `SelectionRequest` mit genau einer Ebene:

```json
{
  "levels": [
    {
      "source": "gdc",
      "cohorts": ["TCGA-BRCA"],
      "modality": "gene_expression",
      "attributes": ["gender", "tumor_stage", "primary_diagnosis", "sample_type"]
    }
  ],
  "size": 20
}
```

Die Datei ist die Referenz für den Abnahmetest und für den Bericht. Feldnamen und
Wertebereiche gegen `mediator/app/schemas.py` (`SingleSelection`, `SelectionRequest`)
prüfen, nicht raten.

### 3) `start_all.ps1`: Schritt 6 und 6c ersetzen

Neue Parameter, zusätzlich zu den bestehenden:

| Parameter | Default | Wirkung |
|---|---|---|
| `-DemoCohort` | `TCGA-BRCA` | Kohorte des Demo-Scopes |
| `-DemoSize` | `20` | Proben im Demo-Scope |
| `-DemoGenerate` | aus | statt `preview` ein `generate`, also mit Download der Rohdaten und `.h5ad` |
| `-FullLoad` | aus | **ausdrücklich** der alte Weg: `load_gdc.py --pancancer` plus `fetch_pancancer_h5ad.py`, mit `-Size` und `-PancancerSize` wie bisher |

Neuer Ablauf an der Stelle der heutigen Schritte 6 und 6c:

- `-SkipLoad`: nichts abrufen. Der Store enthält nach `wissensnetz init` nur TBox und
  Vokabulare. Meldung: Store ist leer, MP-Lite zeigt das BRCA-Fixture.
- `-FullLoad`: die beiden alten Aufrufe unverändert, davor eine klar sichtbare Warnung, dass
  das der Weg vor ADR-0003 ist und den Store global füllt.
- Standard, also ohne `-SkipLoad` und ohne `-FullLoad`: aus `-DemoCohort` und `-DemoSize`
  eine temporäre Auswahl-JSON schreiben (Vorlage ist `scripts/selection_demo.json`, nur
  `cohorts` und `size` überschreiben) und

  ```powershell
  python scripts\run_selection.py $tmpJson --mediator-url "http://localhost:$MediatorPort"
  ```

  aufrufen. Mit `-DemoGenerate` zusätzlich `--generate --out wissensnetz\data\selection_demo.h5ad`.

Ein Fehlschlag darf den Start **nicht** abbrechen, gleiche Behandlung wie heute bei
Schritt 6: `Fail`-Meldung und weiter, weil MP-Lite auf das Fixture zurückfällt.

### 4) `.h5ad` an MP-Lite übergeben, ohne MP-Lite zu ändern
Lief `-DemoGenerate` erfolgreich, vor dem Start von Bokeh setzen:

```powershell
$env:DATABRIDGE_H5AD = (Resolve-Path "wissensnetz\data\selection_demo.h5ad")
```

Das ist die vorgesehene Schnittstelle: `resolve_h5ad_path()` prüft explizites Argument,
dann `DATABRIDGE_H5AD`, dann `pancancer.h5ad`, dann das BRCA-Fixture (siehe
`wissensnetz/prototype/mp_lite/h5ad_source.py`, `ENV_VAR` in Zeile 41). Kein Eingriff in
`app.py` nötig.

Ohne `-DemoGenerate` die Variable **nicht** setzen. Liegt noch ein altes
`wissensnetz/data/pancancer.h5ad` aus früheren Läufen herum, zieht MP-Lite es weiterhin vor.
Darauf in der Startmeldung hinweisen, nicht die Datei löschen.

### 5) Kopf des Skripts nachziehen
Der `.SYNOPSIS`-Block listet in Schritt 6 und 6c noch das Vorladen. Reihenfolge,
`.EXAMPLE`-Abschnitte und die Kommentare über den geänderten Schritten an das neue Verhalten
anpassen. Mindestens ein Beispiel je neuem Schalter, und `-FullLoad` ausdrücklich als
Altweg kennzeichnen.

### 6) Altwege im Code markieren
Je eine kurze Hinweiszeile in der Hilfe beziehungsweise beim Start von
`scripts/load_gdc.py --pancancer` und `scripts/fetch_pancancer_h5ad.py`: dieser Weg füllt
den Store global und entspricht dem Stand vor ADR-0003; der reguläre Weg ist
`scripts/run_selection.py`. **Keine Funktion entfernen**, beide Skripte bleiben für
Vergleichsmessungen und für den Bericht nutzbar.

### 7) `RUNBOOK.md`
Abschnitt zum Start aktualisieren: Standardstart lädt einen Scope, `-FullLoad` ist der
Altweg, `-SkipLoad` startet mit leerem Store. Kurz halten, die Befehlsreferenz soll nicht
doppelt erklärt werden.

## Verifikation

Mit wirklich leerem Store, sonst ist der Test wertlos:

```powershell
docker compose down -v          # verwirft das TDB2-Volume
.\start_all.ps1 -NoUi
```

Erwartung:

1. Keine Zeile `Geladen: 32/32`, kein `Export: 32 Kohorte(n) in EINEM Aufruf`.
2. `wissensnetz selections` zeigt **genau eine** Auswahl.
3. `wissensnetz query "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a db:Case }"` liefert
   eine Zahl in der Größenordnung von `-DemoSize`, nicht 5387.
4. `.\start_all.ps1 -NoUi -SkipLoad` lässt den Store leer, Schritt 3 ergibt 0.
5. `.\start_all.ps1 -NoUi -FullLoad` verhält sich wie bisher, inklusive der beiden alten
   Aufrufe und der Warnung davor.
6. `.\start_all.ps1 -NoUi -DemoGenerate` erzeugt `wissensnetz\data\selection_demo.h5ad`,
   und im anschließenden Lauf mit Oberfläche zeigt MP-Lite diese Datei (Dateiname erscheint
   in der Statuszeile).
7. Ein Aufruf mit den alten Parametern, `.\start_all.ps1 -Size 50 -PancancerSize 5 -NoUi`,
   läuft ohne Fehler durch.

## Grenze

Keine Änderung an `mediator/` oder `wrappers/`. Keine Funktion aus `load_gdc.py` oder
`fetch_pancancer_h5ad.py` entfernen. `start_all.ps1` muss alle bisherigen Parameter
weiterhin annehmen: `-Size`, `-MediatorPort`, `-UiPort`, `-SkipInstall`, `-SkipLoad`,
`-PancancerSize`, `-RebuildMediator`, `-NoUi`. `-Size` und `-PancancerSize` wirken künftig
nur noch zusammen mit `-FullLoad`; ohne `-FullLoad` werden sie ignoriert, und das Skript
sagt das in einer Zeile, statt still etwas anderes zu tun.
