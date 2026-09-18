<#
.SYNOPSIS
    DataBridge - startet ALLES mit einem Befehl; Strg+C faehrt alles wieder herunter.

    Reihenfolge:
      1. Abhaengigkeiten sicherstellen (pip install -r requirements.txt, falls noetig)
      2. Docker pruefen - laeuft er nicht, Docker Desktop starten und warten
      3. Triple-Store (Fuseki / graph-db) starten und auf Bereitschaft warten
      4. Wissensnetz initialisieren (Dataset + TBox + Vokabulare (Rueckkanal, Auswahl))
      5. Mediator (FastAPI) als Container starten (docker compose, enthaelt
         gdc-client) und auf /health warten
      6. EINEN Demo-Scope ueber POST /selection/preview abrufen - der Store
         waechst mit den Aufrufen (ADR-0003), es wird NICHT mehr global
         vorgeladen. Vorlage: scripts/selection_demo.json
      6b. NUR mit -WithGraphView: Graph-Visualisierung (pyvis, graph_view.html)
          erzeugen und oeffnen
      7. NUR mit -WithUi: eigene Auswahl-Oberflaeche (frontend/, PySide6) starten,
         bzw. NUR mit -WithMpLite: Oviedo-Prototyp MP-lite (Bokeh)

    Der Standardstart oeffnet KEINE Oberflaeche. Er bringt nur die Dienste hoch,
    fuehrt den Demo-Scope aus, gibt eine Uebersicht aus und beendet sich; die
    Dienste laufen weiter. Die eigene Auswahl-Oberflaeche (-WithUi), MP-Lite
    (-WithMpLite) und die pyvis-Ansicht (-WithGraphView) sind alle Opt-in.

    Schritt 6 kennt drei Betriebsarten:
      Standard      ein Scope ueber /selection/preview (-DemoCohort/-DemoSize)
      -DemoGenerate wie Standard, aber /selection/generate mit Rohdaten-Download
                    und .h5ad nach wissensnetz\data\selection_demo.h5ad
      -FullLoad     ALTWEG vor ADR-0003: load_gdc.py --pancancer plus
                    fetch_pancancer_h5ad.py, fuellt den Store global
      -SkipLoad     gar kein Abruf; der Store bleibt leer (nur TBox+Vokabulare)

    Herunterfahren: .\stop_all.ps1 - im Standardfall der einzige Weg, denn das
    Skript beendet sich nach dem Start und die Dienste laufen weiter.
    NUR mit -WithMpLite laeuft Bokeh im Vordergrund; dann stoppt Strg+C in diesem
    Fenster die Oberflaeche, faehrt Mediator und graph-db herunter und schliesst
    das Fenster.

.NOTES
    Voraussetzung: aktivierte Conda-Env "F+E"  (conda activate F+E).
    Das Fenster-Schliessen per Strg+C betrifft nur -WithMpLite (Bokeh im
    Vordergrund). Am zuverlaessigsten klappt es, wenn du das Skript direkt in der
    aktivierten Session startest:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
        .\start_all.ps1 -WithMpLite
    Ohne -WithMpLite beendet sich das Skript von selbst; die Dienste laufen
    weiter, bis .\stop_all.ps1 sie stoppt.

.EXAMPLE
    # Standard: ein Demo-Scope (TCGA-BRCA, 20 Proben) ueber /selection/preview
    .\start_all.ps1
.EXAMPLE
    # anderer Scope
    .\start_all.ps1 -DemoCohort TCGA-KIRC -DemoSize 50
.EXAMPLE
    # mit Rohdaten und .h5ad; MP-lite zeigt danach selection_demo.h5ad
    .\start_all.ps1 -DemoGenerate
.EXAMPLE
    # nur die Dienste, leerer Store, keine Oberflaeche
    .\start_all.ps1 -SkipLoad
.EXAMPLE
    # eigene Auswahl-Oberflaeche mitstarten (PySide6-Fenster, ADR-0004)
    .\start_all.ps1 -WithUi
.EXAMPLE
    # Oviedo-Prototyp MP-lite mitstarten (Bokeh im Vordergrund, Browser oeffnet sich)
    .\start_all.ps1 -WithMpLite
.EXAMPLE
    # pyvis-Diagnoseansicht erzeugen und oeffnen, ohne MP-lite
    .\start_all.ps1 -WithGraphView
.EXAMPLE
    # ALTWEG vor ADR-0003: alle 32 Kohorten laden + globales pancancer.h5ad
    .\start_all.ps1 -FullLoad -Size 50 -PancancerSize 5
.EXAMPLE
    .\start_all.ps1 -RebuildMediator
#>
[CmdletBinding()]
param(
    [int]$Size = 50,                    # nur mit -FullLoad wirksam (Faelle je Kohorte)
    [int]$MediatorPort = 8000,
    [int]$UiPort = 5006,
    [switch]$SkipInstall,
    [switch]$SkipLoad,
    [int]$PancancerSize = 5,            # nur mit -FullLoad wirksam (Proben je Kohorte)
    [switch]$RebuildMediator,
    [switch]$NoUi,                      # wirkungslos: kein Start oeffnet mehr eine Oberflaeche
    [string]$DemoCohort = "TCGA-BRCA",  # Kohorte des Demo-Scopes (ADR-0003)
    [int]$DemoSize = 20,                # Proben im Demo-Scope
    [switch]$DemoGenerate,              # /selection/generate statt /preview (mit .h5ad)
    [switch]$FullLoad,                  # ALTWEG vor ADR-0003 (global vorladen)
    [switch]$WithMpLite,                # Oviedo-Prototyp MP-Lite starten (Bokeh, oeffnet Browser)
    [switch]$WithGraphView,             # pyvis-Diagnoseansicht erzeugen und oeffnen
    [switch]$WithUi                     # eigene Auswahl-Oberflaeche starten (frontend/, ADR-0004)
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot   # = Projekt-Root (dort wo dieses Skript liegt)

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function Step($m) { Write-Host "-> $m" -ForegroundColor Yellow }
function Good($m) { Write-Host "   OK: $m" -ForegroundColor Green }
function Fail($m) { Write-Host "   FEHLER: $m" -ForegroundColor Red }

function Wait-Url([string]$Url, [int]$TimeoutSec = 90) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try { Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true }
        catch { Start-Sleep -Seconds 2; Write-Host "." -NoNewline }
    }
    return $false
}

function Stop-PortProcess([int]$Port) {
    try {
        $ids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
               Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    } catch { }
}

function Stop-All {
    Write-Host ""
    Info "Fahre alles herunter ..."
    # Mediator NICHT per Port-Kill stoppen: er laeuft jetzt im Container, und der
    # Host-Port 8000 gehoert Docker Desktops Port-Weiterleitung - ein Force-Kill
    # darauf wuerde Docker Desktop selbst beenden. "docker compose down" stoppt
    # Mediator + graph-db sauber. Nur der Bokeh-Server ist ein Host-Prozess.
    Stop-PortProcess $UiPort            # Bokeh-Server (Host-Prozess, falls aktiv)
    docker compose down *> $null
    Good "Alles gestoppt (Mediator, graph-db, Oberflaeche)."
}

Info "==================  DataBridge - Start  =================="
Info "Projekt-Root: $PSScriptRoot"

# --- 1) Abhaengigkeiten -----------------------------------------------------
if (-not $SkipInstall) {
    $need = $false
    if (-not (Get-Command wissensnetz -ErrorAction SilentlyContinue)) { $need = $true }
    python -c "import bokeh, pyvis, requests, rdflib" *> $null
    if ($LASTEXITCODE -ne 0) { $need = $true }
    if ($need) {
        Step "Installiere/aktualisiere Abhaengigkeiten (pip install -r requirements.txt) ..."
        pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen."; exit 1 }
        Good "Abhaengigkeiten installiert."
    } else {
        Good "Abhaengigkeiten vorhanden."
    }
}

# --- 2) Docker pruefen / starten -------------------------------------------
Step "Pruefe Docker-Engine ..."
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Step "Docker laeuft nicht - versuche Docker Desktop zu starten ..."
    $dd = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) {
        Start-Process $dd | Out-Null
    } else {
        Fail "Docker Desktop nicht unter '$dd' gefunden. Bitte manuell starten und erneut ausfuehren."
        exit 1
    }
    Write-Host "   Warte auf Docker-Engine " -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 3; Write-Host "." -NoNewline
    }
    Write-Host ""
    if (-not $ready) { Fail "Docker-Engine nicht bereit (Timeout)."; exit 1 }
}
Good "Docker laeuft."

# --- 3) Fuseki (graph-db) starten ------------------------------------------
Step "Starte Triple-Store (graph-db) ..."
docker compose up -d graph-db
if ($LASTEXITCODE -ne 0) { Fail "docker compose up graph-db fehlgeschlagen."; exit 1 }
Write-Host "   Warte auf Fuseki " -NoNewline
if (-not (Wait-Url 'http://localhost:3030/$/ping' 90)) { Write-Host ""; Fail "Fuseki nicht erreichbar (Timeout)."; exit 1 }
Write-Host ""
Good "Fuseki bereit (http://localhost:3030, Login admin/admin)."

# --- 4) Wissensnetz initialisieren -----------------------------------------
Step "Initialisiere Wissensnetz (Dataset + TBox + Vokabulare (Rueckkanal, Auswahl)) ..."
wissensnetz init
if ($LASTEXITCODE -ne 0) { Fail "wissensnetz init fehlgeschlagen."; Stop-All; exit 1 }
Good "Wissensnetz initialisiert."

# --- 5) Mediator starten (Container - bringt gdc-client aus mediator/Dockerfile mit) ---
# Bewusst als Container (nicht Host-uvicorn): nur so ist `gdc-client` fuer den
# Bulk-Download der Expressions-Rohdaten (POST /export/anndata) verfuegbar. Auf
# Windows gibt es dafuer kein conda-Paket; das Linux-Image installiert es per
# bioconda. Der Container erreicht Fuseki ueber graph-db:3030 (Compose-Netzwerk).
$medHealth = "http://localhost:$MediatorPort/health"
$medUp = $false
try { Invoke-WebRequest $medHealth -UseBasicParsing -TimeoutSec 2 | Out-Null; $medUp = $true } catch { $medUp = $false }
if ($medUp) {
    Good "Mediator laeuft bereits ($medHealth)."
} else {
    $env:MEDIATOR_PORT = "$MediatorPort"   # Port-Mapping in docker-compose.yml (${MEDIATOR_PORT:-8000})
    if ($RebuildMediator) {
        Step "Baue Mediator-Container NEU (-RebuildMediator) - dauert einige Minuten ..."
        docker compose up -d --build mediator
    } else {
        Step "Starte Mediator-Container (vorhandenes Image; baut nur beim ersten Mal automatisch). -RebuildMediator erzwingt Neubau ..."
        docker compose up -d mediator
    }
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up mediator fehlgeschlagen."; Stop-All; exit 1 }
    Write-Host "   Warte auf Mediator " -NoNewline
    if (-not (Wait-Url $medHealth 120)) { Write-Host ""; Fail "Mediator nicht erreichbar (Timeout) - 'docker compose logs mediator' pruefen."; Stop-All; exit 1 }
    Write-Host ""
    Good "Mediator bereit ($medHealth) - Container mit gdc-client."
}

# --- 6) Daten abrufen ------------------------------------------------------
# Seit ADR-0003 startet der Store LEER und waechst mit den Aufrufen: der
# Standardweg laedt EINEN Scope ueber POST /selection/preview, nicht mehr alle 32
# Kohorten. Nur das macht den Abnahmetest aus HANDOFF_pablo_store_waechst.md
# ueberhaupt moeglich (Schritt 6 dort: eine Auswahl sieht nur ihre eigenen Faelle).
# Der alte Vollweg bleibt unter -FullLoad erhalten.
$demoH5ad = $null

if ($SkipLoad -and $FullLoad) {
    Fail "-SkipLoad und -FullLoad schliessen sich aus - es wird nichts abgerufen (-SkipLoad gewinnt)."
}
if (-not $FullLoad -and ($PSBoundParameters.ContainsKey('Size') -or $PSBoundParameters.ContainsKey('PancancerSize'))) {
    Info "   Hinweis: -Size/-PancancerSize wirken nur mit -FullLoad und werden hier ignoriert."
    Info "            Der Demo-Scope nutzt -DemoCohort/-DemoSize."
}

if ($SkipLoad) {
    Good "Datenabruf uebersprungen (-SkipLoad). Der Store enthaelt nur TBox und Vokabulare."
    Info "   MP-lite faellt damit auf das BRCA-Fixture zurueck (mediator/sample_data)."
} elseif ($FullLoad) {
    Write-Host "   ACHTUNG: -FullLoad ist der Weg VOR ADR-0003. Er fuellt den Store GLOBAL" -ForegroundColor Magenta
    Write-Host "            (alle 32 Kohorten) und erzeugt ein globales pancancer.h5ad." -ForegroundColor Magenta
    Write-Host "            Der Abnahmetest 'eine Auswahl sieht nur ihre Faelle' ist danach" -ForegroundColor Magenta
    Write-Host "            nicht mehr aussagekraeftig. Regulaer: ohne -FullLoad starten." -ForegroundColor Magenta

    Step "ALTWEG: Lade ALLE Oviedo-Kohorten aus GDC ins Wissensnetz (Pancancer, size=$Size je Kohorte) ..."
    python scripts\load_gdc.py --pancancer --size $Size --mediator-url "http://localhost:$MediatorPort"
    if ($LASTEXITCODE -ne 0) { Fail "GDC-Load fehlgeschlagen (Beispieldaten bleiben nutzbar)." }
    else { Good "GDC-Daten geladen (alle Kohorten)." }

    # Erzeugt wissensnetz/data/pancancer.h5ad ueber POST /export/anndata; MP-lite
    # bevorzugt die Datei danach automatisch. Braucht den Mediator-Container mit
    # gdc-client (Schritt 5) und ein gefuelltes Fuseki. Bei project_id als Liste
    # gilt --size PRO Kohorte, daher -PancancerSize = Proben je Kohorte.
    Step "ALTWEG: Rufe Pancancer-Expressions-.h5ad ab (fetch_pancancer_h5ad.py --size $PancancerSize) ..."
    python scripts\fetch_pancancer_h5ad.py --size $PancancerSize --mediator-url "http://localhost:$MediatorPort"
    if ($LASTEXITCODE -ne 0) { Fail "Pancancer-Abruf fehlgeschlagen (MP-lite bleibt beim BRCA-Fixture)." }
    else { Good "pancancer.h5ad erzeugt - MP-lite bevorzugt sie automatisch." }
} else {
    # Vorlage nur in cohorts/size anpassen - alles andere (Modalitaet, Attribute)
    # bleibt so, wie es in der versionierten Referenz-Auswahl steht.
    $demoTemplate = Join-Path $PSScriptRoot "scripts\selection_demo.json"
    $tmpJson = Join-Path ([System.IO.Path]::GetTempPath()) "databridge_selection_$PID.json"
    try {
        $sel = Get-Content -Raw -Encoding UTF8 $demoTemplate | ConvertFrom-Json
        $sel.levels[0].cohorts = @($DemoCohort)
        $sel.size = $DemoSize
        # Kein Out-File: Windows PowerShell 5.1 schreibt dort UTF-8 MIT BOM,
        # und ein BOM ist in JSON nicht erlaubt.
        [System.IO.File]::WriteAllText($tmpJson, ($sel | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))

        $mode = if ($DemoGenerate) { "generate (mit Rohdaten und .h5ad)" } else { "preview (nur Metadaten)" }
        Step "Lade EINEN Scope ins Wissensnetz: $DemoCohort, $DemoSize Proben - $mode ..."
        if ($DemoGenerate) {
            $demoH5ad = Join-Path $PSScriptRoot "wissensnetz\data\selection_demo.h5ad"
            python scripts\run_selection.py $tmpJson --mediator-url "http://localhost:$MediatorPort" --generate --out "wissensnetz\data\selection_demo.h5ad"
        } else {
            python scripts\run_selection.py $tmpJson --mediator-url "http://localhost:$MediatorPort"
        }
        if ($LASTEXITCODE -ne 0) {
            Fail "Auswahl-Abruf fehlgeschlagen (MP-lite faellt auf das BRCA-Fixture zurueck)."
            $demoH5ad = $null
        } else {
            Good "Scope geladen - der Store enthaelt jetzt genau diese Auswahl."
            Info "   Pruefen mit:  wissensnetz selections   bzw.  wissensnetz selection <recipe_key>"
        }
    } catch {
        Fail "Demo-Auswahl konnte nicht vorbereitet werden: $($_.Exception.Message)"
        $demoH5ad = $null
    } finally {
        Remove-Item $tmpJson -ErrorAction SilentlyContinue
    }
}

# --- 6a) .h5ad an MP-lite uebergeben ---------------------------------------
# Vorgesehene Schnittstelle (h5ad_source.resolve_h5ad_path): explizites Argument,
# dann DATABRIDGE_H5AD, dann pancancer.h5ad, dann das BRCA-Fixture. Kein Eingriff
# in app.py noetig. Ohne -DemoGenerate wird die Variable NICHT gesetzt.
if ($demoH5ad -and (Test-Path $demoH5ad)) {
    $env:DATABRIDGE_H5AD = (Resolve-Path $demoH5ad).Path
    Good "MP-lite nutzt selection_demo.h5ad (DATABRIDGE_H5AD gesetzt)."
} elseif (-not $FullLoad) {
    $stalePancancer = Join-Path $PSScriptRoot "wissensnetz\data\pancancer.h5ad"
    if (Test-Path $stalePancancer) {
        Info "   Hinweis: wissensnetz\data\pancancer.h5ad liegt noch aus einem frueheren Lauf herum."
        Info "            MP-lite zieht sie dem Fixture weiterhin vor. Fuer den Auswahl-Scope"
        Info "            entweder mit -DemoGenerate starten oder die Datei wegraeumen."
    }
}

# --- 6b) Wissensnetz visualisieren (pyvis) ---------------------------------
# Diagnosewerkzeug, kein Teil des Starts: nur mit -WithGraphView. Die Datei in der
# Projektwurzel wird dadurch nur noch auf Anforderung neu erzeugt und ist sonst
# potenziell veraltet.
if ($WithGraphView -and -not $NoUi) {
    Step "Erzeuge Graph-Visualisierung (pyvis, graph_view.html) ..."
    python scripts\graph_view.py --limit 500
    if ($LASTEXITCODE -ne 0) { Fail "Graph-Visualisierung fehlgeschlagen (nicht kritisch)." }
    else { Good "graph_view.html geoeffnet." }
}

# --- 7) Oberflaeche ---------------------------------------------------------
# Die eigene Auswahl-Oberflaeche liegt in frontend/ (PySide6, ADR-0004) und
# startet mit -WithUi als Host-Prozess in der Env F+E, nicht im Container.
# MP-Lite ist der Oviedo-Prototyp und startet nur mit -WithMpLite. Ohne Schalter
# oeffnet der Start weiterhin nichts.
if ($NoUi -and ($WithUi -or $WithMpLite -or $WithGraphView)) {
    Info "   Hinweis: -NoUi schlaegt -WithUi/-WithMpLite/-WithGraphView - es wird keine Oberflaeche gestartet."
} elseif ($NoUi) {
    Info "   Hinweis: -NoUi ist nicht mehr noetig - der Start oeffnet ohnehin keine Oberflaeche."
}

if ($WithUi -and -not $NoUi) {
    Step "Starte Auswahl-Oberflaeche (frontend/app.py) ..."
    $env:MEDIATOR_URL = "http://localhost:$MediatorPort"
    python frontend\app.py
    if ($LASTEXITCODE -ne 0) { Fail "Oberflaeche beendet sich mit Fehler (Dienste laufen weiter)." }
    else { Good "Oberflaeche beendet." }
}

if ($WithMpLite -and -not $NoUi) {
    Info "Starte Oberflaeche (MP-lite) auf Port $UiPort - Browser oeffnet sich."
    Info "Strg+C beendet ALLES (Mediator, Docker, Oberflaeche) und schliesst dieses Fenster."
    try {
        bokeh serve --show --port $UiPort wissensnetz\prototype\mp_lite\app.py
    } finally {
        Stop-All
    }
    # Fenster schliessen (wirkt, wenn das Skript dieses Fenster besitzt; sonst zurueck zum Prompt)
    Stop-Process -Id $PID -Force
}

# Standardfall: keine Oberflaeche. Dienste laufen weiter, kurze Uebersicht.
Write-Host ""
Info "==================  Fertig - Dienste laufen  =================="
Info "  Fuseki:            http://localhost:3030            (Login admin/admin)"
Info "  Mediator:          http://localhost:$MediatorPort/health   und   /docs"
Info ""
Info "  Auswahl ausfuehren:  python scripts\run_selection.py <selection.json>"
Info "  Auswahlen ansehen:   wissensnetz selections"
Info "  Oberflaeche:         .\start_all.ps1 -WithUi        (oder: python frontend\app.py)"
Info "  MP-Lite bei Bedarf:  .\start_all.ps1 -WithMpLite"
Info "  Herunterfahren:      .\stop_all.ps1"
exit 0
