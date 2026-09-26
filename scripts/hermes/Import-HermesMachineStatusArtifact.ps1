#requires -Version 7.4

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "Medium")]
param(
    [Parameter(Mandatory)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$RunId,

    [Parameter()]
    [string]$Organization = "https://aiinfra.visualstudio.com",

    [Parameter()]
    [string]$Project = "AIFoundryLocal",

    [Parameter()]
    [string]$ArtifactName = "hermes-machine-status-evidence",

    [Parameter()]
    [string]$ExpectedPipelineName = "CFMI-Hermes-GPU4090-Status-Export",

    [Parameter(Mandatory)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$ExpectedDefinitionId,

    [Parameter()]
    [string]$ExpectedRepositoryType = "GitHub",

    [Parameter()]
    [string]$ExpectedRepositoryId = "rui-ren/Continuous-Foundation-Model-Integration",

    [Parameter()]
    [string]$ExpectedNodeId = "gpu-4090-pilot",

    [Parameter()]
    [string]$ExpectedComputerName = "ORT-GPU-BENCH-5",

    [Parameter()]
    [string]$ExpectedServiceName = "vstsagent.aiinfra.FoundryLocal-GPU-4090.ORT-GPU-BENCH-5",

    [Parameter()]
    [string]$EvidencePath = "$env:LOCALAPPDATA\hermes\fleet-status.json",

    [Parameter()]
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot "..\.."),

    [Parameter()]
    [string]$PythonExecutable = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
$EvidencePath = [IO.Path]::GetFullPath($EvidencePath)
$importerPath = Join-Path $RepositoryRoot "tools\import_machine_status_artifact.py"
$receiptDirectory = Join-Path (Split-Path -Parent $EvidencePath) "fleet-status-imports"
$importReceiptPath = Join-Path $receiptDirectory "run-$RunId.json"

if (-not (Test-Path -LiteralPath $importerPath -PathType Leaf)) {
    throw "Machine-status artifact importer was not found: $importerPath"
}
$python = Get-Command $PythonExecutable -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python executable was not found: $PythonExecutable"
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI was not found."
}

$runText = (
    & az pipelines runs show `
        --id $RunId `
        --org $Organization `
        --project $Project `
        --output json |
    Out-String
).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI could not read pipeline run $RunId."
}
$run = $runText | ConvertFrom-Json
if (
    $run.status -cne "completed" -or
    $run.result -cne "succeeded" -or
    $run.definition.name -cne $ExpectedPipelineName -or
    [int]$run.definition.id -ne $ExpectedDefinitionId -or
    $run.repository.type -cne $ExpectedRepositoryType -or
    $run.repository.id -ine $ExpectedRepositoryId
) {
    throw "Run $RunId does not match the exact approved pipeline and repository."
}
if ("$($run.sourceVersion)" -notmatch '^[a-fA-F0-9]{40}$') {
    throw "Run $RunId does not report an immutable Git source version."
}

if (-not $PSCmdlet.ShouldProcess(
    $EvidencePath,
    "Import validated 4090 Machine Doctor evidence from pipeline run $RunId"
)) {
    Write-Host ""
    Write-Host "WhatIf completed; no artifact was downloaded or imported."
    Write-Host "Pipeline: $ExpectedPipelineName"
    Write-Host "Definition ID: $ExpectedDefinitionId"
    Write-Host "Repository: $ExpectedRepositoryType $ExpectedRepositoryId"
    Write-Host "Run ID: $RunId"
    Write-Host "Source version: $($run.sourceVersion)"
    Write-Host "Destination: $EvidencePath"
    return
}

$temporaryDirectory = Join-Path (
    [IO.Path]::GetTempPath()
) "cfmi-machine-status-$RunId-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
try {
    & az pipelines runs artifact download `
        --run-id $RunId `
        --artifact-name $ArtifactName `
        --path $temporaryDirectory `
        --org $Organization `
        --project $Project `
        --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI could not download '$ArtifactName' from run $RunId."
    }

    $snapshots = @(
        Get-ChildItem -LiteralPath $temporaryDirectory -Recurse -File `
            -Filter "machine-status.json"
    )
    $exportReceipts = @(
        Get-ChildItem -LiteralPath $temporaryDirectory -Recurse -File `
            -Filter "export-receipt.json"
    )
    if ($snapshots.Count -ne 1 -or $exportReceipts.Count -ne 1) {
        throw "The artifact must contain exactly one snapshot and one export receipt."
    }

    New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null
    & $python.Source $importerPath `
        --snapshot $snapshots[0].FullName `
        --export-receipt $exportReceipts[0].FullName `
        --destination $EvidencePath `
        --import-receipt $importReceiptPath `
        --expected-node-id $ExpectedNodeId `
        --expected-computer-name $ExpectedComputerName `
        --expected-service-name $ExpectedServiceName `
        --expected-pipeline-name $ExpectedPipelineName `
        --expected-definition-id "$ExpectedDefinitionId" `
        --expected-repository-type $ExpectedRepositoryType `
        --expected-repository-id $ExpectedRepositoryId `
        --expected-run-id "$RunId" `
        --expected-source-version "$($run.sourceVersion)"
    if ($LASTEXITCODE -ne 0) {
        throw "Machine-status artifact validation or import failed."
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryDirectory -PathType Container) {
        Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
    }
}

Write-Host ""
Write-Host "Imported validated 4090 evidence from run $RunId."
Write-Host "Evidence path: $EvidencePath"
Write-Host "Import receipt: $importReceiptPath"
