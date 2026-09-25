#requires -Version 5.1

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$ExpectedWindowsIdentity,

    [Parameter()]
    [ValidatePattern('^[a-z][a-z0-9-]{0,63}$')]
    [string]$AgentId = "local-observer",

    [Parameter()]
    [string]$HermesHome,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$HermesVersion = "0.21.5"
$HermesCommit = "749220ef0007f8d87bd1531f1c24b0fe93816385"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "The unattended pipeline installer currently supports Windows only."
}

$osArchitecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
$processArchitecture = [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
if ($osArchitecture -notin @("X64", "Arm64")) {
    throw "Unsupported Windows architecture '$osArchitecture'. Use 64-bit AMD64 or ARM64."
}
if ($processArchitecture -cne $osArchitecture) {
    throw "PowerShell architecture '$processArchitecture' must match the '$osArchitecture' operating system."
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "A matching 64-bit Python 3.11-3.13 installation is required."
}
$pythonInfoText = (
    & $pythonCommand.Source -c @"
import json
import platform
import struct
print(json.dumps({"machine": platform.machine(), "bits": struct.calcsize("P") * 8}))
"@ |
    Out-String
).Trim()
if ($LASTEXITCODE -ne 0 -or -not $pythonInfoText) {
    throw "Unable to inspect the Python architecture."
}
$pythonInfo = ConvertFrom-Json -InputObject $pythonInfoText
$pythonMachine = "$($pythonInfo.machine)"
$pythonBits = [int]$pythonInfo.bits
$allowedPythonMachines = if ($osArchitecture -ceq "X64") {
    @("AMD64", "X86_64")
}
else {
    @("ARM64", "AARCH64")
}
if (
    $pythonBits -ne 64 -or
    $pythonMachine.ToUpperInvariant() -notin $allowedPythonMachines
) {
    throw "Python architecture '$pythonMachine' ($pythonBits-bit) does not match the $osArchitecture operating system."
}

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($currentIdentity -ine $ExpectedWindowsIdentity) {
    throw "Pipeline identity mismatch. Expected '$ExpectedWindowsIdentity'; running as '$currentIdentity'."
}

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$installerRoot = Join-Path $repositoryRoot "scripts\openclaw"
$modulePath = Join-Path $installerRoot "Hermes.Install.psm1"
$agentInstructions = Join-Path $installerRoot "templates\HermesObserver-AGENTS.md"

Import-Module $modulePath -Force
if (-not $HermesHome) {
    $HermesHome = Get-CfmiHermesHome
}
$HermesHome = [IO.Path]::GetFullPath($HermesHome)
$runtime = Get-CfmiHermesRuntime -HermesHome $HermesHome
$workspacePath = Join-Path $HermesHome "workspace-$AgentId"
$ownershipMarkerPath = Join-Path $HermesHome "pipeline-installation.json"

if (-not $PSCmdlet.ShouldProcess(
    $HermesHome,
    "Install pinned Hermes for pipeline identity '$currentIdentity'"
)) {
    Write-Host ""
    if ($WhatIfPreference) {
        Write-Host "WhatIf completed; Hermes was not installed or configured."
    }
    else {
        Write-Host "Installation was not approved; Hermes was not changed."
    }
    Write-Host "Pipeline identity: $currentIdentity"
    Write-Host "Architecture: OS=$osArchitecture, PowerShell=$processArchitecture, Python=$pythonMachine ($pythonBits-bit)"
    Write-Host "Hermes home: $HermesHome"
    return
}

if (Test-Path -LiteralPath $HermesHome -PathType Container) {
    $existingItems = @(Get-ChildItem -LiteralPath $HermesHome -Force)
    if ($existingItems.Count -gt 0 -and -not (
        Test-Path -LiteralPath $ownershipMarkerPath -PathType Leaf
    )) {
        throw "Refusing to reuse nonempty Hermes home without a pipeline ownership marker: $HermesHome"
    }
    if (Test-Path -LiteralPath $ownershipMarkerPath -PathType Leaf) {
        $ownership = Get-Content -LiteralPath $ownershipMarkerPath -Raw |
            ConvertFrom-Json
        if (
            $ownership.windows_identity -ine $currentIdentity -or
            $ownership.hermes_version -cne $HermesVersion -or
            $ownership.hermes_commit -cne $HermesCommit.ToLowerInvariant()
        ) {
            throw "Existing pipeline ownership marker does not match the reviewed installation identity or pin."
        }
    }
}

$attemptId = [Guid]::NewGuid().ToString("N")
$attemptDirectory = Join-Path $HermesHome "installation-attempts"
$attemptPath = Join-Path $attemptDirectory "$attemptId.json"
New-Item -ItemType Directory -Path $attemptDirectory -Force | Out-Null

function Write-InstallationAttempt {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("IN_PROGRESS", "SUCCEEDED", "FAILED")]
        [string]$Status,

        [Parameter()]
        [string]$FailureMessage
    )

    $record = [ordered]@{
        schema_version = 1
        attempt_id = $attemptId
        status = $Status
        recorded_at = [DateTimeOffset]::UtcNow.ToString("o")
        windows_identity = $currentIdentity
        os_architecture = $osArchitecture
        powershell_process_architecture = $processArchitecture
        python_architecture = $pythonMachine
        python_bits = $pythonBits
        hermes_version = $HermesVersion
        hermes_commit = $HermesCommit.ToLowerInvariant()
        hermes_home = $HermesHome
        workspace = $workspacePath
        agent_id = $AgentId
        provider_configuration_action = "not_managed_by_pipeline"
        gateway_action = "not_started_by_pipeline"
        fleet_connectivity_action = "not_configured_by_pipeline"
        failure_message = $FailureMessage
    }
    $temporaryPath = "$attemptPath.tmp"
    $json = $record | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText(
        $temporaryPath,
        $json,
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporaryPath -Destination $attemptPath -Force
}

Write-InstallationAttempt -Status "IN_PROGRESS"

try {
    $runtime = Install-CfmiHermesPackage `
        -Version $HermesVersion `
        -Commit $HermesCommit `
        -HermesHome $HermesHome `
        -Force:$Force

    Set-CfmiHermesSafetyDefaults `
        -HermesPath $runtime.Hermes `
        -HermesHome $HermesHome

    New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
    Copy-Item `
        -LiteralPath $agentInstructions `
        -Destination (Join-Path $workspacePath "AGENTS.md") `
        -Force

    $ownership = [ordered]@{
        schema_version = 1
        windows_identity = $currentIdentity
        hermes_version = $HermesVersion
        hermes_commit = $HermesCommit.ToLowerInvariant()
        created_by = "Install-HermesPipeline.ps1"
    }
    $temporaryOwnershipPath = "$ownershipMarkerPath.tmp"
    [IO.File]::WriteAllText(
        $temporaryOwnershipPath,
        ($ownership | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item `
        -LiteralPath $temporaryOwnershipPath `
        -Destination $ownershipMarkerPath `
        -Force

    Write-InstallationAttempt -Status "SUCCEEDED"
}
catch {
    Write-InstallationAttempt -Status "FAILED" -FailureMessage $_.Exception.Message
    throw
}

Write-Host ""
Write-Host "Pinned Hermes installation completed."
Write-Host "Pipeline identity: $currentIdentity"
Write-Host "Architecture: OS=$osArchitecture, PowerShell=$processArchitecture, Python=$pythonMachine ($pythonBits-bit)"
Write-Host "Hermes executable: $($runtime.Hermes)"
Write-Host "Observer workspace: $workspacePath"
Write-Host "Installation receipt: $attemptPath"
Write-Host "Provider configuration action: not managed by this pipeline."
Write-Host "Gateway action: not started by this pipeline."
Write-Host "Fleet connectivity action: not configured by this pipeline."
Write-Warning "This machine is staged, not operationally connected. GitHub Copilot authentication remains local and interactive."
