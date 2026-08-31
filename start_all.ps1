<#
.SYNOPSIS
    DataBridge - startet ALLES mit einem Befehl; Strg+C faehrt alles wieder herunter.

    Reihenfolge:
      1. Abhaengigkeiten sicherstellen (pip install -r requirements.txt, falls noetig)
      2. Docker pruefen - laeuft er nicht, Docker Desktop starten und warten
      3. Triple-Store (Fuseki / graph-db) starten und auf Bereitschaft warten
      4. Wissensnetz initialisieren (Dataset + TBox + Rueckkanal-Vokabular)
      5. Mediator (FastAPI) als Container starten (docker compose, enthaelt
         gdc-client) und auf /health warten
      6. Alle Oviedo-Kohorten (Pancancer) ueber die API abrufen und ins
         Wissensnetz laden - Basis fuer die Kohorten-Faerbung der obs
      6c. Pancancer-Expressions-.h5ad ueber den Mediator-Export abrufen
          (wissensnetz/data/pancancer.h5ad -> MP-lite bevorzugt sie automatisch)
      6b. Graph-Visualisierung (pyvis, graph_view.html) erzeugen und oeffnen
      7. Oberflaeche (MP-lite, Bokeh) starten - Browser oeffnet sich

    Strg+C in diesem Fenster stoppt die Oberflaeche und faehrt danach automatisch
    Mediator, graph-db (Docker) und die Oberflaeche herunter - und schliesst dieses
    Fenster. Manuelles Herunterfahren: .\stop_all.ps1

.NOTES
    Voraussetzung: aktivierte Conda-Env "F+E"  (conda activate F+E).
    Am zuverlaessigsten schliesst sich das Fenster, wenn du das Skript direkt in
    der aktivierten Session startest:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
        .\start_all.ps1

.EXAMPLE
    .\start_all.ps1
.EXAMPLE
    .\start_all.ps1 -Size 100
.EXAMPLE
    .\start_all.ps1 -SkipLoad -NoUi
.EXAMPLE
    .\start_all.ps1 -PancancerSize 80
#>
[CmdletBinding()]
param(
    [int]$Size = 50,
    [int]$MediatorPort = 8000,
    [int]$UiPort = 5006,
    [switch]$SkipInstall,
    [switch]$SkipLoad,
    [int]$PancancerSize = 40,
    [switch]$NoUi
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
    Stop-PortProcess $MediatorPort      # Mediator (uvicorn) + dessen Fenster
    Stop-PortProcess $UiPort            # Bokeh-Server (falls noch aktiv)
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
Step "Initialisiere Wissensnetz (Dataset + TBox + Rueckkanal-Vokabular) ..."
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
    Step "Baue/starte Mediator-Container (docker compose up -d --build mediator) - erster Build dauert einige Minuten ..."
    $env:MEDIATOR_PORT = "$MediatorPort"   # Port-Mapping in docker-compose.yml (${MEDIATOR_PORT:-8000})
    docker compose up -d --build mediator
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up mediator fehlgeschlagen."; Stop-All; exit 1 }
    Write-Host "   Warte auf Mediator " -NoNewline
    if (-not (Wait-Url $medHealth 120)) { Write-Host ""; Fail "Mediator nicht erreichbar (Timeout) - 'docker compose logs mediator' pruefen."; Stop-All; exit 1 }
    Write-Host ""
    Good "Mediator bereit ($medHealth) - Container mit gdc-client."
}

# --- 6) TCGA/GDC-Daten abrufen und laden -----------------------------------
if ($SkipLoad) {
    Good "GDC-Datenabruf uebersprungen (-SkipLoad)."
} else {
    Step "Lade ALLE Oviedo-Kohorten aus GDC ins Wissensnetz (Pancancer, size=$Size je Kohorte) - Basis der Kohorten-Faerbung ..."
    python scripts\load_gdc.py --pancancer --size $Size --mediator-url "http://localhost:$MediatorPort"
    if ($LASTEXITCODE -ne 0) { Fail "GDC-Load fehlgeschlagen (Beispieldaten bleiben nutzbar)." }
    else { Good "GDC-Daten geladen (alle Kohorten)." }
}

# --- 6c) Pancancer-Expressions-.h5ad abrufen (fester Pipeline-Schritt) ------
# Erzeugt wissensnetz/data/pancancer.h5ad ueber POST /export/anndata; MP-lite
# bevorzugt die Datei danach automatisch (echte Gene-Expression-Karte statt
# BRCA-Fixture). Braucht den Mediator-Container mit gdc-client (Schritt 5) und
# ein gefuelltes Fuseki (Schritt 6). Grosse RNA-Seq-Downloads dauern - -PancancerSize
# steuert die Probenzahl (Default 40). Bei -SkipLoad ausgelassen (keine Daten laden).
if (-not $SkipLoad) {
    Step "Rufe Pancancer-Expressions-.h5ad ab (fetch_pancancer_h5ad.py --size $PancancerSize) ..."
    python scripts\fetch_pancancer_h5ad.py --size $PancancerSize --mediator-url "http://localhost:$MediatorPort"
    if ($LASTEXITCODE -ne 0) { Fail "Pancancer-Abruf fehlgeschlagen (MP-lite bleibt beim BRCA-Fixture)." }
    else { Good "pancancer.h5ad erzeugt - MP-lite bevorzugt sie automatisch." }
}

# --- 6b) Wissensnetz visualisieren (pyvis) ---------------------------------
if (-not $NoUi) {
    Step "Erzeuge Graph-Visualisierung (pyvis, graph_view.html) ..."
    python scripts\graph_view.py --limit 500
    if ($LASTEXITCODE -ne 0) { Fail "Graph-Visualisierung fehlgeschlagen (nicht kritisch)." }
    else { Good "graph_view.html geoeffnet." }
}

# --- 7) Oberflaeche (MP-lite) starten --------------------------------------
if ($NoUi) {
    Info "Fertig. Dienste laufen weiter. Herunterfahren mit:  .\stop_all.ps1"
    exit 0
}

Info "Starte Oberflaeche (MP-lite) auf Port $UiPort - Browser oeffnet sich."
Info "Strg+C beendet ALLES (Mediator, Docker, Oberflaeche) und schliesst dieses Fenster."
try {
    bokeh serve --show --port $UiPort wissensnetz\prototype\mp_lite\app.py
} finally {
    Stop-All
}

# Fenster schliessen (wirkt, wenn das Skript dieses Fenster besitzt; sonst zurueck zum Prompt)
Stop-Process -Id $PID -Force
