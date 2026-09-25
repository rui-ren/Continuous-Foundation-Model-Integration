#requires -Version 5.1

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')]
    [string]$NodeId,

    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')]
    [string]$ExpectedComputerName,

    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.$_-]{0,255}$')]
    [string]$PipelineAgentServiceName,

    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string[]]$Volumes = @("C:\"),

    [Parameter()]
    [string]$HermesHome = "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2",

    [Parameter()]
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot "..\.."),

    [Parameter()]
    [string]$AgentId = "local-observer"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$HermesHome = [IO.Path]::GetFullPath($HermesHome)
$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
$runtimeRoot = Join-Path $HermesHome "machine-doctor"
$runtimeSource = Join-Path $runtimeRoot "src\cfmi"
$runtimeTools = Join-Path $runtimeRoot "tools"
$configPath = Join-Path $runtimeRoot "machine-doctor-config.json"
$evidencePath = Join-Path $HermesHome "machine-status.json"
$workspacePath = Join-Path $HermesHome "workspace-$AgentId"
$hermesExecutable = Join-Path $HermesHome "cfmi-runtime\Scripts\hermes.exe"
$pythonExecutable = Join-Path $HermesHome "cfmi-runtime\Scripts\python.exe"
$collectorPath = Join-Path $runtimeTools "windows_machine_status.py"
$serverPath = Join-Path $runtimeTools "fleet_status_mcp.py"
$instructionsSource = Join-Path $PSScriptRoot "templates\HermesMachineDoctor-AGENTS.md"
$instructionsDestination = Join-Path $workspacePath "AGENTS.md"
$receiptPath = Join-Path $runtimeRoot "configuration-receipt.json"

$sourceFiles = [ordered]@{
    (Join-Path $RepositoryRoot "src\cfmi\__init__.py") = (Join-Path $runtimeSource "__init__.py")
    (Join-Path $RepositoryRoot "src\cfmi\fleet_status.py") = (Join-Path $runtimeSource "fleet_status.py")
    (Join-Path $RepositoryRoot "src\cfmi\machine_status.py") = (Join-Path $runtimeSource "machine_status.py")
    (Join-Path $RepositoryRoot "tools\fleet_status_mcp.py") = $serverPath
    (Join-Path $RepositoryRoot "tools\windows_machine_status.py") = $collectorPath
}

$observedComputerName = [Environment]::MachineName
if ($observedComputerName -ine $ExpectedComputerName) {
    throw "Observed computer '$observedComputerName' does not match expected computer '$ExpectedComputerName'."
}
foreach ($volume in $Volumes) {
    if ($volume -notmatch '^[A-Za-z]:\\$') {
        throw "Volume '$volume' must be a local drive root such as C:\."
    }
}
if (@($Volumes | Sort-Object -Unique).Count -ne $Volumes.Count) {
    throw "Volumes must not contain duplicates."
}
foreach ($sourcePath in @($sourceFiles.Keys) + @($instructionsSource)) {
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Required reviewed source file was not found: $sourcePath"
    }
}
if (-not (Test-Path -LiteralPath $hermesExecutable -PathType Leaf)) {
    throw "Hermes executable was not found: $hermesExecutable"
}
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw "Hermes Python executable was not found: $pythonExecutable"
}

$configuration = [ordered]@{
    schema_version = 1
    node_id = $NodeId
    expected_computer_name = $ExpectedComputerName
    service_name = $PipelineAgentServiceName
    volumes = @($Volumes | ForEach-Object { $_.ToUpperInvariant() } | Sort-Object)
    output_path = $evidencePath
    sample_count = 3
    sample_interval_seconds = 1.0
    probe_timeout_seconds = 5.0
    total_timeout_seconds = 30.0
}

if (-not $PSCmdlet.ShouldProcess(
    $HermesHome,
    "Install and configure the local read-only Hermes Machine Doctor pilot"
)) {
    Write-Host ""
    Write-Host "WhatIf completed; no files or Hermes settings were changed."
    Write-Host "Node ID: $NodeId"
    Write-Host "Expected computer: $ExpectedComputerName"
    Write-Host "Pipeline service: $PipelineAgentServiceName"
    Write-Host "Evidence path: $evidencePath"
    return
}

New-Item -ItemType Directory -Path $runtimeSource -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeTools -Force | Out-Null
New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
foreach ($sourcePath in $sourceFiles.Keys) {
    Copy-Item -LiteralPath $sourcePath -Destination $sourceFiles[$sourcePath] -Force
}
Copy-Item -LiteralPath $instructionsSource -Destination $instructionsDestination -Force

$temporaryConfigPath = "$configPath.tmp"
[IO.File]::WriteAllText(
    $temporaryConfigPath,
    ($configuration | ConvertTo-Json -Depth 4),
    [Text.UTF8Encoding]::new($false)
)
Move-Item -LiteralPath $temporaryConfigPath -Destination $configPath -Force

& $pythonExecutable $collectorPath --config $configPath
if ($LASTEXITCODE -ne 0) {
    throw "The initial Machine Doctor collection failed."
}

$expectedTools = @(
    "get_job_progress",
    "get_local_system_status",
    "get_node_status",
    "list_nodes"
)
$previousEvidencePath = $env:CFMI_FLEET_STATUS_PATH
try {
    $env:CFMI_FLEET_STATUS_PATH = $evidencePath
    $discoveryRequest = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    $discoveryText = (
        $discoveryRequest |
        & $pythonExecutable $serverPath |
        Out-String
    ).Trim()
    $discoveryExitCode = $LASTEXITCODE
}
finally {
    $env:CFMI_FLEET_STATUS_PATH = $previousEvidencePath
}
if ($discoveryExitCode -ne 0 -or -not $discoveryText) {
    throw "Failed to discover tools from the staged Machine Doctor MCP server."
}
try {
    $discoveryResponse = $discoveryText | ConvertFrom-Json
}
catch {
    throw "The staged Machine Doctor MCP server returned invalid discovery JSON."
}
$responsePropertyNames = @($discoveryResponse.PSObject.Properties.Name)
if ($responsePropertyNames -notcontains "result") {
    $errorDetail = if ($responsePropertyNames -contains "error") {
        " code=$($discoveryResponse.error.code) message=$($discoveryResponse.error.message)"
    }
    else {
        ""
    }
    throw "The staged Machine Doctor MCP server returned no result.$errorDetail"
}
$resultPropertyNames = @($discoveryResponse.result.PSObject.Properties.Name)
if ($resultPropertyNames -notcontains "tools") {
    throw "The staged Machine Doctor MCP server returned no tool list."
}
$discoveredTools = @($discoveryResponse.result.tools.name | Sort-Object)
if (Compare-Object $expectedTools $discoveredTools) {
    throw "Machine Doctor MCP discovery did not match the approved read-only tool set."
}

function Invoke-HermesConfigSet {
    param(
        [Parameter(Mandatory)]
        [string]$Key,

        [Parameter(Mandatory)]
        [string]$Value
    )

    & $hermesExecutable config set $Key $Value
    if ($LASTEXITCODE -ne 0) {
        throw "Hermes failed to set '$Key'."
    }
}

$env:HERMES_HOME = $HermesHome
Invoke-HermesConfigSet "approvals.mode" "manual"
Invoke-HermesConfigSet "approvals.cron_mode" "deny"
Invoke-HermesConfigSet "approvals.single_query_mode" "deny"
Invoke-HermesConfigSet "approvals.unattended_mode" "deny"

& $hermesExecutable config unset mcp_servers.cfmi_fleet_status *> $null
"y" | & $hermesExecutable mcp add cfmi_fleet_status `
    --command $pythonExecutable `
    --env "CFMI_FLEET_STATUS_PATH=$evidencePath" `
    --args $serverPath
if ($LASTEXITCODE -ne 0) {
    throw "Hermes failed to register the Machine Doctor MCP server."
}

Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.enabled" "true"
Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.trust" "full"
Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.supports_parallel_tool_calls" "false"
Invoke-HermesConfigSet "mcp_servers.cfmi_fleet_status.tools.include" (
    $expectedTools | ConvertTo-Json -Compress
)
Invoke-HermesConfigSet "platform_toolsets.cli" (
    @("clarify", "cfmi_fleet_status") | ConvertTo-Json -Compress
)
& $hermesExecutable tools enable --platform cli clarify
if ($LASTEXITCODE -ne 0) {
    throw "Hermes failed to enable the restricted CLI toolset."
}

$receipt = [ordered]@{
    schema_version = 1
    status = "SUCCEEDED"
    recorded_at = [DateTimeOffset]::UtcNow.ToString("o")
    node_id = $NodeId
    expected_computer_name = $ExpectedComputerName
    observed_computer_name = $observedComputerName
    pipeline_agent_service_name = $PipelineAgentServiceName
    volumes = @($configuration.volumes)
    evidence_path = $evidencePath
    tools = @($expectedTools)
    provider_configuration_action = "not_managed"
    gateway_action = "not_started"
    remote_transport_action = "not_configured"
    scheduling_action = "not_configured"
    remediation_action = "not_enabled"
}
$temporaryReceiptPath = "$receiptPath.tmp"
[IO.File]::WriteAllText(
    $temporaryReceiptPath,
    ($receipt | ConvertTo-Json -Depth 4),
    [Text.UTF8Encoding]::new($false)
)
Move-Item -LiteralPath $temporaryReceiptPath -Destination $receiptPath -Force

Write-Host ""
Write-Host "Configured the local read-only Hermes Machine Doctor pilot."
Write-Host "Node ID: $NodeId"
Write-Host "Evidence path: $evidencePath"
Write-Host "Configuration receipt: $receiptPath"
Write-Host "Collector command:"
Write-Host "  & '$pythonExecutable' '$collectorPath' --config '$configPath'"
Write-Host "Hermes test command:"
Write-Host "  Set-Location '$workspacePath'"
Write-Host "  & '$hermesExecutable' chat"
Write-Warning "The snapshot is point-in-time evidence. Re-run the collector before querying Hermes. No scheduler, remote transport, gateway, or remediation was enabled."
