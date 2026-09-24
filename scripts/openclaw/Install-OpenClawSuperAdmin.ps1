#requires -Version 7.4

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter()]
    [ValidatePattern('^\d{4}\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$OpenClawVersion = "2026.6.34",

    [Parameter()]
    [ValidateSet("loopback", "tailnet", "lan")]
    [string]$GatewayBind = "tailnet",

    [Parameter()]
    [ValidateRange(1, 65535)]
    [int]$GatewayPort = 18789,

    [Parameter()]
    [string]$AgentId = "superadmin",

    [Parameter()]
    [switch]$AllowLan,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "OpenClaw.Install.psm1") -Force

if ($GatewayBind -eq "lan" -and -not $AllowLan) {
    throw "LAN binding requires -AllowLan. Prefer a private Tailnet and review firewall exposure first."
}
if ($AgentId -notmatch '^[a-z][a-z0-9-]{0,63}$') {
    throw "AgentId must start with a lowercase letter and contain only lowercase letters, digits, and hyphens."
}

if ($PSCmdlet.ShouldProcess("npm global prefix", "Install pinned OpenClaw $OpenClawVersion")) {
    Install-CfmiOpenClawPackage -Version $OpenClawVersion
}

$stateDirectory = Get-CfmiOpenClawStateDirectory
$cfmiDirectory = Join-Path $stateDirectory "cfmi"
$secretPath = Join-Path $cfmiDirectory "gateway-secrets.json"
$workspacePath = Join-Path $stateDirectory "workspace-$AgentId"
$agentInstructions = Join-Path $PSScriptRoot "templates\SuperAdmin-AGENTS.md"

if ($PSCmdlet.ShouldProcess($secretPath, "Create a file-backed Gateway authentication secret")) {
    if (-not (Test-Path -LiteralPath $secretPath)) {
        $tokenBytes = [byte[]]::new(32)
        [Security.Cryptography.RandomNumberGenerator]::Fill($tokenBytes)
        $token = [Convert]::ToBase64String($tokenBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
        Write-CfmiJsonFile -Path $secretPath -Value @{ gatewayToken = $token }
    }
}

if ($PSCmdlet.ShouldProcess("OpenClaw configuration", "Apply the restricted Gateway and node policy")) {
    Invoke-CfmiNativeCommand openclaw @("config", "set", "gateway.mode", "local")
    Invoke-CfmiNativeCommand openclaw @("config", "set", "gateway.bind", $GatewayBind)
    Invoke-CfmiNativeCommand openclaw @("config", "set", "gateway.port", "$GatewayPort", "--strict-json")
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "secrets.providers.cfmi",
        "--provider-source", "file", "--provider-path", $secretPath, "--provider-mode", "json"
    )
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "gateway.auth.token",
        "--ref-provider", "cfmi", "--ref-source", "file", "--ref-id", "gatewayToken"
    )
    Invoke-CfmiNativeCommand openclaw @("config", "set", "gateway.auth.mode", "token")
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "update.auto.enabled", "false", "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "update.checkOnStart", "false", "--strict-json"
    )
    $deniedNodeCommands = @(
        "browser.proxy",
        "system.execApprovals.get",
        "system.execApprovals.set",
        "system.run",
        "system.run.prepare",
        "system.which"
    ) | ConvertTo-Json -Compress
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "gateway.nodes.denyCommands", $deniedNodeCommands, "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @("config", "set", "commands.restart", "false", "--strict-json")
}

if ($PSCmdlet.ShouldProcess($workspacePath, "Create the restricted SuperAdmin agent workspace")) {
    $agentListJson = (& openclaw config get "agents.list" --json 2> $null | Out-String)
    $agentList = if ($LASTEXITCODE -eq 0) {
        @($agentListJson | ConvertFrom-Json)
    }
    else {
        @()
    }
    $matchingAgents = @($agentList | Where-Object { $_.id -eq $AgentId })
    if ($matchingAgents.Count -gt 1) {
        throw "Multiple agents use id '$AgentId'; refusing to choose one."
    }
    if ($matchingAgents.Count -eq 1) {
        $existingWorkspace = $matchingAgents[0].workspace
        if ([string]::IsNullOrWhiteSpace($existingWorkspace)) {
            throw "Existing agent '$AgentId' has no explicit workspace; refusing to change its permissions."
        }
        if ([IO.Path]::GetFullPath($existingWorkspace) -ne [IO.Path]::GetFullPath($workspacePath)) {
            throw "Existing agent '$AgentId' uses workspace '$existingWorkspace', not '$workspacePath'."
        }
    }
    else {
        Invoke-CfmiNativeCommand openclaw @(
            "agents", "add", $AgentId, "--workspace", $workspacePath, "--non-interactive"
        )
        $agentListJson = (& openclaw config get "agents.list" --json | Out-String)
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to read the agent roster after adding '$AgentId'."
        }
        $agentList = @($agentListJson | ConvertFrom-Json)
    }

    New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
    Copy-Item -LiteralPath $agentInstructions -Destination (Join-Path $workspacePath "AGENTS.md") -Force

    $allowedTools = @("session_status") | ConvertTo-Json -Compress
    $deniedTools = @(
        "apply_patch", "browser", "canvas", "cron", "edit", "exec", "gateway",
        "image", "nodes", "process", "read", "sessions_send", "sessions_spawn", "write"
    ) | ConvertTo-Json -Compress
    $agentIndex = [Array]::FindIndex(
        [object[]]$agentList,
        [Predicate[object]] { param($agent) $agent.id -eq $AgentId }
    )
    if ($agentIndex -lt 0) {
        throw "Agent '$AgentId' was not found in the configured roster."
    }
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "agents.list[$agentIndex].tools.allow", $allowedTools, "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "agents.list[$agentIndex].tools.deny", $deniedTools, "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @("config", "validate")
}

if ($PSCmdlet.ShouldProcess("OpenClaw Gateway service", "Install and start the managed service")) {
    $gatewayArguments = @("gateway", "install", "--port", "$GatewayPort")
    if ($Force) {
        $gatewayArguments += "--force"
    }
    Invoke-CfmiNativeCommand openclaw $gatewayArguments
    Invoke-CfmiNativeCommand openclaw @("gateway", "status")
    Invoke-CfmiNativeCommand openclaw @("security", "audit")
}

Write-Host ""
Write-Host "SuperAdmin installation is configured without node-control tools."
Write-Host "Use 'openclaw agent --agent $AgentId' to address the restricted agent."
Write-Host "Use the operator CLI ('openclaw nodes status') for live node visibility."
Write-Host "Pair each node manually; do not approve unexpected device or command-surface requests."
Write-Host "Provision nodes with the token stored at '$secretPath' using an approved secret-transfer channel."
