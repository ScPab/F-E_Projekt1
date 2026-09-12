# Kandidatenliste für `ncit_primary_diagnosis.json`

Arbeitsdokument zur Befüllung der Alignment-Tabelle. Erhoben am 2026-09-12 über die
GDC-Facet-API, Programm TCGA: **11.428 Fälle, 261 distinkte `primary_diagnosis`-Werte**,
davon 995 `not reported` und 125 `unknown`.

Die Projektverteilung je Wert wurde über eine Facet-Abfrage pro Projekt für **alle 33
TCGA-Projekte** ermittelt (`filters` auf `cases.project.project_id`, `facets=diagnoses.primary_diagnosis`).
Werte unter 2 Fällen je Projekt sind in den Verteilungen nicht aufgeführt, deshalb
addieren sich die Spalten nicht immer exakt auf die Gesamtzahl. Ein Fall kann mehrere
Diagnosen tragen.

## Die zwei Regeln

**Regel A, Bedeutungsgleichheit.** Der NCIt-Code muss genau das bedeuten, was der
ICD-O-3-Begriff sagt. Nicht spezifischer. "NOS" heißt "not otherwise specified" und darf
nicht zu einem Subtyp aufgelöst werden.

**Regel B, kein Organ hinzuerfinden.** Ein organspezifischer NCIt-Code ist nur erlaubt,
wenn der Wert ausschließlich in der Kohorte dieses Organs vorkommt. Sonst muss die
organunabhängige Morphologie-Klasse gewählt werden, oder der Wert bleibt unbelegt.

Regel B ist der Grund für die Spalte "Ebene" unten. `spezifisch` heißt: organspezifischer
Code erlaubt. `generisch` heißt: nur die organunabhängige Morphologie-Klasse, ein
Organ-Code wäre für einen Teil der Fälle falsch.

## Bugfix zuerst: die drei bestehenden Einträge

| Schlüssel in der Datei | Eingetragen | Problem |
|---|---|---|
| `Infiltrating duct carcinoma, NOS` | `NCIT_C4194` = Invasive Breast Carcinoma of No Special Type | Wert kommt in 7 Projekten vor, davon 151 Fälle in TCGA-PAAD (Pankreas). Für diese ist ein Brust-Code falsch. |
| `Lobular carcinoma, NOS` | `NCIT_C7950` | Wert kommt nur in TCGA-BRCA vor (201 von 201). Brustspezifisch ist hier **zulässig**, Code trotzdem gegenprüfen. |
| `Infiltrating duct and lobular carcinoma` | `NCIT_C7688` | Nur TCGA-BRCA (29 Fälle). Zulässig, Code gegenprüfen. |

Also: ein Eintrag muss korrigiert werden, zwei sind vom Prinzip her in Ordnung.

## Kandidaten, nach Fallzahl

Die 25 Werte unten deckten zusammen rund 9.800 Diagnose-Nennungen ab, also den
überwiegenden Teil der informationstragenden Werte. Die Spalte `NCIt` ist absichtlich
leer: die Codes gehören einzeln nachgeschlagen und gegengeprüft.

| # | Wert (Schreibweise aus der API, kleingeschrieben) | Fälle | Projektverteilung | Ebene | NCIt |
|---|---|---|---|---|---|
| 1 | adenocarcinoma, nos | 1610 | 26 Projekte: COAD 390, LUAD 318, PRAD 291, STAD 165, READ 141, BLCA 92, ESCA 87, PAAD 22, KIRP 16, KIRC 15, LIHC 12, CESC 10, LUSC 9, SKCM 8, THCA 7, UCEC 7, BRCA 4, SARC 4, … | generisch | |
| 2 | squamous cell carcinoma, nos | 1236 | 13 Projekte: LUSC 470, HNSC 451, CESC 172, ESCA 90, SKCM 14, LIHC 7, LUAD 7, KIRC 5, BLCA 5, PRAD 4, … | generisch | |
| 3 | infiltrating duct carcinoma, nos | 964 | 7 Projekte: BRCA 784, **PAAD 151**, PRAD 9, LUAD 5, UCEC 5, KIRP 2, UCS 2 | generisch | |
| 4 | serous cystadenocarcinoma, nos | 712 | 2 Projekte: OV 581, UCEC 127 | generisch | |
| 5 | papillary adenocarcinoma, nos | 694 | 8 Projekte: THCA 354, KIRP 291, LUAD 24, STAD 8, HNSC 6, PCPG 3, COAD 2, BLCA 2 | generisch | |
| 6 | glioblastoma | 599 | nur GBM 599 | spezifisch | |
| 7 | clear cell adenocarcinoma, nos | 529 | KIRC 523, LUAD 2, KIRP 2 | generisch | |
| 8 | malignant melanoma, nos | 485 | SKCM 469, PRAD 3, LUAD 2, COAD 2 | spezifisch (Entität, organunabhängig) | |
| 9 | endometrioid adenocarcinoma, nos | 415 | UCEC 410, CESC 3, LUAD 2 | spezifisch (Entität, organunabhängig) | |
| 10 | transitional cell carcinoma | 361 | BLCA 348, LUSC 5, KIRC 3, KIRP 2 | spezifisch (Entität) | |
| 11 | hepatocellular carcinoma, nos | 361 | nur LIHC 360 | spezifisch | |
| 12 | acinar cell carcinoma | 219 | PRAD 195, LUAD 24 | **nicht mappen** | |
| 13 | lobular carcinoma, nos | 201 | nur BRCA 201 | spezifisch | bereits: C7950 |
| 14 | seminoma, nos | 154 | nur TGCT 153 | spezifisch | |
| 15 | mucinous adenocarcinoma | 141 | 7 Projekte: COAD 63, STAD 22, BRCA 16, READ 15, LUAD 14, PAAD 5, CESC 2 | generisch | |
| 16 | mixed glioma | 131 | nur LGG 131 | spezifisch | |
| 17 | astrocytoma, anaplastic | 130 | nur LGG 130 | spezifisch | |
| 18 | adenocarcinoma with mixed subtypes | 119 | LUAD 107, PRAD 3, STAD 2, READ 2 | generisch | |
| 19 | pheochromocytoma, nos | 118 | nur PCPG 116 | spezifisch | |
| 20 | oligodendroglioma, nos | 115 | nur LGG 115 | spezifisch | |
| 21 | renal cell carcinoma, chromophobe type | 115 | nur KICH 113 | spezifisch | |
| 22 | papillary carcinoma, follicular variant | 111 | THCA 106, HNSC 3 | spezifisch, HNSC-Fälle prüfen | |
| 23 | squamous cell carcinoma, keratinizing, nos | 105 | HNSC 57, CESC 30, LUSC 13, ESCA 5 | generisch | |
| 24 | carcinoma, nos | 97 | BLCA 87, PAAD 2, … | generisch | |
| 25 | adenocarcinoma, intestinal type | 88 | nur STAD 88 | spezifisch | |

### Billige Zusatztreffer

Diese Werte stehen nicht in den Top 25, kommen aber in genau einer Kohorte vor und sind
damit ohne weitere Prüfung organspezifisch mappbar. Guter Zuwachs für wenig Aufwand:

| Wert | Fälle | Kohorte |
|---|---|---|
| leiomyosarcoma, nos | 101 | SARC |
| adrenal cortical carcinoma | 92 | ACC |
| papillary transitional cell carcinoma | 80 | BLCA |
| oligodendroglioma, anaplastic | 78 | LGG |
| carcinoma, diffuse type | 68 | STAD |
| astrocytoma, nos | 66 | LGG |
| papillary transitional cell carcinoma, non-invasive | 66 | BLCA |
| epithelioid mesothelioma, malignant | 58 | MESO |
| dedifferentiated liposarcoma | 58 | SARC |
| cholangiocarcinoma | 49 | CHOL |
| mixed germ cell tumor | 48 | TGCT |
| mullerian mixed tumor | 45 | UCS |
| diffuse large b-cell lymphoma, nos | 41 | DLBC |
| pheochromocytoma, malignant | 40 | PCPG |
| undifferentiated sarcoma | 33 | SARC |

### Werte, die bewusst unbelegt bleiben sollten

| Wert | Grund |
|---|---|
| acinar cell carcinoma | PRAD 195 und LUAD 24 sind zwei verschiedene Entitäten (azinäres Prostatakarzinom vs. azinäres Lungenkarzinom). Ein Code kann nicht beides sein. |
| not reported (995), unknown (125) | keine Diagnose |
| basal cell carcinoma, nos | erscheint als Nebendiagnose in vielen Kohorten, jeweils 2 bis 10 Fälle, inhaltlich Hautbefunde neben der Hauptdiagnose |

## Der Nachschlage-Schritt

Pro Wert eine Abfrage, ohne `exact`, weil die GDC-Werte in NCIt meist nur Synonyme sind:

```
https://www.ebi.ac.uk/ols4/api/search?q="<Wert>"&ontology=ncit&rows=5
```

Jeder Treffer liefert `label`, `obo_id`, `iri` und `synonym`. Auswahlkriterium: das
`synonym`-Feld muss den GDC-Wert enthalten, und das `label` darf nach Regel A und B nicht
mehr behaupten als der Wert. Danach im NCI Thesaurus gegenprüfen, weil die Synonym-Suche
auch Nachbarkonzepte einsammelt.

Kontrollierter Fall aus der Praxis: `"Infiltrating duct carcinoma, NOS"` liefert unter
anderem C4194 mit dem Label "Invasive Breast Carcinoma of No Special Type". Der GDC-Wert
steht dort nur als Synonym, und das Label trägt ein Organ, das der Wert nicht hergibt.
Genau dieser Treffer ist nach Regel B abzulehnen.

## Zielformat

Flach bleiben, weil `load_alignment_table()` genau `{Wert: IRI}` erwartet. Alle Schlüssel
mit führendem Unterstrich werden vom Loader verworfen und stehen damit für Metadaten frei:

```json
{
  "_readme": "…",
  "_format": "…",

  "Glioblastoma": "http://purl.obolibrary.org/obo/NCIT_Cxxxx",
  "Lobular carcinoma, NOS": "http://purl.obolibrary.org/obo/NCIT_C7950",

  "_provenance": {
    "Glioblastoma": {
      "ncit_label": "<Label aus NCIt>",
      "ebene": "spezifisch, nur TCGA-GBM",
      "faelle_tcga": 599,
      "quelle": "OLS4 ncit, gegengeprueft im NCI Thesaurus",
      "datum": "2026-09-12"
    }
  },

  "_nicht_gemappt": {
    "Acinar cell carcinoma": "PRAD 195 und LUAD 24 sind verschiedene Entitaeten",
    "Adenocarcinoma, NOS": "26 Kohorten, nur generische Klasse zulaessig"
  }
}
```

**Achtung Schreibweise:** Die Facet-API liefert alles kleingeschrieben. Der Schlüssel in
der Tabelle muss die Originalschreibweise tragen, wie sie in
`diagnoses[].primary_diagnosis` eines echten Records steht, also zum Beispiel
`"Infiltrating duct carcinoma, NOS"` und nicht `"infiltrating duct carcinoma, nos"`.
Prüfen mit einer Einzelabfrage:

```
https://api.gdc.cancer.gov/cases?size=1&fields=diagnoses.primary_diagnosis&filters=
  {"op":"in","content":{"field":"cases.project.project_id","value":["TCGA-GBM"]}}
```

## Was danach noch fehlt

Das Mapping allein erzeugt IRIs ohne Kanten. Für `rdfs:subClassOf*` muss NCIt-Hierarchie
im Store liegen, sonst bleibt die Navigation ab Ebene 2 wirkungslos. Empfehlung: Slim aus
`https://purl.obolibrary.org/obo/ncit.owl` mit nur den gemappten Klassen plus deren
Vorfahren, geladen in einen eigenen Named Graph:

```bash
wissensnetz load wissensnetz/ontology/ncit-slim.ttl --graph http://databridge.hka/graph/ncit
```

Das funktioniert ohne Code-Änderung, weil `_hierarchy()` in `src/wissensnetz/enrichment.py`
bereits Default-Graph und `GRAPH ?g` per UNION abfragt.

## Offener Punkt für das Team

Die Zeilen mit Ebene `generisch` verlieren Tiefe: `Adenocarcinoma` liegt in NCIt weit oben,
eine Navigation darunter bringt wenig. Wer die Organ-Information nutzen will, braucht einen
zusammengesetzten Schlüssel aus `primary_diagnosis` plus `project_id` oder
`site_of_resection_or_biopsy`. Das ist eine Änderung an `load_alignment_table()` und
`cases_to_graph()` im Mediator, also ein Hand-off an Pablo, keine Sache der Tabelle.
