#requires -Version 7.4

# Legacy filename retained so existing operator references fail over to the
# approved Hermes path instead of installing prohibited OpenClaw software.
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter()]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$HermesVersion = "0.21.5",

    [Parameter()]
    [ValidatePattern('^[A-Fa-f0-9]{40}$')]
    [string]$HermesCommit = "749220ef0007f8d87bd1531f1c24b0fe93816385",

    [Parameter()]
    [ValidatePattern('^[a-z][a-z0-9-]{0,63}$')]
    [string]$AgentId = "superadmin",

    [Parameter()]
    [string]$HermesHome,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "Hermes.Install.psm1") -Force

if (-not $HermesHome) {
    $HermesHome = Get-CfmiHermesHome
}
$HermesHome = [IO.Path]::GetFullPath($HermesHome)
$workspacePath = Join-Path $HermesHome "workspace-$AgentId"
$agentInstructions = Join-Path $PSScriptRoot "templates\HermesObserver-AGENTS.md"
$runtime = Get-CfmiHermesRuntime -HermesHome $HermesHome

if ($PSCmdlet.ShouldProcess($runtime.Venv, "Install pinned Hermes Agent $HermesVersion")) {
    $runtime = Install-CfmiHermesPackage `
        -Version $HermesVersion `
        -Commit $HermesCommit `
        -HermesHome $HermesHome `
        -Force:$Force
}

if ($PSCmdlet.ShouldProcess($HermesHome, "Apply supervised Hermes approval defaults")) {
    if (-not (Test-Path -LiteralPath $runtime.Hermes)) {
        throw "Hermes is not installed at '$($runtime.Hermes)'. Run again without -WhatIf."
    }
    Set-CfmiHermesSafetyDefaults -HermesPath $runtime.Hermes -HermesHome $HermesHome
}

if ($PSCmdlet.ShouldProcess($workspacePath, "Create the read-only CFMI observer workspace")) {
    New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
    Copy-Item `
        -LiteralPath $agentInstructions `
        -Destination (Join-Path $workspacePath "AGENTS.md") `
        -Force
}

if ($WhatIfPreference) {
    Write-Host ""
    Write-Host "WhatIf completed; Hermes was not installed or configured."
    return
}

if (-not (Test-Path -LiteralPath $runtime.Hermes)) {
    throw "Hermes installation is incomplete: '$($runtime.Hermes)' was not found."
}

Write-Host ""
Write-Host "Hermes Agent $HermesVersion ($($HermesCommit.Substring(0, 8))) is installed as the central CFMI assistant."
Write-Host "OpenClaw is not installed and no Hermes runtime is deployed to fleet nodes."
Write-Host "Manual command approval and deny-on-unattended defaults are configured."
Write-Host "Run provider setup interactively before first use:"
Write-Host "  & '$($runtime.Hermes)' setup"
Write-Host "Start the constrained observer from its workspace:"
Write-Host "  Set-Location '$workspacePath'"
Write-Host "  & '$($runtime.Hermes)' chat --toolsets clarify"
Write-Warning "AGENTS.md is an instruction boundary, not an OS security boundary. Do not add SSH, terminal, file, browser, cron, or computer-use toolsets without a separate review."
