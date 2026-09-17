# Aufgabe 16 (nur): Kein Browser-Fenster beim Start, Oberflächen nur auf Anforderung

## Rahmen
Beachte zuerst `wissensnetz/CLAUDE.md`. Setze **ausschließlich diese Aufgabe** um.
Betroffen sind `start_all.ps1` (Projekt-Wurzel), `scripts/graph_view.py` und `RUNBOOK.md`.
**NICHT** `mediator/`, **NICHT** `wrappers/`, und **keine** Änderung an
`wissensnetz/prototype/mp_lite/`. Kleine Commits, `RUNBOOK.md` als letzter.

`start_all.ps1` und `RUNBOOK.md` nutzen Pablo und Julian ebenfalls, siehe Grenze.

Kontext: `docs/adr/0003-ui-gesteuerte-akquise.md` Abschnitt 6 (Frontend),
`recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md` Abschnitt 6.

## Ziel

Der Start soll **keine** Oberfläche mehr öffnen. Heute passiert beides automatisch, solange
nicht `-NoUi` gesetzt ist:

- Zeile 283 bis 288: `python scripts\graph_view.py --limit 500` erzeugt `graph_view.html`
  und öffnet sie im Browser.
- Zeile 299: `bokeh serve --show ... mp_lite\app.py` startet MP-Lite und öffnet den Browser.

Künftig sind beide **Opt-in**. Grund: die eigentliche Oberfläche für unsere eigenen Anfragen
wird gerade gebaut (`frontend/`, ADR-0003 Abschnitt 6). MP-Lite ist der Oviedo-Prototyp und
die pyvis-Ansicht ein Diagnosewerkzeug, beides soll den Start nicht mehr bestimmen.

Der Standardstart bringt also nur noch die Dienste hoch (Fuseki, Mediator), führt den
Demo-Scope aus und beendet sich mit einem Hinweis, wie man weiterkommt.

## Deliverables

### 1) Zwei neue Schalter in `start_all.ps1`

| Parameter | Default | Wirkung |
|---|---|---|
| `-WithMpLite` | aus | startet MP-Lite über `bokeh serve --show` auf `-UiPort` (heutiges Schritt-7-Verhalten) |
| `-WithGraphView` | aus | erzeugt `graph_view.html` und öffnet sie (heutiges Schritt-6b-Verhalten) |

`-NoUi` bleibt akzeptiert und bedeutet weiterhin "keine Oberfläche". Da das der neue
Standard ist, wird der Schalter wirkungslos, **aber er darf keinen Fehler auslösen** und
keine Warnung produzieren, die wie ein Problem aussieht. Ein Hinweis in einer Zeile genügt,
dass er nicht mehr nötig ist. Wird `-NoUi` zusammen mit `-WithMpLite` oder `-WithGraphView`
angegeben, gewinnt `-NoUi`: ein ausdrückliches Nein schlägt ein ausdrückliches Ja.

### 2) Schritt 6b umstellen
Bedingung von `if (-not $NoUi)` auf `if ($WithGraphView -and -not $NoUi)` ändern. Sonst
unverändert, insbesondere bleibt ein Fehlschlag nicht kritisch.

Prüfen, ob `scripts/graph_view.py` einen Schalter kennt, mit dem die Datei erzeugt, aber
**nicht** geöffnet wird. Gibt es keinen, einen `--no-open` ergänzen (Default: öffnen, damit
das bisherige Verhalten gleich bleibt). Das ist nützlich, sobald die Ansicht aus der neuen
Oberfläche heraus eingebunden wird.

`graph_view.html` in der Projektwurzel **nicht** löschen. Sie wird künftig nur noch auf
Anforderung neu erzeugt und ist damit potenziell veraltet. Das in der Hilfe des Skripts in
einem Satz sagen.

### 3) Schritt 7 umstellen
Neuer Ablauf am Ende des Skripts:

- `-WithMpLite` (und nicht `-NoUi`): heutiges Verhalten. `bokeh serve --show`, Strg+C fährt
  über `Stop-All` alles herunter, Fenster schließt sich.
- Sonst, also im **Standardfall**: keine Oberfläche starten, Dienste laufen lassen, eine
  kurze Übersicht ausgeben und mit `exit 0` beenden. Inhalt der Übersicht:

  - Fuseki: `http://localhost:3030` (Login admin/admin)
  - Mediator: `http://localhost:<MediatorPort>/health` und `/docs`
  - Auswahl ausführen: `python scripts\run_selection.py <selection.json>`
  - Auswahlen ansehen: `wissensnetz selections`
  - Herunterfahren: `.\stop_all.ps1`
  - MP-Lite bei Bedarf: `.\start_all.ps1 -WithMpLite`

Den Block so kommentieren, dass klar ist, wo die neue Oberfläche später einhängt:

```powershell
# --- 7) Oberflaeche ---------------------------------------------------------
# Die eigene Auswahl-Oberflaeche (frontend/, ADR-0003 Abschnitt 6) existiert noch
# nicht und wird hier eingehaengt, sobald sie da ist. MP-Lite ist der
# Oviedo-Prototyp und startet nur noch mit -WithMpLite.
```

### 4) Strg+C-Zusage im Kopf korrigieren
`.SYNOPSIS` Zeile 3 und der `.NOTES`-Abschnitt versprechen, dass Strg+C alles herunterfährt
und das Fenster schließt. Das gilt nur, solange `bokeh serve` im Vordergrund läuft, also ab
jetzt nur mit `-WithMpLite`. Beide Stellen entsprechend umformulieren: im Standardfall
beendet sich das Skript, die Dienste laufen weiter, und `.\stop_all.ps1` fährt sie herunter.

Ebenso die Reihenfolge-Liste im Kopf (Punkte 6b und 7) und die `.EXAMPLE`-Abschnitte. Das
Beispiel `.\start_all.ps1 -SkipLoad -NoUi` durch eines mit den neuen Schaltern ersetzen,
mindestens je ein Beispiel für `-WithMpLite` und `-WithGraphView`.

### 5) `RUNBOOK.md`
Abschnitt zum Start anpassen: Standardstart öffnet keinen Browser, MP-Lite und die
pyvis-Ansicht sind Opt-in, und die Übersicht der URLs plus `stop_all.ps1`. Kurz halten.

## Verifikation

```powershell
.\start_all.ps1
```

Erwartung:

1. Es öffnet sich **kein** Browserfenster, weder MP-Lite noch `graph_view.html`.
2. Das Skript beendet sich mit `exit 0` und gibt die Übersicht aus.
3. Fuseki und Mediator laufen weiter: `docker compose ps` zeigt beide,
   `curl http://localhost:8000/health` antwortet.
4. `.\stop_all.ps1` fährt beide herunter.

Weiter:

5. `.\start_all.ps1 -WithMpLite` verhält sich wie früher: Bokeh startet, Browser öffnet
   sich, Strg+C fährt alles herunter.
6. `.\start_all.ps1 -WithGraphView` erzeugt `graph_view.html` und öffnet sie, startet aber
   **kein** MP-Lite.
7. `.\start_all.ps1 -WithMpLite -NoUi` startet nichts, ohne Fehler.
8. Ein Aufruf mit den alten Parametern, `.\start_all.ps1 -SkipLoad -NoUi`, läuft
   unverändert durch.

## Grenze

Keine Änderung an `mediator/`, `wrappers/` oder `wissensnetz/prototype/mp_lite/`. MP-Lite
bleibt voll funktionsfähig und wird nur nicht mehr automatisch gestartet.
`start_all.ps1` muss alle bisherigen Parameter weiterhin annehmen: `-Size`,
`-MediatorPort`, `-UiPort`, `-SkipInstall`, `-SkipLoad`, `-PancancerSize`,
`-RebuildMediator`, `-NoUi`, `-DemoCohort`, `-DemoSize`, `-DemoGenerate`, `-FullLoad`.

## Hinweis, keine Aufgabe

`graph_view.html` liegt versioniert in der Projektwurzel und wird ab jetzt nur noch auf
Anforderung neu erzeugt, veraltet also. Ob die Datei in `.gitignore` gehört, ist eine
Team-Entscheidung und nicht Teil dieser Aufgabe.
