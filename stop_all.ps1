<#
.SYNOPSIS
    DataBridge - faehrt alles herunter: Auswahl-Oberflaeche (frontend/app.py),
    Mediator, Bokeh-Oberflaeche und graph-db/Docker.
    Im Standardfall der vorgesehene Weg, denn start_all.ps1 beendet sich nach dem
    Start und laesst Dienste und Explorer weiterlaufen.

.EXAMPLE
    .\stop_all.ps1
#>
[CmdletBinding()]
param(
    [int]$MediatorPort = 8000,
    [int]$UiPort = 5006
)

Set-Location -Path $PSScriptRoot

function Stop-PortProcess([int]$Port) {
    try {
        $ids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
               Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    } catch { }
}

function Stop-Explorer {
    # Die Auswahl-Oberflaeche laeuft als abgekoppelter Host-Prozess und haengt an
    # keinem Port, laesst sich also nur ueber die Kommandozeile erkennen.
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*frontend*app.py*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch { }
}

Write-Host "Stoppe DataBridge-Dienste ..." -ForegroundColor Yellow
Stop-Explorer                       # DataBridge Explorer (frontend/app.py)
# Mediator laeuft im Container -> per "docker compose down" stoppen, NICHT per
# Port-Kill: Host-Port 8000 gehoert Docker Desktops Weiterleitung, ein Force-Kill
# darauf wuerde Docker Desktop selbst beenden.
Stop-PortProcess $UiPort            # Bokeh-Oberflaeche (Host-Prozess)
docker compose down
Write-Host "Alles gestoppt (Explorer, Mediator, MP-lite, graph-db)." -ForegroundColor Green
