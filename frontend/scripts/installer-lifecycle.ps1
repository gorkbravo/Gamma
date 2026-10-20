<#
.SYNOPSIS
  Prueba el ciclo de vida del instalador NSIS de Gamma: instalar, arrancar, reinstalar encima y desinstalar.

.DESCRIPTION
  Pensado para una máquina desechable (runner de GitHub Actions, máquina virtual o cuenta de
  Windows de pruebas): instala Gamma para el usuario actual y lo desinstala al final. No lo
  ejecutes en tu equipo de trabajo si no quieres que Gamma se instale ahí.

  Comprobaciones obligatorias (fallan el script):
    - el instalador silencioso (/S) termina con código 0 y registra la desinstalación;
    - la instalación contiene el backend empaquetado;
    - la app instalada arranca el backend empaquetado (log del backend) y carga la ventana
      principal (marcador GAMMA_DESKTOP_SMOKE_FILE);
    - al cerrarse la app no quedan procesos gamma-backend;
    - reinstalar encima conserva los datos de la app y vuelve a arrancar;
    - la desinstalación silenciosa borra la carpeta de instalación y la entrada del registro.
  Informativas: accesos directos y datos de la app que quedan tras desinstalar.

.PARAMETER InstallerPath
  Ruta del instalador. Por defecto, el único Gamma_*-setup.exe de src-tauri/target/release/bundle/nsis.

.PARAMETER OutputDir
  Carpeta donde se copian los logs de la app y el resumen (summary.md).
#>
param(
    [string]$InstallerPath = "",
    [string]$OutputDir = (Join-Path ([System.IO.Path]::GetTempPath()) "gamma-installer-lifecycle")
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Split-Path -Parent $scriptDir
$appDataDir = Join-Path $env:APPDATA "com.gamma.shell\runtime"
$results = New-Object System.Collections.Generic.List[object]

function Add-Result([string]$Check, [bool]$Passed, [string]$Detail, [bool]$Required = $true) {
    $results.Add([pscustomobject]@{ Check = $Check; Passed = $Passed; Required = $Required; Detail = $Detail })
    $state = if ($Passed) { "ok  " } elseif ($Required) { "FAIL" } else { "info" }
    Write-Host "[$state] $Check - $Detail"
}

function Find-UninstallEntry {
    $roots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($root in $roots) {
        $entry = Get-ItemProperty $root -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq "Gamma" } | Select-Object -First 1
        if ($entry) { return $entry }
    }
    return $null
}

function Get-InstallDir($entry) {
    if ($entry.InstallLocation) { return $entry.InstallLocation.Trim('"') }
    $uninstaller = ($entry.UninstallString -replace '"', '').Trim()
    return Split-Path -Parent $uninstaller
}

function Save-Logs([string]$Phase) {
    $target = Join-Path $OutputDir "logs-$Phase"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $logDir = Join-Path $appDataDir "logs"
    if (Test-Path $logDir) { Copy-Item -Path (Join-Path $logDir "*") -Destination $target -Force -ErrorAction SilentlyContinue }
}

function Stop-GammaProcesses([string]$ShellExe) {
    Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $ShellExe -or $_.ProcessName -eq "gamma-backend" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Invoke-InstalledSmoke([string]$ShellExe, [string]$Phase) {
    $marker = Join-Path $OutputDir "smoke-$Phase.json"
    Remove-Item $marker -Force -ErrorAction SilentlyContinue
    # El shell instalado escribe el marcador al cargar la ventana principal y se cierra solo.
    $env:GAMMA_DESKTOP_SMOKE_FILE = $marker
    try {
        $process = Start-Process -FilePath $ShellExe -PassThru
        $deadline = (Get-Date).AddSeconds(150)
        while ((Get-Date) -lt $deadline -and -not (Test-Path $marker) -and -not $process.HasExited) {
            Start-Sleep -Milliseconds 500
        }
        Start-Sleep -Seconds 2
        $markerOk = $false
        $markerDetail = "no marker: the main window did not load"
        if (Test-Path $marker) {
            $payload = Get-Content $marker -Raw | ConvertFrom-Json
            $markerOk = ($payload.status -eq "ok" -and $payload.window -eq "main")
            $markerDetail = "main window loaded; API $($payload.apiBase)"
        }
        if (-not $process.HasExited) { $process.WaitForExit(15000) | Out-Null }
        if (-not $process.HasExited) { Stop-GammaProcesses $ShellExe }

        $logText = ""
        foreach ($name in @("backend-stdout.log", "backend-stderr.log")) {
            $path = Join-Path $appDataDir "logs\$name"
            if (Test-Path $path) { $logText += (Get-Content $path -Raw -ErrorAction SilentlyContinue) }
        }
        $shellFailure = Join-Path $appDataDir "logs\shell-startup-failure.txt"
        $failureText = if (Test-Path $shellFailure) { (Get-Content $shellFailure -Raw).Trim() } else { "" }
        $backendStarted = $logText -match "Starting Gamma desktop backend"
        $backendDetail = if ($backendStarted) { "packaged backend started" } elseif ($failureText) { "shell startup failure: $failureText" } else { "no backend start in the logs" }
        Add-Result "$Phase - backend starts from the install" $backendStarted $backendDetail
        Add-Result "$Phase - main window loads" $markerOk $markerDetail

        Start-Sleep -Seconds 5
        $leftover = @(Get-Process -Name "gamma-backend" -ErrorAction SilentlyContinue)
        Add-Result "$Phase - no backend left running after exit" ($leftover.Count -eq 0) "$($leftover.Count) gamma-backend process(es) left"
        Stop-GammaProcesses $ShellExe
    } finally {
        Remove-Item Env:\GAMMA_DESKTOP_SMOKE_FILE -ErrorAction SilentlyContinue
        Save-Logs $Phase
    }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
if (-not $InstallerPath) {
    $bundleDir = Join-Path $frontendDir "src-tauri\target\release\bundle\nsis"
    $candidates = @(Get-ChildItem -Path $bundleDir -Filter "Gamma_*-setup.exe" -File -ErrorAction SilentlyContinue)
    if ($candidates.Count -ne 1) { throw "Expected exactly one Gamma_*-setup.exe in $bundleDir, found $($candidates.Count)." }
    $InstallerPath = $candidates[0].FullName
}
if (Find-UninstallEntry) { throw "Gamma is already installed on this machine; run this only on a disposable machine or account." }
Write-Host "Installer: $InstallerPath"

# 1. Instalación silenciosa.
$install = Start-Process -FilePath $InstallerPath -ArgumentList "/S" -Wait -PassThru
$entry = Find-UninstallEntry
Add-Result "install - silent installer exits 0" ($install.ExitCode -eq 0) "exit code $($install.ExitCode)"
Add-Result "install - uninstall entry registered" ($null -ne $entry) $(if ($entry) { $entry.PSPath -replace '^.*::', '' } else { "no uninstall entry named Gamma" })
if (-not $entry) { throw "Installation did not register Gamma; stopping." }
$installDir = Get-InstallDir $entry
$shellExe = Get-ChildItem -Path $installDir -Filter "*.exe" -File | Where-Object { $_.Name -notmatch "^uninstall" } | Select-Object -First 1
Add-Result "install - shell executable present" ($null -ne $shellExe) $(if ($shellExe) { $shellExe.FullName } else { "no shell exe in $installDir" })
$backendCandidates = @(
    (Join-Path $installDir "resources\backend\gamma-backend\gamma-backend.exe"),
    (Join-Path $installDir "backend\gamma-backend\gamma-backend.exe")
)
$backendExe = $backendCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
Add-Result "install - packaged backend present" ($null -ne $backendExe) $(if ($backendExe) { $backendExe } else { "not found under $installDir" })
if (-not $shellExe) { throw "No shell executable installed; stopping." }

# 2. Primer arranque de la app instalada (carpeta de datos real: %APPDATA%\com.gamma.shell\runtime).
Invoke-InstalledSmoke $shellExe.FullName "first-run"

# 3. Reinstalar encima: los datos de la app deben sobrevivir y la app debe volver a arrancar.
$sentinel = Join-Path $appDataDir "data\installer-lifecycle-sentinel.txt"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sentinel) | Out-Null
Set-Content -Path $sentinel -Value "kept across reinstall" -Encoding utf8
$reinstall = Start-Process -FilePath $InstallerPath -ArgumentList "/S" -Wait -PassThru
Add-Result "reinstall - silent installer exits 0" ($reinstall.ExitCode -eq 0) "exit code $($reinstall.ExitCode)"
Add-Result "reinstall - app data preserved" (Test-Path $sentinel) $sentinel
Invoke-InstalledSmoke $shellExe.FullName "reinstall"

# 4. Desinstalación silenciosa. El desinstalador NSIS se copia a TEMP y el proceso original vuelve
#    enseguida, así que se espera a que desaparezca la carpeta de instalación.
$entry = Find-UninstallEntry
$uninstaller = ($entry.UninstallString -replace '"', '').Trim()
Start-Process -FilePath $uninstaller -ArgumentList "/S" -Wait | Out-Null
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline -and ((Test-Path $installDir) -or (Find-UninstallEntry))) { Start-Sleep -Seconds 1 }
Add-Result "uninstall - install folder removed" (-not (Test-Path $installDir)) $installDir
Add-Result "uninstall - uninstall entry removed" ($null -eq (Find-UninstallEntry)) "registry"
$shortcuts = @(@(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Gamma.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Gamma.lnk")
) | Where-Object { Test-Path $_ })
Add-Result "uninstall - shortcuts removed" ($shortcuts.Count -eq 0) $(if ($shortcuts.Count) { $shortcuts -join ", " } else { "none left" }) $false
$appDataLeft = Test-Path $appDataDir
Add-Result "uninstall - app data kept" $appDataLeft $(if ($appDataLeft) { "kept at $appDataDir (user data survives uninstall)" } else { "removed" }) $false

# Resumen (también en el resumen del job de GitHub Actions si existe).
$lines = @("## Gamma installer lifecycle", "", "Installer: ``$(Split-Path -Leaf $InstallerPath)``", "", "| Check | Result | Detail |", "| --- | --- | --- |")
foreach ($result in $results) {
    $label = if ($result.Passed) { "pass" } elseif ($result.Required) { "**FAIL**" } else { "info" }
    $lines += "| $($result.Check) | $label | $($result.Detail -replace '\|', '/') |"
}
$summary = $lines -join "`n"
Set-Content -Path (Join-Path $OutputDir "summary.md") -Value $summary -Encoding utf8
if ($env:GITHUB_STEP_SUMMARY) { Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $summary -Encoding utf8 }

$failed = @($results | Where-Object { $_.Required -and -not $_.Passed })
if ($failed.Count -gt 0) {
    Write-Host "Installer lifecycle failed: $($failed.Count) required check(s)."
    exit 1
}
Write-Host "Installer lifecycle passed."
