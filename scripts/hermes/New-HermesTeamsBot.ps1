#requires -Version 7.4

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$ServiceManagementReference,

    [Parameter(Mandatory)]
    [uri]$MessagingEndpoint,

    [Parameter()]
    [string]$ResourceGroup = "ruiren-dev",

    [Parameter()]
    [ValidatePattern("^[A-Za-z0-9_-]{4,42}$")]
    [string]$BotName = "cfmi-hermes-ruiren",

    [Parameter()]
    [string]$DisplayName = "CFMI Hermes Fleet Observer",

    [Parameter()]
    [string]$AllowedUsers = "ruiren@microsoft.com",

    [Parameter()]
    [string]$HermesEnvPath = "$env:LOCALAPPDATA\hermes\.env",

    [Parameter()]
    [switch]$RotateSecret
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($MessagingEndpoint.Scheme -ne "https") {
    throw "MessagingEndpoint must use HTTPS."
}
if ($MessagingEndpoint.AbsolutePath.TrimEnd("/") -ne "/api/messages") {
    throw "MessagingEndpoint must end in /api/messages."
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI is not installed."
}

function Invoke-AzureJson {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $output = & az @Arguments --only-show-errors --output json
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI failed: az $($Arguments -join ' ')"
    }
    return $output | ConvertFrom-Json
}

function Set-HermesEnvironmentValues {
    param(
        [Parameter(Mandatory)]
        [Collections.IDictionary]$Values
    )

    $parent = Split-Path -Parent $HermesEnvPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $lines = if (Test-Path -LiteralPath $HermesEnvPath) {
        [Collections.Generic.List[string]](Get-Content -LiteralPath $HermesEnvPath)
    }
    else {
        [Collections.Generic.List[string]]::new()
    }

    foreach ($key in $Values.Keys) {
        $replacement = "$key=$($Values[$key])"
        $index = -1
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^$([regex]::Escape($key))=") {
                $index = $i
                break
            }
        }
        if ($index -ge 0) {
            $lines[$index] = $replacement
        }
        else {
            $lines.Add($replacement)
        }
    }
    [IO.File]::WriteAllLines(
        $HermesEnvPath,
        $lines,
        [Text.UTF8Encoding]::new($false)
    )
}

$account = Invoke-AzureJson @("account", "show")
$tenantId = [string]$account.tenantId
$resourceGroupInfo = Invoke-AzureJson @("group", "show", "--name", $ResourceGroup)
$apps = Invoke-AzureJson @(
    "ad",
    "app",
    "list",
    "--filter",
    "displayName eq '$DisplayName'"
)
if (@($apps).Count -gt 1) {
    throw "More than one Entra application is named '$DisplayName'."
}

$app = @($apps) | Select-Object -First 1
$secret = $null
$hasLocalSecret = $false
if (-not $app -and $WhatIfPreference) {
    $null = $PSCmdlet.ShouldProcess(
        $DisplayName,
        "Create single-tenant Entra application with approved SMR"
    )
    $null = $PSCmdlet.ShouldProcess($DisplayName, "Create one-year client secret")
    $null = $PSCmdlet.ShouldProcess($BotName, "Create free single-tenant Azure Bot")
    $null = $PSCmdlet.ShouldProcess($BotName, "Enable Microsoft Teams channel")
    $null = $PSCmdlet.ShouldProcess(
        $HermesEnvPath,
        "Store Teams identity and safety settings"
    )
    Write-Host "WhatIf completed; no Entra application or Azure Bot was created."
    return
}

if ($app) {
    if ($app.serviceManagementReference -ne $ServiceManagementReference) {
        throw "Existing app does not have the approved Service Management Reference."
    }
    if ($app.signInAudience -ne "AzureADMyOrg") {
        throw "Existing app is not single-tenant."
    }
    $appId = [string]$app.appId
    $hasLocalSecret = (Test-Path -LiteralPath $HermesEnvPath -PathType Leaf) -and
        [bool](Select-String -LiteralPath $HermesEnvPath -Pattern "^TEAMS_CLIENT_SECRET=.+")
    if (-not $hasLocalSecret -and -not $RotateSecret) {
        throw "Existing app secret is unavailable locally. Use -RotateSecret after approval."
    }
}
elseif ($PSCmdlet.ShouldProcess($DisplayName, "Create single-tenant Entra application")) {
    $app = Invoke-AzureJson @(
        "ad",
        "app",
        "create",
        "--display-name",
        $DisplayName,
        "--sign-in-audience",
        "AzureADMyOrg",
        "--service-management-reference",
        $ServiceManagementReference
    )
    $appId = [string]$app.appId
}
else {
    throw "Entra application creation was declined."
}

if (-not $appId) {
    throw "Entra application ID is unavailable."
}

$environmentValues = [ordered]@{
    TEAMS_CLIENT_ID = $appId
    TEAMS_TENANT_ID = $tenantId
    TEAMS_HOST = "127.0.0.1"
    TEAMS_PORT = "3978"
    TEAMS_ALLOWED_USERS = $AllowedUsers
    TEAMS_ALLOW_ALL_USERS = "false"
    TEAMS_REQUIRE_MENTION = "true"
}
$environmentStored = $false
if (-not $hasLocalSecret -or $RotateSecret) {
    if ($PSCmdlet.ShouldProcess($DisplayName, "Create one-year client secret")) {
        $credential = Invoke-AzureJson @(
            "ad",
            "app",
            "credential",
            "reset",
            "--id",
            $appId,
            "--append",
            "--years",
            "1",
            "--display-name",
            "Hermes Teams gateway"
        )
        $secret = [string]$credential.password
        if (-not $secret) {
            throw "Entra client secret creation returned no secret."
        }
        $environmentValues.TEAMS_CLIENT_SECRET = $secret
        Set-HermesEnvironmentValues $environmentValues
        $environmentStored = $true
    }
}

$botResourceId = "$($resourceGroupInfo.id)/providers/Microsoft.BotService/botServices/$BotName"
$botJson = & az resource show --ids $botResourceId --only-show-errors --output json 2>$null
if ($LASTEXITCODE -ne 0) {
    if ($PSCmdlet.ShouldProcess($BotName, "Create free single-tenant Azure Bot")) {
        $null = Invoke-AzureJson @(
            "bot",
            "create",
            "--name",
            $BotName,
            "--resource-group",
            $ResourceGroup,
            "--app-type",
            "SingleTenant",
            "--appid",
            $appId,
            "--tenant-id",
            $tenantId,
            "--sku",
            "F0",
            "--endpoint",
            $MessagingEndpoint.AbsoluteUri,
            "--description",
            "Read-only CFMI Hermes fleet observer for Microsoft Teams"
        )
    }
}
else {
    $bot = $botJson | ConvertFrom-Json
    $mismatches = [Collections.Generic.List[string]]::new()
    if ($bot.properties.msaAppId -ne $appId) {
        $mismatches.Add("application ID")
    }
    if ($bot.properties.msaAppTenantId -ne $tenantId) {
        $mismatches.Add("tenant ID")
    }
    if ($bot.properties.msaAppType -ne "SingleTenant") {
        $mismatches.Add("application type")
    }
    if ($bot.sku.name -ne "F0") {
        $mismatches.Add("SKU")
    }
    if (
        ([uri]$bot.properties.endpoint).AbsoluteUri.TrimEnd("/") -ne
        $MessagingEndpoint.AbsoluteUri.TrimEnd("/")
    ) {
        $mismatches.Add("messaging endpoint")
    }
    if ($mismatches.Count) {
        throw "Existing Azure Bot differs in: $($mismatches -join ', ')."
    }
}

& az bot msteams show --name $BotName --resource-group $ResourceGroup `
    --only-show-errors --output none 2>$null
if ($LASTEXITCODE -ne 0 -and $PSCmdlet.ShouldProcess($BotName, "Enable Teams channel")) {
    & az bot msteams create --name $BotName --resource-group $ResourceGroup `
        --enable-calling false --only-show-errors --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to enable the Microsoft Teams channel."
    }
}

if (
    -not $environmentStored -and
    $PSCmdlet.ShouldProcess($HermesEnvPath, "Store Teams identity and safety settings")
) {
    Set-HermesEnvironmentValues $environmentValues
}

Write-Host ""
Write-Host "Entra application ID: $appId"
Write-Host "Azure Bot: $BotName"
Write-Host "Messaging endpoint: $($MessagingEndpoint.AbsoluteUri)"
Write-Host "Teams channel: enabled"
Write-Host "Hermes gateway: not started"
Write-Host "Client secret value was not displayed."
