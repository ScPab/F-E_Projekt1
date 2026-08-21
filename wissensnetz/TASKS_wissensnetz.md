# Aufgaben: Wissensnetz — Triple-Store, SPARQL & Rückkanal

> Kontext und harte Regeln stehen in `wissensnetz/CLAUDE.md` (bitte zuerst
> beachten). Diese Datei ist die konkrete Arbeitsanweisung. Vor Beginn die unter
> „Wo was liegt“ in `CLAUDE.md` genannten Dateien lesen, um Turtle-Format und
> TBox zu verstehen.

## Zielstruktur (Vorschlag, anpassbar)
```
wissensnetz/
  pyproject.toml            # installierbares Paket "wissensnetz"
  README.md                 # Setup + End-to-End-Ablauf
  requirements.txt
  src/wissensnetz/
    config.py               # Fuseki-URL, Dataset, Namespaces aus ENV
    graphstore.py           # (2) Fuseki-Client: load_turtle / query / update
    enrichment.py           # (3) vordefinierte SPARQL-Abfragen
    feedback.py             # (4) Rückkanal: Selektion→RDF, write/readback
    cli.py                  # CLI-Einstieg für alle Schritte
  init/                     # (1) Fuseki-Dataset-Konfiguration
  data/sample/              # simuliertes MP-Selektions-Event (JSON)
  tests/                    # pytest je Aufgabe
```

## Aufgaben (in Reihenfolge, jede mit Abnahmekriterium)

### 1 — Fuseki-Dataset & TBox-Initialisierung
Dataset `databridge` beim Start anlegen (Assembler-`.ttl` unter `graph-db/init/`
ODER passende `FUSEKI_DATASET_*`-ENV — wähle den Weg, der zum `stain/jena-fuseki`-
Image passt, und dokumentiere ihn) und die TBox
`wissensnetz/ontology/databridge-core.ttl` laden.
**Abnahme:** nach `docker compose up graph-db` existiert das Dataset und eine
SPARQL-Abfrage liefert die TBox-Klassen (`db:Case`, `db:Diagnosis`, …).

### 2 — Graphstore-Client
`graphstore.py`: `load_turtle(text_or_path, graph=None)`, `query(sparql) -> rows`,
`update(sparql)`. Turtle-Ausgabe aus `mediator/scripts/example_gdc_to_rdf.py` bzw.
`POST /transform` in Fuseki laden.
**Abnahme:** Beispieldaten geladen, `query` liefert die erwarteten Cases/Diagnosen
zurück. Pytest deckt load+query gegen ein laufendes Fuseki ab (Skip, wenn nicht
erreichbar).

### 3 — SPARQL-Anreicherung (Lesen)
`enrichment.py`: mindestens (a) Klassen-/Krankheitshierarchie via
`rdfs:subClassOf*`, (b) Fall-/Diagnose-Kontext zu einer gegebenen Case-/Diagnosis-
IRI (verknüpfte Konzepte + Alignment-Ziele). Als Funktionen + CLI
(`wissensnetz query ...`).
**Abnahme:** korrekte Ergebnismengen gegen die geladenen Beispieldaten; Tests vorhanden.

### 4 — Rückkanal (Schreiben)
`feedback.py`: simuliertes MP-Selektions-Event
(`data/sample/selection_event.json`; Felder: Nutzer, Probenmenge, Hypothese/
Reclassification from→to, Sicht, Morph-t, Konfidenz, Zeit) → RDF als
`oa:Annotation` + PROV-O + RDF-star, geschrieben per SPARQL Update in einen
**Named Graph pro Nutzer**; plus Rück-Abfrage. Modellierung nach
`recherche/Rueckkanal-Konzept_MP-zu-RDF`.
**Abnahme:** Event wird geschrieben und ist per SPARQL wieder auslesbar; Test vorhanden.

### Querschnitt
`wissensnetz/README.md` mit End-to-End-Ablauf (`docker compose up graph-db` → init
→ load → query → feedback), `requirements.txt`, CLI-Einstieg, `pytest` grün.
`graph-db/README.md` um den gewählten Init-Weg ergänzen.

## Definition of Done
`docker compose up graph-db` → Init legt Dataset+TBox an → Beispiel-Turtle geladen
→ eine SPARQL-Abfrage liefert erwartete Zeilen → ein Rückkanal-Event wird
geschrieben und zurückgelesen → alle Tests grün → README dokumentiert die Schritte.
Mediator/Wrapper unverändert.

## Empfohlener Einstieg
Zuerst **Aufgabe 1 + 2** umsetzen (Fuseki nutzbar machen + Store-Client), dann
Rückfrage/Review, danach 3 und 4.
