# Prototyp: MP-lite × Wissensnetz

Ein **funktionierender Prototyp** des geschlossenen Loops zwischen einer
Morphing-Projections-artigen Visualisierung und dem Wissensnetz — bewusst klein
gehalten und self-contained.

Warum MP-lite statt der Original-`demo.py` von Oviedo: deren Code ist von 2020
(alte Bokeh-API: `widgetbox`, `legend=…`) und braucht große, vorverarbeitete
TCGA-Daten aus dem Notebook. Für einen ersten lauffähigen Prototyp bildet
`mp_lite/app.py` das MP-Prinzip im Kleinen nach (Scatter + Box-/Lasso-Select +
konvexer Morph-Slider „Gene ↔ miRNA") und koppelt **in-process** an das Paket
`wissensnetz` — kein REST/JS nötig.

> **Späterer Zielweg:** dieselben zwei Hooks (Kontext ② beim Auswählen,
> `write_feedback` ③ beim Selektieren) gegen die echte MP-**Web-Version**. Die
> Prototyp-App ist getrennt gehalten und fasst weder `mediator/`/`wrappers/`
> noch Oviedos eingebettete `demo.py` an — nur das eigene `wissensnetz`-Paket.

## Was es demonstriert
- **② Anreicherung:** Punkt(e) per Tap/Box-Select auswählen → das Seitenpanel
  zeigt den Kontext aus dem Wissensnetz (`enrichment.case_context`: Projekt,
  Geschlecht, Diagnose, ggf. NCIt-Alignment).
- **③ Rückkanal:** Selektion + Hypothese (von → nach) eingeben → Button speichert
  sie via `feedback.write_feedback` in einen Named Graph pro Nutzer; die Liste
  darunter zeigt alle gespeicherten Erkenntnisse (`list_findings`).
- **Morphing:** der Slider überblendet die Punkte konvex zwischen zwei Layouts.

## Voraussetzungen & Start
```bash
# 1) Triple-Store starten
docker compose up -d graph-db

# 2) Pakete
pip install -e ./wissensnetz
pip install bokeh numpy

# 3) Dataset + TBox + Beispiel-ABox laden (idempotent)
wissensnetz init
wissensnetz load wissensnetz/data/sample/cases_brca_sample.ttl

# 4) Prototyp starten (Bokeh-Server; öffnet den Browser)
bokeh serve --show wissensnetz/prototype/mp_lite/app.py
```
Die App lädt beim Start selbst `init` + die Beispiel-ABox; Schritt 3 ist also
optional, schadet aber nicht.

## Bedienung / was man sieht
- **Grüne Punkte** = die vier Fixture-Proben (`TCGA-A1-A0S*`), die **Kontext im
  Graphen haben**. **Graue Punkte** (`SYN-*`) sind synthetisch und zeigen bewusst
  den „kein Kontext"-Fall — so sieht man den Unterschied.
- Ein paar grüne Punkte selektieren → Kontext erscheint. Hypothese eintragen
  (vorbelegt mit dem PAAD→PanNET-Beispiel) → „Selektion als Erkenntnis speichern".
- „Erkenntnisse aktualisieren" listet das Zurückgeschriebene; per SPARQL bzw.
  `wissensnetz findings` ist es ebenfalls sichtbar.

## Grenzen (bewusst, für den Prototyp)
- Die Anreicherung ② liefert nur für die vier überlappenden Barcodes etwas —
  echte Fülle kommt mit der NCIt-Alignment-Tabelle und der TBox-Erweiterung
  (Genexpression/miRNA/Methylierung).
- Der Morph ist ein einfacher konvexer Blend zweier Zufalls-Layouts, kein echtes
  t-SNE — es geht um den Loop, nicht um die Projektion.
- `bokeh serve` ist erforderlich (Server-seitige Python-Callbacks); die
  statische `demo.html` von Oviedo kann keine Python-Hooks ausführen.
