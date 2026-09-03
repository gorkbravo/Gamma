[CmdletBinding()]
param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$FrontendBase = "http://127.0.0.1:5173",
    [ValidateRange(1, 30)]
    [int]$TimeoutSeconds = 5,
    [string]$SessionToken = $env:GAMMA_SESSION_TOKEN
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-HttpStatusCode {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)

    try {
        return [int]$ErrorRecord.Exception.Response.StatusCode
    }
    catch {
        return $null
    }
}

function Invoke-SafeJsonGet {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [hashtable]$Headers = @{}
    )

    try {
        $data = Invoke-RestMethod -Uri $Uri -Method Get -Headers $Headers -TimeoutSec $TimeoutSeconds
        return [pscustomobject]@{
            ok = $true
            status_code = 200
            data = $data
            error_type = $null
        }
    }
    catch {
        return [pscustomobject]@{
            ok = $false
            status_code = Get-HttpStatusCode -ErrorRecord $_
            data = $null
            error_type = $_.Exception.GetType().Name
        }
    }
}

function Test-SafeHttpGet {
    param([Parameter(Mandatory = $true)][string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -Method Get -TimeoutSec $TimeoutSeconds -UseBasicParsing
        return [pscustomobject]@{
            ok = $true
            status_code = [int]$response.StatusCode
            error_type = $null
        }
    }
    catch {
        return [pscustomobject]@{
            ok = $false
            status_code = Get-HttpStatusCode -ErrorRecord $_
            error_type = $_.Exception.GetType().Name
        }
    }
}

function Test-Configured {
    param([AllowNull()][string]$Value)
    return -not [string]::IsNullOrWhiteSpace($Value)
}

function Get-SafeMode {
    param(
        [AllowNull()][string]$Value,
        [string[]]$Allowed
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "unset"
    }
    $normalized = $Value.Trim().ToLowerInvariant()
    if ($Allowed -contains $normalized) {
        return $normalized
    }
    return "set_nonstandard"
}

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\..\.."))
$apiRoot = $ApiBase.TrimEnd("/")
$frontendRoot = $FrontendBase.TrimEnd("/")

$gitAvailable = $false
$gitChangeCount = $null
$gitCommit = $null
$gitBranch = $null
try {
    $null = & git -C $repoRoot rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0) {
        $gitAvailable = $true
        $gitCommit = ((& git -C $repoRoot rev-parse HEAD 2>$null) | Out-String).Trim()
        $gitBranch = ((& git -C $repoRoot branch --show-current 2>$null) | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($gitBranch)) {
            $gitBranch = "detached"
        }
        $gitChanges = @(& git -C $repoRoot status --short 2>$null)
        if ($LASTEXITCODE -eq 0) {
            $gitChangeCount = $gitChanges.Count
        }
    }
}
catch {
    $gitAvailable = $false
}

$headers = @{}
if (Test-Configured -Value $SessionToken) {
    $headers["X-Gamma-Session"] = $SessionToken.Trim()
}

$healthProbe = Invoke-SafeJsonGet -Uri "$apiRoot/health"
$statusProbe = Invoke-SafeJsonGet -Uri "$apiRoot/system/status" -Headers $headers
$diagnosticsProbe = Invoke-SafeJsonGet -Uri "$apiRoot/diagnostics" -Headers $headers
$providerUsageProbe = Invoke-SafeJsonGet -Uri "$apiRoot/system/provider-usage?limit=0" -Headers $headers
$boundaryProbe = Invoke-SafeJsonGet -Uri "$apiRoot/system/read-only-boundary" -Headers $headers
$frontendProbe = Test-SafeHttpGet -Uri $frontendRoot

$runtimeStatus = $null
if ($statusProbe.ok) {
    $runtimeStatus = [ordered]@{
        mock_mode = [bool]$statusProbe.data.mock_mode
        market_data_mode = [string]$statusProbe.data.market_data_mode
        base_currency = [string]$statusProbe.data.base_currency
        ibkr_connected = [bool]$statusProbe.data.connection.connected
        ibkr_status = [string]$statusProbe.data.connection.status_text
        cached_symbol_count = @($statusProbe.data.cached_symbols).Count
    }
}

$auditModeGate = "diagnostic-only"
if ($null -ne $runtimeStatus) {
    if ($runtimeStatus.mock_mode) {
        $auditModeGate = "diagnostic-only"
    }
    elseif ($runtimeStatus.ibkr_connected) {
        $auditModeGate = "ibkr-integrated-candidate"
    }
    else {
        $auditModeGate = "provider-only-explicit-opt-in-required"
    }
}

$runtimeDiagnostics = $null
if ($diagnosticsProbe.ok) {
    $runtimeDiagnostics = [ordered]@{
        local_history_entries = [int]$diagnosticsProbe.data.local_history_entries
        recent_error_count = @($diagnosticsProbe.data.recent_errors).Count
        iv_running = [bool]$diagnosticsProbe.data.iv_running
        iv_status = [string]$diagnosticsProbe.data.iv_status_text
        iv_active_symbol = if ($null -eq $diagnosticsProbe.data.iv_active_symbol) { $null } else { [string]$diagnosticsProbe.data.iv_active_symbol }
    }
}

$providerHealth = @()
if ($providerUsageProbe.ok) {
    $providerHealth = @(
        $providerUsageProbe.data.health | ForEach-Object {
            [ordered]@{
                provider_id = [string]$_.provider_id
                health_label = [string]$_.health_label
                call_count = [int]$_.call_count
                success_count = [int]$_.success_count
                unavailable_count = [int]$_.unavailable_count
                error_count = [int]$_.error_count
            }
        }
    )
}

$readOnlyBoundary = $null
if ($boundaryProbe.ok) {
    $readOnlyBoundary = [ordered]@{
        read_only = [bool]$boundaryProbe.data.read_only
        prohibited_capability_count = @($boundaryProbe.data.prohibits).Count
        hard_lock_count = @($boundaryProbe.data.hard_operator_locks).Count
    }
}

$result = [ordered]@{
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    audit_gate = [ordered]@{
        default_mode = "ibkr-integrated"
        recommendation = $auditModeGate
        full_audit_requires_ibkr = $true
        disconnected_ibkr_is_baseline_constraint = $true
    }
    repository = [ordered]@{
        root = $repoRoot
        git_available = $gitAvailable
        commit = $gitCommit
        branch = $gitBranch
        dirty = if ($null -eq $gitChangeCount) { $null } else { $gitChangeCount -gt 0 }
        change_count = $gitChangeCount
        python_runtime_present = Test-Path -LiteralPath (Join-Path $repoRoot ".venv\Scripts\python.exe")
        frontend_manifest_present = Test-Path -LiteralPath (Join-Path $repoRoot "frontend\package.json")
        frontend_dependencies_present = Test-Path -LiteralPath (Join-Path $repoRoot "frontend\node_modules")
    }
    launcher_environment = [ordered]@{
        mock_data = Get-SafeMode -Value $env:MOCK_DATA -Allowed @("true", "false")
        commodities_provider = Get-SafeMode -Value $env:COMMODITIES_PROVIDER -Allowed @("sample", "eia", "ibkr")
        maritime_provider = Get-SafeMode -Value $env:MARITIME_PROVIDER -Allowed @("sample", "aisstream")
        copilot_provider = Get-SafeMode -Value $env:GAMMA_COPILOT_PROVIDER -Allowed @("openai", "mock", "disabled")
        session_token_configured = Test-Configured -Value $SessionToken
        credentials_present = [ordered]@{
            fred = Test-Configured -Value $env:FRED_API_KEY
            eia = Test-Configured -Value $env:EIA_API_KEY
            aisstream = Test-Configured -Value $env:AISSTREAM_API_KEY
            openai = Test-Configured -Value $env:OPENAI_API_KEY
        }
    }
    api = [ordered]@{
        base = $apiRoot
        health = [ordered]@{
            reachable = [bool]$healthProbe.ok
            status_code = $healthProbe.status_code
            reported_status = if ($healthProbe.ok) { [string]$healthProbe.data.status } else { $null }
        }
        authenticated_probe = [ordered]@{
            ok = [bool]$statusProbe.ok
            status_code = $statusProbe.status_code
            error_type = $statusProbe.error_type
        }
        status = $runtimeStatus
        diagnostics = $runtimeDiagnostics
        provider_health = $providerHealth
        read_only_boundary = $readOnlyBoundary
    }
    frontend = [ordered]@{
        base = $frontendRoot
        reachable = [bool]$frontendProbe.ok
        status_code = $frontendProbe.status_code
        error_type = $frontendProbe.error_type
    }
}

$result | ConvertTo-Json -Depth 8
