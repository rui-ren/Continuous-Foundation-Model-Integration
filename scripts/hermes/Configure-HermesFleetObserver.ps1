#requires -Version 7.4

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [string]$HermesExecutable = "$env:LOCALAPPDATA\hermes\bin\hermes.exe",

    [Parameter()]
    [string]$PythonExecutable = "python",

    [Parameter()]
    [string]$EvidencePath = "$env:LOCALAPPDATA\hermes\fleet-status.json",

    [Parameter()]
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot "..\..")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
$EvidencePath = [IO.Path]::GetFullPath($EvidencePath)
$serverPath = Join-Path $RepositoryRoot "tools\fleet_status_mcp.py"
$expectedTools = @("get_job_progress", "get_node_status", "list_nodes")

if (-not (Test-Path -LiteralPath $HermesExecutable -PathType Leaf)) {
    throw "Hermes executable not found: $HermesExecutable"
}
if (-not (Test-Path -LiteralPath $serverPath -PathType Leaf)) {
    throw "Fleet status MCP server not found: $serverPath"
}
$pythonCommand = Get-Command $PythonExecutable -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "Python executable not found: $PythonExecutable"
}

function Invoke-HermesConfigSet {
    param(
        [Parameter(Mandatory)]
        [string]$Key,

        [Parameter(Mandatory)]
        [string]$Value
    )

    & $HermesExecutable config set $Key $Value
    if ($LASTEXITCODE -ne 0) {
        throw "Hermes failed to set '$Key'."
    }
}

if ($PSCmdlet.ShouldProcess("Hermes config", "Register read-only CFMI fleet status MCP server")) {
    $discoveryRequest = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    $discoveryResponse = $discoveryRequest |
        & $pythonCommand.Source $serverPath |
        ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $null -eq $discoveryResponse.result.tools) {
        throw "Failed to discover tools from the local fleet status MCP server."
    }
    $discoveredTools = @($discoveryResponse.result.tools.name | Sort-Object)
    if (Compare-Object $expectedTools $discoveredTools) {
        throw "Fleet status MCP discovery did not match the approved read-only tool set."
    }

    Invoke-HermesConfigSet "approvals.mode" "manual"
    Invoke-HermesConfigSet "approvals.cron_mode" "deny"
    Invoke-HermesConfigSet "approvals.single_query_mode" "deny"
    Invoke-HermesConfigSet "approvals.unattended_mode" "deny"

    & $HermesExecutable config unset mcp_servers.cfmi_fleet_status *> $null
    "y" | & $HermesExecutable mcp add cfmi_fleet_status `
        --command $pythonCommand.Source `
        --env "CFMI_FLEET_STATUS_PATH=$EvidencePath" `
        --args $serverPath
    if ($LASTEXITCODE -ne 0) {
        throw "Hermes failed to register the fleet status MCP server."
    }

    Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.enabled" "true"
    Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.trust" "untrusted"
    Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.supports_parallel_tool_calls" "false"
    Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.tools.include" (
        @("list_nodes", "get_node_status", "get_job_progress") | ConvertTo-Json -Compress
    )
    Invoke-HermesConfigSet "platform_toolsets.cli" (
        @("clarify", "mcp-cfmi_fleet_status") | ConvertTo-Json -Compress
    )
}

if ($WhatIfPreference) {
    Write-Host ""
    Write-Host "WhatIf completed; Hermes configuration was not changed."
    return
}

Write-Host ""
Write-Host "Configured local read-only MCP server: cfmi_fleet_status"
Write-Host "Evidence path: $EvidencePath"
if (-not (Test-Path -LiteralPath $EvidencePath -PathType Leaf)) {
    Write-Warning "No evidence file exists yet. Tool calls will report RESOURCE_UNAVAILABLE."
}
Write-Host "Test with:"
Write-Host "  & '$HermesExecutable' mcp test cfmi_fleet_status"
