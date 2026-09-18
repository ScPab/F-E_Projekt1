# frontend — DataBridge Explorer (PySide6)

Die Auswahl-Oberfläche: eine Auswahl zusammenstellen, sie an den Mediator
schicken, dessen Antwort anzeigen. Eigenes Fenster, kein Browser-Tab
(siehe [ADR-0004](../docs/adr/0004-frontend-pyside6.md)).

Erste Fassung (Aufgabe 17), bewusst einfach.

## Voraussetzungen

```powershell
conda activate F+E
cd C:\Dev\F+E\F-E_Projekt1
conda install -c conda-forge pyside6     # NICHT per pip, siehe unten
pip install -r requirements.txt
```

> **PySide6 muss aus conda kommen, nicht aus pip.** Das PyPI-Wheel bringt kein
> ICU mit und ist gegen ein neueres ICU gebaut als das conda-Paket `icu 73` in
> der Env `F+E`. `Qt6Core.dll` findet dann die versionsbehafteten ICU-Exporte
> nicht, und der Import scheitert mit
> `DLL load failed while importing QtCore: Die angegebene Prozedur wurde nicht
> gefunden`. Das conda-Paket (6.11.0) ist gegen das vorhandene `qtbase`/`icu`
> gebaut und funktioniert. Derselbe Hinweis steht in `requirements.txt`.

**Fuseki muss laufen**, obwohl diese Oberfläche selbst nicht aus dem Store
liest: der **Mediator** schreibt das übersetzte Turtle bei jedem
`/selection/*`-Aufruf in den Default-Graph (ADR-0003, „der Store wächst mit den
Aufrufen"). Ohne Fuseki schlägt der Aufruf mediator-seitig fehl.

## Start

```powershell
.\start_all.ps1 -NoUi        # Dienste hochfahren (Fuseki + Mediator)
python frontend\app.py       # Fenster öffnen
```

Oder in einem Zug:

```powershell
.\start_all.ps1 -WithUi
```

Die Basis-URL des Mediators kommt aus `MEDIATOR_URL`, Voreinstellung
`http://localhost:8000`.

## Bedienung

Rechts das Auswahlpanel — Kohorte, Modalität, klinische Attribute, Datenquelle,
Probenzahl. Unten links die beiden Schaltflächen:

| | |
| --- | --- |
| **Vorschau** | `POST /selection/preview` — Abruf, Übersetzung, Laden in den Store. Keine Rohdaten, keine Matrix. Billig. |
| **Generieren** | `POST /selection/generate` — dasselbe, plus Rohdaten-Download und `.h5ad`. Dauert Minuten. |

Nicht angebundene Werte (DNA-Methylierung, Mutationen, alle Quellen außer GDC)
stehen sichtbar in der Liste, sind aber deaktiviert und tragen den Grund als
Hinweistext. Ehrliche Lücke statt unsichtbarer Grenze — dasselbe Prinzip wie bei
den MP-Lite-Slidern.

## Aufbau

| Datei | Zweck |
| --- | --- |
| `app.py` | Einstieg: `QApplication`, Stylesheet setzen, Fenster zeigen |
| `main_window.py` | Fenster, Panel, Signals/Slots, Formatierung der Antwort |
| `mediator_client.py` | HTTP gegen den Mediator — **ohne Qt-Import**, deshalb ohne Fenster testbar |
| `worker.py` | `QThread`-Worker für die langen Aufrufe |
| `theme.py` | Farben und Stylesheet an genau einer Stelle |
| `config/panel.json` | Modalitäten, Quellen, Attribute nach Knoten gruppiert |
| `tests/test_mediator_client.py` | Tests ohne Qt und ohne Netz (`requests` gemockt) |

```powershell
pytest frontend/tests -q
```

## Drei Festlegungen, die man kennen sollte

**Alle Netzaufrufe laufen über einen Worker-Thread.** `/selection/generate`
dauert Minuten; im GUI-Thread würde das Fenster einfrieren und abgestürzt
wirken. Während eines Aufrufs sind beide Schaltflächen ausgegraut und die
Statusleiste sagt, was läuft.

**Außerhalb von `theme.py` steht kein Farbwert im Code.** Wer das Aussehen
ändert, ändert es dort.

**Das Panel führt genau die elf Attribute aus `KNOWN_ATTRIBUTES`**
(`mediator/app/semantic/mapping.py`). Die vollständige GDC-Feldliste steht in
[`../wissensnetz/GDC_TCGA_Klinische_Datenfelder.md`](../wissensnetz/GDC_TCGA_Klinische_Datenfelder.md),
aber Felder aus den Knoten Exposure, Treatment, Family History, Follow Up und
Pathology Detail dürfen hier **nicht** aufgenommen werden: `resolve_attribute()`
nimmt bei einem Namen ohne Punkt `diagnoses.<name>` an und löst sie damit falsch
auf. Der Grund steht auch als `_hinweis` in `config/panel.json`.

## Abweichung von ADR-0004, Punkt 4

ADR-0004 sieht den Oberflächen-Entwurf als Qt-Designer-`.ui`-Dateien vor. Diese
Fassung baut das Layout **im Code**: weniger bewegliche Teile für ein Fenster mit
vier Auswahlzeilen und zwei Schaltflächen. **Sobald das Panel wächst, auf `.ui`
umstellen und ADR-0004 entsprechend ergänzen.**

## Was diese Fassung ausdrücklich nicht tut

Kein Zugriff auf das Wissensnetz — kein `GraphStore`, kein
`cases_for_selection`, keine Tabelle aus dem Store, keine Graphansicht. Die
Anzeigefläche zeigt genau das, was der Mediator selbst zurückgibt. Einzige
Ausnahme beim Import ist die Kohorten-Konstante `wissensnetz.cohorts.COHORT_PROJECT_IDS`,
damit Ladeskript, MP-Lite und Oberfläche dieselbe Wahrheit nutzen; schlägt der
Import fehl, greift die Liste aus `panel.json`.

Ebenfalls nicht: geschachtelte Auswahl-Ebenen, Zählungen oder Facetten im Panel,
Karte oder Plot, PyInstaller-Paket. Das sind Folgeaufgaben.
