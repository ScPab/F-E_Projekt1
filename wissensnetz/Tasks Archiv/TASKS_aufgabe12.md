# Aufgabe 12 (nur): Hover zeigt bei überdeckten Punkten nur EIN Sample

## Rahmen
Beachte `wissensnetz/CLAUDE.md`. Nur `wissensnetz/prototype/mp_lite/app.py`
ändern. NICHT `mediator/`/`wrappers/`. Kleiner Commit.

## Problem
Liegen mehrere Punkte an (fast) derselben Stelle — häufig bei aktivem kategorialem
Slider (z. B. `cancer`), wo alle Proben einer Klasse auf dieselbe Kreis-Encoding-
Position fallen, oder in dichten tSNE-Clustern —, zeigt Bokehs `HoverTool` **einen
Tooltip-Block pro getroffenem Punkt**. Die stapeln sich dann (mehrere Sample-Blöcke
untereinander). **Kein Daten-/SPARQL-Problem**: die `obs` hat genau eine Zeile pro
`sample_id`; es sind echte, verschiedene Proben, die sich nur überdecken.

## Ziel
Bei Überdeckung nur das **oberste** Sample im Hover anzeigen — wie im Oviedo-
Original (`demo.py`), das dafür einen HTML-String-Tooltip mit einem `<style>`-Block
nutzt, der alle außer dem ersten Tooltip-Kind ausblendet.

## Umsetzung
Den aktuellen Tupel-Listen-Hover (in `app.py`, ~Zeile 475) durch einen
**HTML-String-Tooltip** ersetzen, der mit dem Ausblende-`<style>` beginnt:

```python
_hover_fields = [
    ("Sample", "@tumor"), ("cancer", "@cancer"), ("type", "@sample_type"),
    ("race", "@race"), ("gender", "@gender"), ("ethnicity", "@ethnicity"),
    ("tumor_stage", "@tumor_stage"), ("morphology", "@morphology"),
    ("site_of_resection_or_biopsy", "@site_biopsy"),
    ("primary_diagnosis", "@primary_diagnosis"),
    ("has_metastasis", "@has_metastasis"), ("vital_status", "@vital_status"),
]
_tt = '<style>.bk-tooltip>div:not(:first-child){display:none;}</style>'
_tt += "".join(f'<b>{lbl}:</b> {ref}<br>' for lbl, ref in _hover_fields)
plot.add_tools(HoverTool(tooltips=_tt))
```
Feldliste/Reihenfolge bleibt exakt wie bisher (Oviedo-Reihenfolge, fehlend -> "--").

## WICHTIG: Bokeh-3-Selektor verifizieren
Der Selektor `.bk-tooltip>div:not(:first-child)` stammt aus altem Bokeh; das Projekt
läuft auf **Bokeh 3.10**, wo sich die Tooltip-DOM-Struktur/-Klassen geändert haben.
Nach dem Einbau **im Browser prüfen** (`bokeh serve --show ...`, über einen dichten
Cluster/bei aktivem `cancer`-Slider hovern):
- Wird nur noch **ein** Sample gezeigt? → fertig.
- Tauchen die Extra-Blöcke weiter auf? → mit den Browser-DevTools den Tooltip-
  Knoten inspizieren und den CSS-Selektor an die tatsächliche Bokeh-3-Struktur
  anpassen (z. B. die richtige Container-Klasse und die Trefferzeilen-Kinder
  treffen). Ziel bleibt: nur das erste getroffene Sample sichtbar.

## Verifikation
- `bokeh serve --show wissensnetz/prototype/mp_lite/app.py`: Über überlappende
  Punkte hovern → nur ein Sample im Tooltip; einzelne Punkte zeigen weiterhin alle
  Oviedo-Felder korrekt.
- Fallback ohne `.h5ad` startet weiter; bestehende Tests grün
  (`pytest wissensnetz/tests -q`).

## Grenze
Nur `prototype/mp_lite/app.py`. Keine Mediator-/Wrapper-Änderung.
