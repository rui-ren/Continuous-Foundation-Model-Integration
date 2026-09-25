#requires -Version 5.1

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory)]
    [string]$ExpectedWindowsIdentity,

    [Parameter()]
    [string]$HermesHome = "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$hermesVersion = "0.21.5"
$hermesCommit = "749220ef0007f8d87bd1531f1c24b0fe93816385"
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($currentIdentity -ine $ExpectedWindowsIdentity) {
    throw "Repair identity mismatch. Expected '$ExpectedWindowsIdentity'; running as '$currentIdentity'."
}

$HermesHome = [IO.Path]::GetFullPath($HermesHome)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$modulePath = Join-Path $repositoryRoot "scripts\openclaw\Hermes.Install.psm1"
$ownershipPath = Join-Path $HermesHome "pipeline-installation.json"
$attemptDirectory = Join-Path $HermesHome "repair-attempts"

Import-Module $modulePath -Force
if (-not (Test-Path -LiteralPath $ownershipPath -PathType Leaf)) {
    throw "The pipeline-owned Hermes installation marker was not found."
}
$ownership = Get-Content -LiteralPath $ownershipPath -Raw | ConvertFrom-Json
if (
    $ownership.schema_version -ne 1 -or
    $ownership.created_by -cne "Install-HermesPipeline.ps1" -or
    $ownership.windows_identity -ine $currentIdentity -or
    $ownership.hermes_version -cne $hermesVersion -or
    $ownership.hermes_commit -cne $hermesCommit
) {
    throw "The pipeline-owned Hermes installation marker does not match the approved repair."
}

$successfulReceipt = Get-ChildItem `
    -LiteralPath (Join-Path $HermesHome "installation-attempts") `
    -Filter "*.json" |
    ForEach-Object {
        $record = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
        if (
            $record.status -ceq "SUCCEEDED" -and
            $record.windows_identity -ieq $currentIdentity -and
            $record.hermes_version -ceq $hermesVersion -and
            $record.hermes_commit -ceq $hermesCommit
        ) {
            $_
        }
    } |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $successfulReceipt) {
    throw "No prior successful pinned installation receipt exists."
}

$runtime = Assert-CfmiHermesSourceCheckout `
    -Commit $hermesCommit `
    -HermesHome $HermesHome

if (-not $PSCmdlet.ShouldProcess(
    $HermesHome,
    "Repair only the pinned Hermes editable package without dependencies"
)) {
    Write-Host "Repair was not approved; no package files were changed."
    return
}

New-Item -ItemType Directory -Path $attemptDirectory -Force | Out-Null
$attemptPath = Join-Path $attemptDirectory "$([Guid]::NewGuid().ToString("N")).json"

function Write-RepairAttempt {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("IN_PROGRESS", "SUCCEEDED", "FAILED")]
        [string]$Status,

        [Parameter()]
        [string]$FailureMessage
    )

    $record = [ordered]@{
        schema_version = 1
        status = $Status
        recorded_at = [DateTimeOffset]::UtcNow.ToString("o")
        windows_identity = $currentIdentity
        hermes_version = $hermesVersion
        hermes_commit = $hermesCommit
        source = $runtime.Source
        dependency_action = "not_installed"
        provider_configuration_action = "not_managed"
        gateway_action = "not_started"
        failure_message = $FailureMessage
    }
    $temporaryPath = "$attemptPath.tmp"
    [IO.File]::WriteAllText(
        $temporaryPath,
        ($record | ConvertTo-Json -Depth 4),
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporaryPath -Destination $attemptPath -Force
}

Write-RepairAttempt -Status "IN_PROGRESS"
try {
    Invoke-CfmiNativeCommand $runtime.Python @(
        "-m", "pip", "install",
        "--disable-pip-version-check",
        "--no-deps",
        "--editable",
        "$($runtime.Source)[all]"
    )
    $runtime = Assert-CfmiHermesInstallation `
        -Version $hermesVersion `
        -Commit $hermesCommit `
        -HermesHome $HermesHome
    Write-RepairAttempt -Status "SUCCEEDED"
}
catch {
    Write-RepairAttempt -Status "FAILED" -FailureMessage $_.Exception.Message
    throw
}

Write-Host "Pinned Hermes package metadata and executable were repaired without installing dependencies."
Write-Host "Repair receipt: $attemptPath"
