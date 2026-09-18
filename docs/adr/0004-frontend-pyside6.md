# ADR-0004: PySide6 als Frontend-Technologie

**Status:** Angenommen
**Datum:** 2026-09-17

## Kontext

ADR-0003 legt fest, dass die Auswahl in der Oberfläche der Auftrag ist und die Kette von
dort aus angestoßen wird. Die Oberfläche selbst war darin ausdrücklich offen (Entscheidung
7.1 im Umsetzungsplan): `frontend/` enthält bis heute nur `.gitkeep` und ein README, es gibt
keinen Compose-Service und keine Technologieentscheidung.

Randbedingungen:

- Entwicklung und Betrieb finden auf Windows statt, in der Conda-Umgebung `F+E`.
- Die Oberfläche soll ein **eigenes Fenster** sein, kein Browser-Tab.
- Der gesamte übrige Stack ist Python. Das Wissensnetz liegt als installierbares Paket vor
  und bietet Lesefunktionen (`cases_for_selection`, `list_selections`, `case_context`), die
  die Anzeige direkt braucht.
- MP-Lite (Bokeh) bleibt als Oviedo-Prototyp bestehen, startet aber seit Aufgabe 16 nicht
  mehr automatisch.
- Das Zielwerkzeug der Uni Oviedo ist langfristig eine Web-Anwendung.

## Entscheidung

Die Auswahl-Oberfläche wird eine **PySide6-Desktop-Anwendung** unter `frontend/`.

1. **Eigener Prozess auf dem Host**, in der Conda-Umgebung `F+E`, nicht im
   Mediator-Container. Start über `python frontend\app.py`, in `start_all.ps1` über den
   Schalter `-WithUi`.
2. **Layout nach der Handskizze:** links die Anzeigefläche, rechts das Auswahlpanel mit vier
   Zeilen (Kohorte, Modalität, Attribute, Datenquelle), unten die Schaltflächen `Vorschau`
   und `Generieren`.
3. **Zwei Wege nach außen, klar getrennt:**
   - Aufträge gehen per HTTP an den Mediator, `POST /selection/preview` und
     `POST /selection/generate`. Die Oberfläche spricht nie direkt mit einem Wrapper
     (ADR-0001).
   - Die Anzeige liest das Ergebnis über das Paket `wissensnetz` **direkt im Prozess**
     (`cases_for_selection`), nicht über HTTP. Das erspart einen Anzeige-Endpunkt im
     Mediator für jede Ansicht.
4. **Oberflächen-Entwurf über Qt Designer** als `.ui`-Dateien, geladen zur Laufzeit. Der
   Entwurf bleibt damit vom Code getrennt und im Diff lesbar.
5. **Alle Netzaufrufe außerhalb des GUI-Threads.** `/selection/generate` lädt Rohdaten
   herunter und dauert Minuten; ein Aufruf im GUI-Thread friert das Fenster ein.
6. **MP-Lite bleibt unangetastet.** Es ist der Vergleichsmaßstab gegenüber Oviedo, nicht die
   künftige Oberfläche.

## Betrachtete Alternativen

- **Bokeh** (wie MP-Lite). Verworfen für diesen Zweck: es ist ein Server plus Browser-Tab,
  kein eigenes Fenster. Sonst wäre es die billigste Wahl, weil bereits im Stack.
- **C# mit WPF in Visual Studio.** Verworfen: eine zweite Sprache im Projekt, und die
  Oberfläche könnte das Paket `wissensnetz` nicht direkt nutzen. Jede Ansicht bräuchte dann
  einen zusätzlichen Endpunkt im Mediator, also Arbeit bei Pablo für etwas, das in Python
  ein Funktionsaufruf ist. Der grafische Designer allein wiegt das nicht auf, Qt Designer
  leistet dasselbe.
- **Streamlit.** Verworfen: kein eigenes Fenster, und das Skript läuft bei jeder Interaktion
  komplett neu, was mit teuren Aufrufen und geschachtelten Ebenen schlecht zusammenpasst.
- **Web-Frontend mit React oder Vue.** Zurückgestellt, nicht verworfen. Es ist der Weg zur
  Web-Version, die Oviedo langfristig braucht. Kosten heute: Node-Werkzeugkette, eine neue
  Sprache im Team, CORS im Mediator. Die REST-Schnittstelle aus ADR-0003 bleibt dafür
  unverändert nutzbar, ein Wechsel kostet also nur die Oberfläche selbst.

## Konsequenzen

**Positiv**

- Eigenes Fenster ohne Browser, wie gewünscht.
- Eine Sprache im ganzen Projekt. Kein Build-Schritt, kein Node, keine CORS-Konfiguration.
- Die Anzeige nutzt die Wissensnetz-Lesefunktionen direkt, es entsteht kein Bedarf an
  zusätzlichen Endpunkten im Mediator.
- Die Kohortenliste kann aus `wissensnetz.cohorts` kommen, bleibt also eine einzige
  Wahrheit für Ladeskript, MP-Lite und Oberfläche.

**Zu tragen**

- Neue Abhängigkeit `pyside6` in `requirements.txt`, ein Paket, kein Unterbau.
- Qt-Denkweise (Signals und Slots, Layouts, Modelle) ist neu für das Team.
- **Threading ist Pflicht, nicht Feinschliff.** Ohne Worker-Thread friert das Fenster beim
  Generieren ein und wirkt abgestürzt.
- Die Darstellung der Karte muss später eingebettet werden, über matplotlib oder pyqtgraph.
  MP-Lites Bokeh-Plot lässt sich nicht übernehmen.
- Ein Windows-Programm zum Weitergeben (etwa über PyInstaller) ist möglich, aber
  ausdrücklich nicht Teil dieser Entscheidung.
- Die Oberfläche hängt zur Laufzeit an zwei Diensten: Mediator für Aufträge, Fuseki für die
  Anzeige. Beide Ausfälle müssen sichtbar behandelt werden.

**Revidieren, falls** die Uni Oviedo eine Web-Version als Abgabeform braucht. Dann bleibt
die REST-Schnittstelle, und nur die Oberfläche wird ersetzt.

## Quellen

- `docs/adr/0003-ui-gesteuerte-akquise.md`
- `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.md`, Abschnitte 6 und 7.1
- Handskizze vom 2026-09-17 (Fensterlayout, Auswahlpanel)
- ADR-0001 (Wrapper als Python-Package)
