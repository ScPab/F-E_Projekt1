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
- **Morphing:** je Variable ein Slider; die Endposition ist die softmax-gewichtete
  Summe der Encodings (wie im Oviedo-Original). Basis-Views „genes"/„miRNA",
  Einzelmarker-Slider (z. B. CA9/SAA1) und Kreis-Encodings der klinischen Variablen.

## Datenquellen-Priorität (Aufgabe 9)
Beim Start wählt die App in dieser Reihenfolge:
1. **Expressions-`.h5ad`** (Mediator-Artefakt, Default
   `mediator/sample_data/tcga_brca_sample.h5ad`, per ENV `DATABRIDGE_H5AD`
   überschreibbar) → Punkte/Hover aus `obs`, echte tSNE (`obsm["X_tsne_genes"]`)
   als Basis-View „genes", Einzelmarker-Slider aus `X` (ENV `DATABRIDGE_MARKERS`,
   Default `CA9,SAA1`).
2. sonst der **Graph** (`all_cases()`, Aufgabe 7) → Expressions-Slider deaktiviert.
3. sonst **Synthetik-Fallback**.

Die Statuszeile („Daten:") zeigt den gewählten Pfad. Fehlt `anndata` oder die
Datei, fällt die App ohne Crash auf 2./3. zurück. `.h5ad` wird **nur gelesen**.

## Voraussetzungen & Start
```bash
# 1) Triple-Store starten
docker compose up -d graph-db

# 2) Pakete (Prototyp-Extras: bokeh, numpy, anndata)
pip install -e "./wissensnetz[prototype]"
# oder einzeln:  pip install bokeh numpy anndata

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
- Ohne `.h5ad` (Graph-/Synthetik-Pfad) sind die Basis-Views „genes"/„miRNA"
  synthetische Zufalls-Layouts, kein echtes t-SNE. Mit dem `.h5ad` morpht „genes"
  entlang der vorberechneten tSNE und die Marker-Slider linear entlang der echten
  Expressionswerte. Das Referenz-`.h5ad` ist klein (BRCA); der Pancancer-Pfad läuft
  bis auf Weiteres über den Graphen (Aufgabe 7).
- `bokeh serve` ist erforderlich (Server-seitige Python-Callbacks); die
  statische `demo.html` von Oviedo kann keine Python-Hooks ausführen.
