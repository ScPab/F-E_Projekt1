<#
.SYNOPSIS
    DataBridge - startet ALLES mit einem Befehl; Strg+C faehrt alles wieder herunter.

    Reihenfolge:
      1. Abhaengigkeiten sicherstellen (pip install -r requirements.txt, falls noetig)
      2. Docker pruefen - laeuft er nicht, Docker Desktop starten und warten
      3. Triple-Store (Fuseki / graph-db) starten und auf Bereitschaft warten
      4. Wissensnetz initialisieren (Dataset + TBox + Rueckkanal-Vokabular)
      5. Mediator (FastAPI) in eigenem Fenster starten und auf /health warten
      6. TCGA/GDC-Daten ueber die API abrufen und ins Wissensnetz laden
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
    .\start_all.ps1 -Project TCGA-BRCA -Size 100
.EXAMPLE
    .\start_all.ps1 -SkipLoad -NoUi
#>
[CmdletBinding()]
param(
    [string]$Project = "TCGA-BRCA",
    [int]$Size = 50,
    [int]$MediatorPort = 8000,
    [int]$UiPort = 5006,
    [switch]$SkipInstall,
    [switch]$SkipLoad,
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
    if (Get-Command wissensnetz -ErrorAction SilentlyContinue) {
        Good "Abhaengigkeiten vorhanden (wissensnetz gefunden)."
    } else {
        Step "Installiere Abhaengigkeiten (pip install -r requirements.txt) ..."
        pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen."; exit 1 }
        Good "Abhaengigkeiten installiert."
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

# --- 5) Mediator starten (eigenes Fenster) ---------------------------------
$medHealth = "http://localhost:$MediatorPort/health"
$medUp = $false
try { Invoke-WebRequest $medHealth -UseBasicParsing -TimeoutSec 2 | Out-Null; $medUp = $true } catch { $medUp = $false }
if ($medUp) {
    Good "Mediator laeuft bereits ($medHealth)."
} else {
    Step "Starte Mediator (uvicorn, Port $MediatorPort) in neuem Fenster ..."
    $medDir = Join-Path $PSScriptRoot "mediator"
    Start-Process -FilePath "python" -ArgumentList @('-m','uvicorn','app.main:app','--port',"$MediatorPort") -WorkingDirectory $medDir | Out-Null
    Write-Host "   Warte auf Mediator " -NoNewline
    if (-not (Wait-Url $medHealth 90)) { Write-Host ""; Fail "Mediator nicht erreichbar (Timeout) - siehe Mediator-Fenster."; Stop-All; exit 1 }
    Write-Host ""
    Good "Mediator bereit ($medHealth)."
}

# --- 6) TCGA/GDC-Daten abrufen und laden -----------------------------------
if ($SkipLoad) {
    Good "GDC-Datenabruf uebersprungen (-SkipLoad)."
} else {
    Step "Lade $Project (size=$Size) aus GDC ins Wissensnetz ..."
    python scripts\load_gdc.py --project $Project --size $Size --mediator-url "http://localhost:$MediatorPort"
    if ($LASTEXITCODE -ne 0) { Fail "GDC-Load fehlgeschlagen (Beispieldaten bleiben nutzbar)." }
    else { Good "GDC-Daten geladen." }
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
