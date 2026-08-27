# Hand-off: Daten für das Multi-Variablen-Morphing in MP-lite

Aufgabe 6 hat die Morph-Mechanik des Oviedo-Originals in MP-lite portiert:
ein Slider **pro Variable**, finale Position = `Σ aᵢ · E[i]` mit
`a = softmax(10 · slider_werte)`, Gewichtung clientseitig (CustomJS). Der
Prototyp-Code ist damit fertig und **datengetrieben**: Sobald eine Variable
mindestens zwei verschiedene Nicht-Null-Werte im Graphen hat (`is_encodable`),
baut die App automatisch ihr Encoding und aktiviert den Slider. Fehlt die
Datenbasis, erscheint die Variable als **deaktivierter** Slider — die Lücke ist
im UI ehrlich sichtbar (Div „Ohne Daten deaktiviert: …").

Aktuell (4 echte BRCA-Proben + 20 synthetische) sind i. d. R. nur wenige
klinische Variablen encodierbar; die Basis-Views **genes**/**miRNA** morphen
immer. Damit die restlichen Slider echt morphen, müssen zuerst Daten durch die
Kette — getrennt nach zwei Quellen:

## 1) Klinische Slider — hängen an Aufgabe 5

`race`, `ethnicity`, `tumor_stage`, `morphology`, `has_metastasis`,
`vital_status`, `type` (sample_type):

- Diese Slider werden **automatisch aktiv**, sobald die zugehörigen `db:`-Felder
  im Graphen echte Werte tragen. Es ist hier **kein** weiterer MP-lite-Code
  nötig — nur Daten.
- Was dafür in Mediator/Wrapper passieren muss, steht bereits in
  **`HANDOFF_oviedo_felder.md`** (Aufgabe 5): GDC-Wrapper muss die Felder
  anfragen, der Mediator sie als Tripel auf die neuen `db:`-Properties schreiben,
  danach die Fixture `cases_brca_sample.ttl` neu ziehen.
- `type`/`sample_type` braucht zusätzlich die dort beschriebene Sample-/
  Biospecimen-Klasse (offener Modell-Punkt) — bis dahin bleibt der Slider
  deaktiviert.
- Anmerkung: Auch ein bereits gemapptes Feld bleibt deaktiviert, solange die
  Kohorte nur **einen** distinct Wert hat (z. B. `cancer = BRCA` bei reiner
  BRCA-Fixture). Zum Morphen braucht es Variation — siehe Punkt 3.

## 2) Expressions-Slider — komplett fehlende Datenquelle

`genes`-tSNE, `miRNA`-tSNE sowie Einzelmarker wie `miRNA-210-3p`, `CA9`, `SAA1`
(im Original lineare Encodings). Diese existieren im Wissensnetz **noch gar
nicht**. Benötigt werden:

1. **Expressionsvektoren pro Probe** (DNA/miRNA) — der `anndata`/`.h5ad`-Teil der
   DataBridge-Architektur, der aktuell nicht ins Wissensnetz integriert ist.
2. **Vorberechnete 2D-tSNE-Layouts** für genes und miRNA (im Original in
   `pancancer_morphing.hdf`, Spalten `genes_x/y`, `mirna_x/y`). Diese liefern die
   „genes"/„miRNA"-Encodings `E[0]`/`E[1]`; MP-lite nutzt derzeit synthetische
   Platzhalter-Layouts (`L0`/`L1`) an ihrer Stelle.
3. **Einzel-Marker-Spalten** (z. B. Ensembl-Gen- / MIMAT-miRNA-IDs) als Basis
   für lineare Encodings einzelner Marker.

### Offene Architekturfrage (mit Team klären — nicht in dieser Aufgabe)

Kommen Expressionswerte über den **Graphen** (als Tripel/Literals an Case/Sample)
oder über einen **Seitenkanal** (h5ad direkt in den Prototyp geladen, am RDF-
Store vorbei)? Das betrifft Mediator/Wrapper **und** Wissensnetz gemeinsam und
ist Voraussetzung, bevor die Expressions-Slider gebaut werden können.

## 3) Zusätzlich: echte Kohorte statt Mini-Fixture

Aussagekräftiges Morphing braucht eine **echte, variantenreiche Kohorte** statt
4 echter + 20 synthetischer Proben. Erst mit mehreren Cancer-Typen, Stages,
Geschlechtern usw. entstehen sinnvolle Cluster, zwischen denen das Morphing
Struktur zeigt. Die synthetischen Proben tragen bewusst keine Klinik-Werte
(`"--"`) und ballen sich daher im Ursprung der klinischen Encodings.
