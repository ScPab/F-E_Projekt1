<#
.SYNOPSIS
    DataBridge - faehrt alle Dienste herunter (Mediator, Bokeh-Oberflaeche, graph-db/Docker).
    Nuetzlich, wenn start_all.ps1 mit -NoUi lief oder unsauber beendet wurde.

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

Write-Host "Stoppe DataBridge-Dienste ..." -ForegroundColor Yellow
Stop-PortProcess $MediatorPort      # Mediator (uvicorn)
Stop-PortProcess $UiPort            # Bokeh-Oberflaeche
docker compose down
Write-Host "Alles gestoppt (Mediator, Oberflaeche, graph-db)." -ForegroundColor Green
