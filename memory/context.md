# Projektkontext DataBridge

Stand: 2026-09-26

## Ziel

Konzeption und prototypische Umsetzung einer Systemarchitektur zur
automatisierten Datenintegration für Visualisierungswerkzeuge im Bereich
Onkologie/Genetik (Kooperation Hochschule Karlsruhe / Universität Oviedo,
26ss_CB_DataBridge). Testfall: TCGA-Daten über die GDC Developer API.
Fokus: Flexibilität gegenüber sich entwickelnden Datenstrukturen/Ontologien.

## Architektur (Grundgerüst, Stand siehe /docs/adr)

- **Muster:** Mediator-Wrapper. Zentraler Mediator-Service (Python/FastAPI,
  `/mediator`) nimmt Anfragen entgegen; Wrapper-Module je Datenquelle
  (`/wrappers`, erste Quelle: `gdc`).
- **Wrapper-Platzierung:** als Python-Package im Mediator-Container, nicht
  als eigener Docker-Service — siehe [ADR-0001](../docs/adr/0001-wrapper-als-python-package.md).
- **Zielformat der Ausgabe:** anndata (`.h5ad`) für Messmatrizen, RDF/OWL
  (Turtle) für die semantische Schicht (Wissensnetz).
- **Graph-Speicherung:** entschieden für RDF-Triple-Store mit OWL (Apache
  Jena Fuseki/TDB2), Kanten-Metadaten via RDF-star; Property-Graph und
  hybrides Modell verworfen — siehe
  [ADR-0002](../docs/adr/0002-graph-db-wahl-offen.md) (Status: Angenommen,
  2026-08-15).
- **Wissensnetz/Semantic ETL:** Teilbereich von Marcel, siehe
  `wissensnetz/Wissensnetz_Konzept-Entwurf` (übergeordnetes Konzept) und
  `wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL` (konkretes GDC→RDF-Mapping).
  Ontologie unter `wissensnetz/ontology/`, Mapping-Code unter
  `mediator/app/semantic/`.
- **Auftragsrichtung:** die Auswahl in der Oberfläche IST der Auftrag; sie
  stößt die Kette an, der Mediator übersetzt das Ergebnis und verzweigt es
  nach Wissensnetz und anndata. Siehe
  [ADR-0003](../docs/adr/0003-ui-gesteuerte-akquise.md). Der Store startet leer
  und wächst mit den Aufrufen: `POST /selection/preview` ruft ab, übersetzt
  und lädt (ohne Matrix), `POST /selection/generate` zusätzlich Rohdaten und
  `.h5ad`.
- **Frontend/Visualisierung:** entschieden, gebaut und in Benutzung.
  PySide6-Desktopanwendung unter `/frontend` ("DataBridge Explorer"), eigenes
  Fenster statt Browser-Tab, Host-Prozess in der Conda-Env `F+E`, **kein**
  Compose-Service. Siehe
  [ADR-0004](../docs/adr/0004-frontend-pyside6.md) und den Abschnitt
  "Umgesetzt seit letztem Stand (2026-09-26)". MP-Lite (Bokeh,
  `wissensnetz/prototype/mp_lite/`) bleibt unangetastet als
  Oviedo-Vergleichsmassstab und startet nur noch mit
  `start_all.ps1 -WithMpLite`.
- **Orchestrierung:** Docker Compose; Python-Service intern über
  Conda/Mamba (`mediator/environment.yml`) für wissenschaftliche Pakete
  (anndata, scanpy, rdflib).

## Offene Punkte

- `POST /query` (GDC, alle Endpunkte) sowie die rohen `/geo/*`/`/ena/*`/
  `/cbioportal/*`-Endpunkte bleiben weiterhin unübersetzt (nur `POST
  /transform` übersetzt, je Quelle über ein eigenes `mapping_<source>.py`,
  siehe `mediator/app/semantic/README.md`) — das ist so beabsichtigt
  (Metadaten-Tier vs. semantische Schicht), kein offener Punkt mehr.
- Kein Enum-Alignment für GEO/ENA/cBioPortal (nur GDCs `primary_diagnosis`
  → NCIt); `db:organism`/`db:tumorStage`/`db:oncotreeCode` wären
  Kandidaten für ein künftiges Alignment, siehe "Grenzen" in
  `mediator/app/semantic/README.md`.
- cBioPortal-`db:Diagnosis`-Knoten (aus `AJCC_PATHOLOGIC_TUMOR_STAGE`/
  `TUMOR_STAGE`) erfüllen die `owl:minCardinality`-Restriktion auf
  `db:primaryDiagnosisLabel` nicht (kein Primärdiagnose-Text in
  cBioPortals Klinikdaten) — bekannte, dokumentierte Inkonsistenz, nur bei
  aktiviertem OWL-Reasoning relevant.
- Kein `owl:sameAs`-Abgleich zwischen GDC- und cBioPortal-`db:Case`-
  Instanzen derselben Person (unterschiedliche IDs: `case_id` vs.
  `patientId`) — offener nächster Schritt für echte Cross-Source-Queries.
- **P4, die Ersetzungslogik, ist der älteste offene Punkt.**
  `_load_selection_knowledge` in `mediator/app/main.py` hängt beim Laden nur
  an, es gibt kein `DELETE WHERE` je Fall (bewusste, im Docstring
  dokumentierte Schuld). Gehört Marcel, weil es Store-Semantik ist. Wichtig:
  **nicht "je Fall ersetzen", sondern Upsert je Property** -- ein Ersetzen des
  ganzen Fall-Subgraphen würde Attribute löschen, die eine frühere,
  reichhaltigere Auswahl beigetragen hat (Auswahl A mit gender+tumor_stage,
  danach B mit nur gender, würde tumor_stage verlieren).
- **ADR-0003 fehlt der Absatz zu dieser Ersetzungssemantik** unter "Zu
  tragen"; er ist in `wissensnetz/Tasks Archiv/HANDOFF_pablo_P4_ersetzen.md`
  zugesagt.
- **ADR-0004 Punkt 4 stimmt nicht mehr.** Dort steht Qt Designer mit
  `.ui`-Dateien; gebaut ist das Layout im Code. Die Abweichung ist in
  `frontend/README.md` dokumentiert, die ADR selbst aber unverändert.
  Da `main_window.py` inzwischen über 1.600 Zeilen hat, ist das keine
  Übergangslösung mehr, sondern die Entscheidung.
- **Erzeugte `.h5ad` liegen im Git.** `Export Anndata/` belegt rund 62 MB der
  etwa 74 MB verfolgten Dateien (vier Dateien), und `.gitignore` deckt den
  Ordner nicht ab. Solange nichts gepusht ist, reicht `git rm -r --cached`
  plus ein `.gitignore`-Eintrag; danach bleiben die Blobs in der Historie.
- **Der Rückkanal fehlt in der Oberfläche.** `write_feedback` und
  `list_findings` sind in MP-Lite fertig, im Explorer nicht angebunden. Erst
  damit wäre der Kreis aus dem Konzept geschlossen: Auswahl in der Karte,
  Hypothese, Named Graph.
- **Die Werteebene unter den Attributen** fehlt in der Suchauftrag-Ansicht
  (bewusst: nur bis zum Attribut). Solange sie fehlt, fällt ein doppelter
  Wert an derselben Property nicht auf, weil über `COUNT(DISTINCT ?case)`
  gezählt wird; P4 bleibt also unsichtbar.
- **Zweite Achse über NCIt.** `db:primaryDiagnosis` zeigt auf NCIt, und
  `enrichment.subclasses()` kann die `rdfs:subClassOf`-Hierarchie bereits
  lesen. Das ist der natürliche nächste Schritt der Netzansicht, setzt aber
  eine brauchbare Alignment-Tabelle voraus.
- Ontologie-/Schema-Design des Wissensnetzes über den jetzigen Kern-Ausschnitt
  hinaus (weitere GDC-Nodes, Wiederverwendung von GO/SO neben NCIt/DO).
- **Alignment-Tabelle: drei Einträge, einer davon falsch.**
  `wissensnetz/ontology/alignment/ncit_primary_diagnosis.json` bildet
  `Infiltrating duct carcinoma, NOS` auf C4194 ab, einen brustspezifischen
  Begriff, obwohl der Wert auch in PAAD-Fällen vorkommt. Das verstößt gegen
  Regel B der eigenen Kandidatenliste (`.../KANDIDATEN.md`: kein Organ
  hinzuerfinden). Die NCIt-Spalte dort ist ansonsten noch leer; 261 distinkte
  `primary_diagnosis`-Werte über 11.428 TCGA-Fälle sind erhoben.
  **Warnung aus der Erhebung:** GDC-Facets auf
  `cases.diagnoses.primary_diagnosis` lieferten still ungefilterte Zahlen
  (identisch zu den vollen Projektgrößen); verlässlich sind nur Abfragen je
  Projekt über `cases.project.project_id`.
- Cache-Tiers 2 (materialisierte anndata-Objekte) und 3 (transiente
  Rohdaten) haben nur ein Datei-Grundgerüst (`wrappers/gdc/cache.py`); echte
  Nutzung folgt erst mit der anndata-Transformation bzw. dem
  `gdc-client`-Bulk-Download.
- Global-as-View reicht für die aktuell einzige Quelle (GDC); bei weiteren
  Quellen ggf. Local-as-View-Formalisierung prüfen (siehe Mapping-Konzept).

## Umgesetzt seit letztem Stand (2026-09-26)

Dieser Eintrag holt den **gesamten Oberflächenteil** nach, der bisher in dieser
Datei fehlte: `/frontend` war hier zuletzt als leerer Platzhalter beschrieben,
tatsächlich ist es inzwischen eine gebaute und benutzte Anwendung mit rund
7.300 Zeilen.

### Die Oberfläche: DataBridge Explorer (PySide6)

- **Technologieentscheidung** in [ADR-0004](../docs/adr/0004-frontend-pyside6.md):
  PySide6 statt Bokeh, C#/WPF, Streamlit oder React. Gründe: eigenes Fenster
  ohne Browser, eine Sprache im ganzen Projekt, und die Anzeige kann die
  Lesefunktionen des Pakets `wissensnetz` direkt aufrufen, statt für jede
  Ansicht einen Endpunkt im Mediator zu brauchen.
- **Aufbau und eine durchgehaltene Regel:** Module ohne Qt-Import sind ohne
  Bildschirm testbar, deshalb liegt die Logik dort und nicht in den Widgets.
  Qt-frei sind `mediator_client.py` (HTTP), `store_reader.py` (die drei
  SPARQL-Abfragen), `morph.py` (Encodings und Positionen) und `ablauf.py`
  (welche Station was belegt). Qt-seitig: `main_window.py`, `netz_view.py`,
  `projektion_view.py`, `architektur_view.py`, `searchable_select.py`,
  `theme.py`, `worker.py`.
- **Zweite Regel:** außerhalb von `theme.py` steht kein Farbwert im Code.
- **Fenster:** dunkle Kopfzeile, links die Anzeigefläche, rechts das
  Auswahlpanel (360 px), darunter `Vorschau`, `Generieren`,
  `Als .h5ad speichern`, ganz unten die Statusleiste mit einem dauerhaften
  Feld für den Store-Stand.
- **Vier Ansichten, zwei Umschalter.** Oben `Suchauftrag` und `Projektion`,
  unten `Architektur` und `Textausgabe`. Die obere Ansicht hieß bis zum
  2026-09-26 `Wissensnetz` und wurde in `Suchauftrag` umbenannt, weil sie seit
  der Umstellung "Netz zeigt nur noch die Auswahl aus dem Panel" nicht mehr den
  Store-Inhalt zeigt, sondern den aktuellen Auftrag. **Die Bezeichner im Code
  heißen weiterhin `netz_view.py`, `NetzPanel`, `_knopf_netz`**; umbenannt
  wurden nur die Anzeigetexte, weil das eigentliche Wissensnetz als Ansicht
  später zurückkommen soll.
- **Auswahlpanel:** fünf einzeilige Felder (Krebs, Var, Obj, Datenquelle,
  Proben). Jedes klappt eine Karte auf; Kohorte und `Obj` haben ein Suchfeld.
  Kohorten sind **mehrfach** wählbar (Vergleich mehrerer Kohorten in einer
  Karte). Gesucht wird bei den Kohorten nur über das offizielle Studienkürzel.
  Nicht angebundene Werte stehen sichtbar, aber deaktiviert in der Liste und
  tragen ihren Grund als Hinweistext.
- **Grenze des Panels:** genau die elf Attribute aus `KNOWN_ATTRIBUTES`
  (`mediator/app/semantic/mapping.py`). Felder aus den GDC-Knoten Exposure,
  Treatment, Family History, Follow Up und Pathology Detail dürfen **nicht**
  ergänzt werden, weil `resolve_attribute()` bei einem Namen ohne Punkt
  `diagnoses.<name>` annimmt und sie damit still falsch auflöst. Der Grund
  steht als `_hinweis` in `frontend/config/panel.json`.

### Suchauftrag-Ansicht: der Store als gezeichnetes Netz

- Drei Reihen (Wurzel, Kohorten, Attribute der aufgeklappten Kohorte), gezeichnet
  in einem `QGraphicsView`, kein Browser und kein pyvis.
- Die Zahlen kommen aus **drei SPARQL-Abfragen** in `store_reader.py`. Die
  Attributabfrage kennt die Attributliste bewusst **nicht** (sie läuft über
  `?entity ?p ?v` mit `isLiteral(?v)`), damit eine vom Mediator dynamisch
  angelegte Property von allein erscheint. Wer dort eine Property-Liste
  einbaut, zerstört genau diese Eigenschaft.
- **Wachstum wird über zwei Abzüge ermittelt**, einen vor und einen nach dem
  Aufruf, verglichen im Speicher: neu (grün), gewachsen (blau, mit `+N`),
  unverändert. Das ist kein Umweg, sondern notwendig: **der Store weiß nicht,
  welcher Fall aus welchem Aufruf kam**, weil der Mediator alles in den
  Default-Graph lädt und `wissensnetz.selection.write_selection` nie aufruft.
  Es gibt kein Manifest und keinen Named Graph, `cases_for_selection` liefert
  deshalb nichts.
- Leerer Store und nicht erreichbarer Store sind zwei getrennte Zustände mit
  eigenen Meldungen. Ein nicht erreichbarer Store blockiert die Oberfläche
  nicht, weil Aufträge an den Mediator gehen und nicht an Fuseki.

### Projektionsansicht: Morphing Projections nativ

- Oviedos Technik (`morphing-projections-demo-and-dataset-preparation-master/`)
  als echtes Qt-Widget mit **pyqtgraph**, nicht als eingebettete Bokeh-App.
- **Die Mathematik wurde nicht neu geschrieben.** `encodings.py` und
  `h5ad_source.py` aus `wissensnetz/prototype/mp_lite/` sind reines numpy und
  anndata und werden wiederverwendet. **Sie dürfen nicht per `import` geholt
  werden**: `wissensnetz/prototype/` ist kein Paket, und `import encodings`
  träfe Pythons stdlib-Paket für Codecs. Sie werden deshalb über
  `importlib.util.spec_from_file_location` per Dateipfad geladen, genau wie
  `mp_lite/app.py` es tut.
- Position = Σ aᵢ·E[i] mit a = softmax(10·Regler). Oviedos 15 Regler in fester
  Reihenfolge; nicht encodierbare Variablen bleiben sichtbar, aber deaktiviert
  und nennen den Grund im Tooltip.
- **Kein erfundenes Layout.** Fehlt `obsm['X_tsne_genes']`, gibt es keine Karte,
  sondern den Klartext, was fehlt und wie man es erzeugt. MP-Lite darf als
  Prototyp auf synthetische Basis-Views zurückfallen, der Explorer nicht.
- Klick auf eine Probe holt den Kontext über `enrichment.case_context()` aus
  dem Store, im eigenen Prozess. Ein Fall, der nicht im Store liegt, wird als
  solcher benannt und ist kein Fehler.

### GDC-Feld `gender` existiert nicht mehr

Wichtigster Sachbefund dieses Zeitraums, live gegen `/files/_mapping` und
`/cases/_mapping` geprüft: GDC hat `demographic.gender` in
`demographic.sex_at_birth` umbenannt. Der alte Name existiert in der API nicht
mehr, und **GDC ignoriert unbekannte Felder stillschweigend**, weshalb die
Spalte lange unbemerkt leer blieb. Durch den ganzen Stack gezogen:

- TBox: `db:sexAtBirth` neu, `db:gender` bleibt als `owl:deprecated` stehen,
  weil Daten aus früheren Läufen sie tragen.
- `enrichment` liest beide Properties.
- Mediator: `KNOWN_ATTRIBUTES` führt `sex_at_birth`; der alte UI-Name `gender`
  wird über `LEGACY_ATTRIBUTE_ALIASES` weiter angenommen.
- MP-Lite, `check_h5ad`, Beispiel-ABox und alle Tests nachgezogen.

**Lehre daraus, die im Code festgehalten ist:** eine halb stimmende
Rückübersetzung zwischen Panel-Namen und Store-Property ist gefährlicher als
gar keine. Die Netzansicht zeigt deshalb den Property-Namen aus dem Store und
nur dann zusätzlich den Panel-Namen, wenn dieser mechanisch in camelCase genau
dem lokalen Namen entspricht. `has_metastasis` (liegt als
`db:metastasisAtDiagnosis` im Store) und `primary_diagnosis` (als
`db:primaryDiagnosisLabel`) bekommen bewusst keine zweite Zeile.

### Drei Anforderungen an den Mediator, alle erledigt

Aus `wissensnetz/HANDOFF_pablo_offene_punkte.md` (ersetzt zwei frühere
Handoffs), von Pablo umgesetzt und frontendseitig nachgezogen:

- **P1, Defekt:** ein langer Auftrag blockierte den ganzen Dienst.
- **P2:** Fortschritt während eines Auftrags melden. Die Architekturansicht
  zeigt die laufende Station jetzt live statt erst aus der Antwort.
- **P3:** den Auftrag ins `.h5ad` schreiben. Die Oberfläche kann den Auftrag
  aus einer fertigen `.h5ad` wiederherstellen, statt ihn aus dem Dateinamen zu
  raten.

Ebenfalls in diesem Zeitraum: Zeitgrenze für `Generieren` auf 30 Minuten mit
ehrlicher Meldung und Größenhinweis; Pablo hat ungenutzte Endpunkte entfernt
(`mediator/docs/CLEANUP_LOG_unused_endpoints.md`).

### Kleinkram, der Wissen trägt

- **Umlaute in den Anzeigetexten** (2026-09-26). Ersetzt wurde nur in
  Zeichenketten-Token ohne Dreifachquotes, gegen eine feste Wortliste mit
  Wortgrenzen. Drei Fallen, die dabei auffielen und weiter gelten:
  Variablennamen in f-Strings (`{faelle}` darf nicht zu `{fälle}` werden),
  die Zustandsschlüssel `LAEUFT`/`UEBERSPRUNGEN`/`UNVERAENDERT`, die keine
  Anzeigetexte sind, und echte "ue" in `Quelle`, `neue`, `Zuerst`.
  **Kommentare und Docstrings sind im Frontend weiterhin durchgehend ASCII.**
- **Windows-11-Falle, dokumentiert in `frontend/README.md`:** Top-Level-Fenster
  füllen keinen Hintergrund, weshalb `PopupCard.paintEvent` die Fläche selbst
  malt. Wer dort etwas ändert, prüft es mit einer Bildschirmaufnahme, nicht mit
  `widget.grab()`, das den Fensterhintergrund nicht mitmalt.
- **`pyside6` nicht über pip installieren**, sondern
  `conda install -c conda-forge pyside6`: das PyPI-Wheel ist gegen ein neueres
  ICU gebaut als das conda-Paket in der Env `F+E`, der Import scheitert dann
  mit "DLL load failed". `pyqtgraph` dagegen ist reines Python, dort ist pip
  unbedenklich. Beides steht als Kommentar in `requirements.txt`.

## Umgesetzt seit letztem Stand (2026-09-19)

- **Back-Mediator (M9, "Quellen-Routing vereinheitlichen") umgesetzt** —
  bisher letzter offener Punkt aus `recherche/Umsetzungsplan_UI-gesteuerte-
  Akquise.pdf` Abschnitt 3: `POST /selection/preview`/`/generate`
  übersetzten Menü-Parameter bisher nur für `source="gdc"`, alle anderen
  Quellen lösten einen `ValueError` aus.
  - **Kernerkenntnis:** die Panel-Zeile "Krebs" liefert einen GDC-
    Projekt-Code (z. B. "TCGA-BRCA"), ist aber eigentlich eine **Krebsart**
    — GEO/cBioPortal kennen keine GDC-Codes, nur Freitext-/Stichwortsuche.
    Neues Modul `mediator/app/semantic/cancer_types.py`
    (`TCGA_COHORT_NAMES`/`cancer_name()`) übersetzt daher das Konzept, nicht
    den rohen String; dieselbe Quelle (GDC `/projects`, Feld `name`) wie
    `frontend/config/panel.json`s `cohort_labels`, damit keine zwei
    unabhängig gepflegten Listen auseinanderlaufen.
  - `mediator/app/main.py::_selection_fetch` (GDC-spezifisch geformt,
    `(hits, cases, failed_cohorts)`) ersetzt durch einen Dispatcher
    `_fetch_selection_level()` + `SelectionFetchResult`-Dataclass
    (`graph`/`star_annotations`/`failed_cohorts` + ein lazy
    `build_anndata`-Callback, den nur `/generate` aufruft — Entscheidung
    7.3 bleibt dadurch unverändert gültig). Vier Quell-Zweige:
    - **`gdc`** — unverändert, nur umverpackt (`_fetch_gdc_level`).
    - **`cbioportal`** — voll angebunden (Vorschau UND Generieren):
      `_resolve_cbioportal_study()` bildet Kohorte→Studie ab (gestufte
      Präferenz: TCGA-PanCancer-Atlas-Studie > irgendeine TCGA-Studie mit
      dem Code > irgendeine Studie mit dem Code > erster Stichwort-Treffer —
      cBioPortals Trefferreihenfolge ist keine Qualitätsordnung, live
      beobachtet für "brca"); `get_molecular_data()` mit neuem, live
      verifiziertem `cancer_types.DEMO_GENE_PANEL` (15 Onko-Gene,
      Entrez-IDs gegen `POST /api/genes/fetch` geprüft, explizit als
      Demo-Panel dokumentiert, kein Vollständigkeitsanspruch).
    - **`geo`** — Vorschau real (`GEOWrapper.query()` mit
      `build_search_term(..., extra=[...])`, nicht `.search()`, das kein
      `extra` durchreicht), Generieren **Best-Effort** (mit dem Nutzer so
      abgestimmt): lädt Supplementary-Dateien, versucht nur `.txt`/`.tsv`/
      `.csv`(`.gz`) generisch als ID/Wert-Tabelle zu lesen — GEO hat kein
      einheitliches Dateiformat je Serie. Scheitert das für eine Ebene,
      bleibt das RDF/`turtle` dieser Ebene trotzdem erhalten (nur der
      `.h5ad`-Teil schlägt fehl), andere Ebenen sind unberührt. Live
      beide Ausgänge beobachtet: TCGA-THCA erfolgreich (4 Proben × 10
      Feature aus echten Supplementary-Tabellen), TCGA-BRCA/-LUAD sauber
      gescheitert ("keine auswertbare Tabelle").
    - **`ena`** — bewusst weiterhin nicht angebunden, jetzt aber mit
      inhaltlicher Begründung statt "noch nicht angebunden": ENA
      organisiert nicht nach Krebsart und der Wrapper hat keine
      Freitextsuche.
  - **Bug gefunden und behoben** (nicht nur Back-Mediator-Code):
    `expression.build_var()` konnte eine `symbol`-Spalte aus
    ausschließlich `None` nicht nach `.h5ad` schreiben (h5py:
    `TypeError: Can't implicitly convert non-string objects to strings`) —
    traf jede Quelle ohne `gene_labels` (z. B. GEOs generischer Export).
    `build_obs()` hatte dieselbe Normalisierung (`None` → `""` für
    object-Spalten) bereits; `build_var()` jetzt angeglichen. Live als
    Server-500 reproduziert (GEO-Generate für TCGA-LUAD) und nach dem Fix
    verifiziert (kein Crash mehr, sauberer Fehl- oder Erfolgsausgang).
  - `frontend/config/panel.json`: `cbioportal` neu in `sources`
    (`enabled: true`), `geo` auf `enabled: true` (mit Hinweis "Generieren:
    Best-Effort"), `ena` bleibt `enabled: false` mit aktualisierter
    inhaltlicher Begründung. UI ist rein datengetrieben
    (`main_window.py::_source_entries`) — keine weiteren Codeänderungen im
    Frontend nötig.
  - Live gegen den echten, neu gebauten Container verifiziert (nicht nur
    TestClient/Mock): `/selection/preview` + `/selection/generate` für
    `cbioportal` (`brca_tcga_pan_can_atlas_2018`, echtes `.h5ad` mit 5
    Proben × 15 Genen inkl. `X_tsne_genes`), `/selection/preview` für `geo`
    (echte GSE-Treffer, 1032 Tripel), `/selection/generate` für `geo`
    (Erfolg UND sauberer Fehlschlag je einmal beobachtet), `/selection/*`
    für `ena` (klare Fehlermeldung, kein Absturz). Alle 22 Wrapper- und 26
    Frontend-Tests weiterhin grün.
  - **Bewusst nicht Teil dieses Durchgangs:** `cBioPortal`s `obs` trägt
    bislang nur den `sample_id`-Index (keine Klinikfelder wie bei GDC/
    `build_obs`) — ehrliche Beschränkung des ersten Wurfs, kein Bug;
    Erweiterung wäre ein separater, kleiner Folgeschritt.

## Umgesetzt seit letztem Stand (2026-09-17, Teil 3)

- **"Der Store wächst mit den Aufrufen"** umgesetzt (Handoff von Marcel:
  `wissensnetz/HANDOFF_pablo_store_waechst.md`, ersetzt die B1/B2-Vorschläge
  aus `wissensnetz/HANDOFF_review_selection.md`). Store ist leer beim Start,
  wächst mit jedem `/selection/*`-Aufruf:
  - **P1** — `SelectionRequest.load: bool = True` + neuer Helper
    `_load_selection_knowledge()`: sowohl `/selection/preview` als auch
    `/selection/generate` laden ihren übersetzten Wissensbestand jetzt in
    den Default-Graph (Reihenfolge: Abruf → Übersetzung → **Laden** → obs →
    Matrix). Beantwortet Entscheidung 7.3 endgültig: `preview` = Abruf +
    Übersetzung + Laden ohne Matrix, `generate` zusätzlich Download + `.h5ad`.
  - **P3 (Übergangslösung)** — `_build_anndata_from_hits` filtert
    `all_cases(store)` jetzt auf die `submitter_ids` aus dem geteilten Abruf,
    statt den kompletten Bestand zu nehmen (funktional identisch zu vorher,
    da `build_obs` ohnehin nur einzeln nachschlägt — reine Vorbereitung auf
    den Austausch gegen `cases_for_selection`, sobald Marcel liefert).
  - **P5** — `/selection/generate` hat jetzt denselben
    `wrapper.cache.materialized`-Kurzschluss wie `/export/anndata`: eine
    Auswahl mit identischem `recipe_key` wird weder erneut heruntergeladen
    noch erneut gebaut (`turtle`/`triple_count` bleiben dabei bewusst leer
    in der Antwort — kompletter Kurzschluss statt teilweiser Neuberechnung).
  - **P4 (Entscheidung, NICHT selbst gebaut):** Laden ist reines Anhängen,
    kein `DELETE WHERE` je Fall vor dem Laden — dokumentierte, bewusste
    Schuld direkt im Code (`_load_selection_knowledge`-Docstring). **Bitte an
    Marcel:** die Ersetzungslogik wie in P4 vorgeschlagen liefern (Vokabular/
    Store-Semantik ist seins, siehe seine eigene Begründung zu P2) — sonst
    entstehen bei geänderten GDC-Werten für denselben Fall zwei Werte an
    derselben Property.
  - **P2 und die finale P3-Lösung bleiben blockiert**: `wissensnetz.selection`
    (`write_selection`) und `wissensnetz.cases_for_selection` existieren noch
    nicht (geprüft, `__init__.py` exportiert sie nicht) — warten auf Marcels
    Lieferung, wie im Handoff selbst vorgesehen.
  - Live gegen einen wirklich leeren Store verifiziert (`docker compose down`
    + `docker volume rm` für `graph-db-data`, `wissensnetz init`, dann
    `db:Case`-Anzahl 0 → 3 nach `/selection/generate` (TCGA-ACC) → 8 nach
    zusätzlichem `/selection/preview` (TCGA-LUAD), inkl. `obs`-Werte aus dem
    frisch geladenen Store nachgewiesen). Cache-Kurzschluss (P5) separat
    verifiziert (Cache-Datei entfernt → Turtle wieder frisch berechnet).
    Alle 22 Wrapper-Tests weiterhin grün.

## Umgesetzt seit letztem Stand (2026-09-17, Teil 2)

- **M3/M6/M7 real verdrahtet** (den im vorherigen Durchgang bewusst
  zurückgestellten "größten Eingriff" aus `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf`
  jetzt umgesetzt, da er die Basis für Frontend/Wissensnetz ist):
  - **M3** — `fetch_selection_files()` (`mediator/app/main.py`): EIN
    Files-Query pro Kohorte liefert gleichzeitig die Datei/Proben-Zuordnung
    UND die eingebetteten Case-Objekte für `cases_to_graph` — live
    verifiziert, dass GDC bei `cases.<feld>`-Feldern an `/files` dieselbe
    verschachtelte Case-Struktur liefert wie der eigenständige
    `/cases`-Endpunkt. Ersetzt die früher zwei unabhängig gezogenen
    Stichproben von `/transform` und `/export/anndata`.
  - **M6** — `_build_anndata_from_hits()`: der komplette Download-/Matrix-/
    obs-Aufbau aus `export_anndata` in eine wiederverwendbare Funktion
    extrahiert; sowohl `POST /export/anndata` als auch `POST
    /selection/generate` bauen jetzt auf demselben Kern und denselben
    `hits` auf.
  - **M7** — `_selection_recipe_key()`: derselbe `recipe_key` für dieselbe
    Auswahl unabhängig von preview/generate (live verifiziert, identisch
    zwischen beiden Endpunkten).
  - `POST /selection/preview` und `POST /selection/generate` sind jetzt
    keine Stubs mehr: `preview` macht den geteilten Abruf + RDF-Serialisierung
    ohne Matrizen (Entscheidung 7.3), `generate` zusätzlich `.h5ad` (inkl.
    tSNE) aus denselben `hits`. Jede Auswahl-Ebene scheitert unabhängig von
    den anderen (`status="error"` + `error`-Feld statt Gesamtabbruch,
    Entscheidung 7.2) — live verifiziert mit einer funktionierenden
    GDC-Ebene neben einer absichtlich nicht angebundenen `source="geo"`-Ebene.
  - `POST /export/anndata` intern auf `fetch_selection_files` +
    `_build_anndata_from_hits` umgestellt — Regressionstest bestätigt
    identisches Verhalten (gleiche `n_obs`/`n_vars`/Metadaten-Form wie vor
    dem Refactor, gegen den neu gebauten Container verifiziert).
  - End-to-End gegen den echten, neu gebauten Container verifiziert (nicht
    nur TestClient/Mock): `/export/anndata` (2 Kohorten × 2 Dateien, 4 Proben,
    60660 Gene), `/selection/preview` (inkl. dynamisch erzeugter Property
    `db:priorMalignancy` aus einem GDC-Feld, das gar nicht in
    KNOWN_ATTRIBUTES steht), `/selection/generate` (Turtle + `.h5ad` inkl.
    `X_tsne_genes` aus derselben Stichprobe). Alle 21 Wrapper-Tests und
    `scripts/check_mediator.py` weiterhin grün.
  - Dabei aufgefallen (kein Bug, dokumentiert): GDC lässt das gesamte
    `demographic`-Objekt weg, wenn das einzige angefragte
    Demographic-Feld für einen Case null ist (statt `{"gender": null}` zu
    liefern) — identisch reproduzierbar sowohl über `/files` (neuer M3-Weg)
    als auch direkt über `/cases` (alter `/transform`-Weg), also keine
    Regression, sondern eine bereits vorher bestehende GDC-Eigenheit.
- **Bewusst weiterhin nicht Teil dieses Durchgangs** (liegt bei anderen/ist
  laut Plan selbst "Später"): **M8** (build_obs verliert GDC-Fallback —
  braucht K1/K2 von Marcel, die es noch nicht gibt), **M9** (Quellen-Routing
  vereinheitlichen, `POST /query` kann weiterhin nur GDC — `SingleSelection.source`
  ist strukturell vorbereitet, liefert für `!= "gdc"` aber einen klaren
  Level-Fehler statt eines Absturzes), **W3–W7** (Julian: Facetten,
  DNA-Methylierung/Mutationen), **K1–K7** (Marcel: Named Graph je Auswahl,
  Vorschau-Lesefunktion, CLI, Attributkatalog aus der TBox, NCIt-Alignment,
  MP-lite-Anbindung).

## Umgesetzt seit letztem Stand (2026-09-17)

- Erster Durchgang von `recherche/Umsetzungsplan_UI-gesteuerte-Akquise.pdf`
  Abschnitt 3 (Mediator-Teil, Pablo) umgesetzt: **M1** (`SingleSelection`/
  `SelectionRequest`/`SelectionLevelResult`/`Selection{Preview,Generate}Response`
  in `mediator/app/schemas.py`), **M2** (`POST /selection/preview` und
  `POST /selection/generate` in `mediator/app/main.py`, bewusst als Stub —
  `status: "stub"`, noch kein echter Abruf), **M4** (`TRANSFORM_CASE_FIELDS`
  ersetzt durch `resolve_case_fields()`, aus Attributen abgeleitet statt fest
  einprogrammiert) und **M5** (`cases_to_graph` nutzt jetzt eine generische
  Attribut-Mapping-Tabelle, `app/semantic/mapping.py::KNOWN_ATTRIBUTES`/
  `resolve_attribute()`, statt der früheren if-Kaskade).
- Drei offene Entscheidungen aus Abschnitt 7 des Plans mit dem Nutzer
  getroffen (bestimmen M1/M5 direkt):
  - **7.2 "weitere Ebene":** parallele, gleichrangige Auswahlen zum
    Vergleich (nicht UND-Verfeinerung derselben Auswahl) — `levels` in
    `SelectionRequest` ist entsprechend eine Liste unabhängiger
    `SingleSelection`-Objekte.
  - **7.3 "Was macht Vorschau":** geteilter Abruf ohne Matrizen (Generieren
    baut später auf demselben Ergebnis auf) — Grundlage für M3.
  - **7.5 Undeklarierte Properties:** dynamisch erlaubt. Unbekannte
    UI-Attribute erzeugen zur Laufzeit eine neue `db:`-Property inline im
    erzeugten Graphen (`owl:DatatypeProperty` + `rdfs:domain/range/label/
    comment`, live getestet: `diagnoses.prior_malignancy` -> `db:priorMalignancy`)
    statt in `wissensnetz/ontology/databridge-core.ttl` nachgetragen zu
    werden — macht K4 (Wissensnetz muss TBox vorab erweitern) unkritisch,
    schwächt aber die in `wissensnetz/CLAUDE.md` festgelegte alleinige
    TBox-Besitzerschaft des Wissensnetzes ab; das sollte dem Team bewusst
    sein.
  - Rückwärtskompatibilität verifiziert: `cases_to_graph()`/
    `TRANSFORM_CASE_FIELDS` ohne `attributes` liefern exakt denselben
    Tripel-/Feldumfang wie vor dem Refactor (113 Tripel für die BRCA-Fixture,
    unverändert; `POST /transform` und `scripts/check_mediator.py` weiterhin
    grün, alle 21 Wrapper-Tests grün).
- **Bewusst NICHT umgesetzt in diesem Durchgang:** M3 (gemeinsamer
  Abrufschritt, der `/transform` und `/export/anndata` auf ein Proben-Set
  zusammenführt), M6, M7 real verdrahtet — der Plan selbst nennt M3 den
  "größten Eingriff"; `/selection/preview`/`/selection/generate` liefern
  bislang nur `recipe_key`/`requested_fields` je Ebene, keinen echten Abruf.
  Folgt als eigener, separat verifizierter Schritt, um die aktuell
  produktiv laufenden Pfade `/transform`/`/export/anndata` nicht ungeprüft
  zu brechen. M9 (Quellen-Routing vereinheitlichen, `POST /query` kann
  bisher nur GDC) ebenfalls offen. Wrapper-Teil (Julian, W1–W7) und
  Wissensnetz-Teil (Marcel, K1–K7) des Plans sind nicht Teil dieses
  Durchgangs.

## Umgesetzt seit letztem Stand (2026-09-02, Teil 3)

- **Bug behoben:** `.\start_all.ps1 -Size 100 -PancancerSize 10` (bzw. jeder
  Pancancer-Export mit vielen Dateien) brach mit `GDC-API nicht erreichbar
  oder Fehler: 414 Client Error: Request-URI Too Long` ab. Ursache: Das
  seit dem Stratifizierungs-Fix (Teil 1) pro Kohorte gesammelte Datei-Set
  (z. B. 32 Kohorten × 10 = bis zu 320 Dateien) landete komplett als
  `files.file_id`-`in`-Liste im `filters`-Query-Parameter von
  `GDCWrapper.build_manifest()`/`.query()` (GET, `wrappers/gdc/client.py`)
  — bei ~320 IDs (~13 KB Filter-JSON) lehnt GDCs Server die resultierende
  URL ab. Live reproduziert (32 sequenzielle Metadaten-Queries liefen
  einwandfrei in 8s, der anschließende `build_manifest`-Call mit allen 320
  IDs schlug mit 414 fehl) und live gegen die echte GDC-API verifiziert
  behoben: `query()` und `build_manifest()` nutzen jetzt POST mit
  JSON-Body statt GET mit Query-String (von GDC laut API-Doku für genau
  diesen Fall vorgesehen, identische Response-Form) — unabhängig von der
  Filtergröße robust. `wrappers/tests/test_gdc_client.py` entsprechend
  angepasst (`FakeSession` bietet jetzt `.post()` und `.get()`, `get_schema()`
  bleibt GET). Alle 21 Wrapper-Tests weiterhin grün; End-to-End-Reproduktion
  des ursprünglichen 320-Datei-Falls über den echten (gefixten)
  `build_manifest()` erfolgreich (321 Zeilen Manifest).

## Umgesetzt seit letztem Stand (2026-09-02, Teil 2)

- Semantische Mapping-Schicht für die drei bisher nur REST-durchgereichten
  Wrapper `geo`/`ena`/`cbioportal` ergänzt (bisher nur GDC): drei neue
  Module `mediator/app/semantic/mapping_geo.py`, `mapping_ena.py`,
  `mapping_cbioportal.py`, alle mit derselben Rückgabeform wie
  `mapping.cases_to_graph` (`(Graph, star_annotations)`), damit
  `serialize_with_provenance` unverändert wiederverwendet wird. `POST
  /transform` unterstützt jetzt `source` = `gdc`/`geo`/`ena`/`cbioportal`
  (`mediator/app/main.py`, `mediator/app/schemas.py`).
- Ontologie erweitert (`wissensnetz/ontology/databridge-core.ttl`): neue
  Klassen `db:Series` (GEO), `db:Study` (ENA), gemeinsam genutztes `db:Run`
  (GEO+ENA) mit `db:hasRun`/`db:isRunOf`; neue Properties `db:organism`,
  `db:sampleCount`, `db:experimentType`, `db:releaseDate`, `db:ftpLink`,
  `db:libraryStrategy`, `db:instrumentPlatform`, `db:readCount`, `db:age`,
  `db:cancerType`, `db:oncotreeCode`. cBioPortal nutzt bewusst die
  bestehenden GDC-Klassen/-Properties (`db:Project`/`db:Case`/
  `db:Demographic`/`db:Diagnosis`/`db:Sample`, `db:gender`/`db:race`/
  `db:ethnicity`/`db:vitalStatus`/`db:tumorStage`/`db:sampleType`) statt
  Duplikate — cBioPortal-PATIENT-Attribute werden dafür (wie bei GDC) auf
  `db:Demographic`/`db:Diagnosis`-Unterknoten verteilt statt direkt auf
  `db:Case` geschrieben (erste Implementierung hatte das falsch direkt auf
  Case gesetzt — Domain-Verletzung gegen die deklarierten `rdfs:domain`,
  beim Live-Test gegen echte cBioPortal-Daten gefunden und korrigiert).
- Neue Doku `mediator/app/semantic/README.md`: vollständige Label-Tabellen
  je Quelle (GDC/GEO/ENA/cBioPortal), Wiederverwendungs-Übersicht, bekannte
  Grenzen (kein Alignment für die drei neuen Quellen, cBioPortal-
  `db:Diagnosis`-Cardinality nicht erfüllt, kein GDC↔cBioPortal-
  `owl:sameAs`), Beispielaufrufe. Von Root-README verlinkt.
- Alle vier `/transform`-Pfade live gegen die echten APIs verifiziert
  (GDC-Regression + GEO/ENA/cBioPortal neu, inkl. Domain-Korrektheit der
  cBioPortal-Tripel per rdflib-Introspektion geprüft); bestehende
  `check_mediator.py`/Pytest-Suite weiterhin grün.

## Umgesetzt seit letztem Stand (2026-09-02)

- Stratifiziertes Sampling für `POST /export/anndata` (Handoff von Marcel:
  `wissensnetz/HANDOFF_export_stratified.md`). Bug: Bei Multi-Kohorten-Exports
  (`project_id` als Liste, z. B. Pancancer) holte `export_anndata` alle Files
  in einem einzigen GDC-Query mit `size` als Gesamt-Limit — ohne
  Stratifizierung lieferte GDCs Default-Reihenfolge de facto nur Proben aus
  einer einzigen Kohorte (`obs["cancer"]` z. B. 40× LUAD statt Pancancer-Mix).
  Fix: Files werden jetzt pro Projekt einzeln abgefragt (`AnndataExportRequest.
  per_project_size`, neu in `mediator/app/schemas.py`; Loop in
  `mediator/app/main.py`, `export_anndata`), eine fehlschlagende Kohorte
  überspringt nur sich selbst (`failed_projects` in der Antwort) statt den
  gesamten Export abzubrechen. `per_project_size` ist Teil des
  `recipe`-Cache-Keys, damit stratifizierte Anfragen einen eigenen
  Materialized-Cache-Eintrag bekommen. Bei einzelnem `project_id` (kein
  `per_project_size`) bleibt das Verhalten unverändert (ein Query, `size` als
  Gesamtzahl) — mit einem gemockten `wrapper.query` verifiziert (Multi-Projekt-
  Stratifizierung inkl. übersprungener fehlerhafter Kohorte, sowie
  Rückwärtskompatibilität für Einzel-Projekt).

## Umgesetzt seit letztem Stand (2026-08-28)

- Drei neue Wrapper analog zu `wrappers/gdc` (Julian): `wrappers/geo`,
  `wrappers/ena`, `wrappers/cbioportal` — je eigenständiges Python-Unterpaket
  gemäß ADR-0001, mit Metadaten-Suche, Schema-Introspektion und
  Bulk-Tier-Äquivalent; live gegen die echten APIs verifiziert. `to_anndata`
  bewusst `NotImplementedError` (außerhalb Wrapper-Scope). **Noch nicht an
  den Mediator angebunden** (kein `/query`/`/schema`-Routing in
  `mediator/app/main.py` für diese drei Quellen).
- Pytest-Unit-Tests für `wrappers/gdc` ergänzt (gemocktes `requests`,
  kein Netzwerkzugriff): `build_filters`, `query`/`search`-Pagination,
  `get_schema`, Fehlerfälle (HTTP-Fehler, unbekannter Endpunkt).
- Wissensnetz-Seite (Marcel) hat MP-lite in mehreren Schritten an das
  Original-Tool von Oviedo angeglichen (Aufgaben 5–8, siehe
  `wissensnetz/TASKS_aufgabe5.md` bis `_aufgabe8.md`): Hover mit voller
  Oviedo-Feldliste, Multi-Variablen-Morphing (ein Slider pro Variable,
  clientseitig), alle 32 TCGA-Kohorten (Pancancer) über `scripts/load_gdc.py
  --pancancer`, sowie ein `db:Sample`-Modell für das Feld `type`
  (`sample_type`). Offene Gegenstücke dazu sind in
  `wissensnetz/prototype/mp_lite/HANDOFF.md` present: Mediator muss die
  neuen klinischen Felder (race/ethnicity/vital_status/tumor_stage/
  morphology/site_of_resection_or_biopsy/has_metastasis/sample_type) auf die
  bereits deklarierten `db:`-Properties mappen (Pablo) — Wrapper-seitig
  (Julian) ist das bereits möglich, siehe unten.
- GDC-Wrapper-seitige Prüfung für HANDOFF Teil 1a (Julian): live gegen die
  echte GDC-API verifiziert, dass `GDCWrapper.query()`/`.search()` die 7
  angeforderten klinischen Felder (`demographic.race/ethnicity/vital_status`,
  `diagnoses.morphology/site_of_resection_or_biopsy/
  ajcc_pathologic_stage/metastasis_at_diagnosis`) unverändert unterstützen —
  der `fields`-Parameter wird generisch durchgereicht, kein Wrapper-Code
  nötig. `diagnoses.tumor_stage` existiert im aktuellen GDC-Schema **nicht**
  (stattdessen `ajcc_pathologic_stage` verwenden).

## Umgesetzt seit letztem Stand (2026-08-24)

- Direkte Anbindung Mediator → graph-db: `POST /transform` akzeptiert
  `load: true` (optional `graph: <IRI>`) und schreibt das erzeugte Turtle
  dann direkt per Graph Store Protocol in Fuseki (`wissensnetz.GraphStore.
  load_turtle`), statt es nur als Text zurückzugeben. Dazu installiert der
  Mediator das `wissensnetz`-Package (`mediator/environment.yml`,
  `mediator/Dockerfile`: `-e /wissensnetz`); in `docker-compose.yml` zeigt
  `GRAPH_DB_URL` beim Mediator-Service fest auf `http://graph-db:3030`
  (Compose-internes Netzwerk statt host-seitigem `GRAPH_DB_PORT`).
  Abhängigkeitsrichtung bleibt Mediator → Wissensnetz, wie in
  `wissensnetz/pyproject.toml` von Anfang an vorgesehen. `scripts/load_gdc.py`
  (zweistufiger externer Weg: Turtle abrufen, dann `GraphStore.load_turtle`)
  bleibt als Alternative bestehen, z. B. für lokale Mediator-Läufe ohne
  Docker/GRAPH_DB_URL-Override.

## Umgesetzt seit vorletztem Stand (2026-08-20)

- Semantische Mapping-Ebene GDC → RDF/OWL für den Kern-Ausschnitt
  case/project/demographic/diagnosis, aufbauend auf Marcels
  Wissensnetz-Konzept (`wissensnetz/Mapping-Konzept_GDC-zu-RDF-OWL`,
  `wissensnetz/Wissensnetz_Konzept-Entwurf`): Pro-Node-Klassen
  (`db:Case`/`db:Project`/`db:Demographic`/`db:Diagnosis`, Namespace
  `http://databridge.hka/onto#`) statt abstrahierter Klassen, RDF-star für
  Provenienz/Konfidenz von Alignment-Aussagen (passend zu ADR-0002).
- Basis-Ontologie (TBox) unter `wissensnetz/ontology/databridge-core.ttl`,
  Alignment-Gerüst unter `wissensnetz/ontology/alignment/` (bewusst leer,
  keine ungeprüften NCIt-Codes committet).
- Mapping-Code als reines Python/`rdflib` (`mediator/app/semantic/mapping.py`)
  — kein RML/Java-Unterbau, passt zum bestehenden Conda/Mamba-Stack.
- Mediator exponiert dies über `POST /transform` (GDC-Cases → Turtle) und
  `GET /ontology` (TBox-Inspektion), `mediator/app/main.py`.
- End-to-End-Beispiel mit TCGA-BRCA-Beispieldaten:
  `mediator/sample_data/cases_brca_sample.json`,
  `mediator/scripts/example_gdc_to_rdf.py`.
- Anleitung für neue Quellen: `docs/adding_new_sources.md`.

## Umgesetzt davor (2026-08-19)

- Abfrage-/Schema-Introspektionslogik im GDC-Wrapper implementiert
  (`GDCWrapper.query/search/get_schema/build_manifest`,
  `wrappers/gdc/client.py`) und live gegen die echte GDC-API verifiziert
  (Testfall TCGA-BRCA/RNA-Seq/open).
- Mediator exponiert dies über REST (`POST /query`, `GET /schema/{endpoint}`,
  `POST /manifest`, `mediator/app/main.py`) — weiterhin als Python-Package im
  Mediator-Container gemäß ADR-0001, kein eigener `wrapper-gdc`-Service.
- Datei-basiertes Cache-Grundgerüst für die drei Cache-Tiers
  (`wrappers/gdc/cache.py`, Verzeichnis über `DATABRIDGE_CACHE_DIR`).

## Verweise

- Architekturentscheidungen: `/docs/adr`
- Literaturrecherche (Ontologien, RDF vs. Property Graph): `/recherche`
- Organisatorisches: `/Orga`
