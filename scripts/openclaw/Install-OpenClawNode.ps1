#requires -Version 7.4

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$NodeName,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$GatewayHost,

    [Parameter()]
    [ValidateRange(1, 65535)]
    [int]$GatewayPort = 18789,

    [Parameter()]
    [ValidatePattern('^\d{4}\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$OpenClawVersion = "2026.6.34",

    [Parameter(Mandatory)]
    [SecureString]$GatewayToken,

    [Parameter()]
    [switch]$Tls,

    [Parameter()]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$TlsFingerprint,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "OpenClaw.Install.psm1") -Force

if ($Tls -and -not $TlsFingerprint) {
    throw "TlsFingerprint is required with -Tls so the node can pin the Gateway certificate."
}
if (-not $Tls -and $TlsFingerprint) {
    throw "TlsFingerprint cannot be used without -Tls."
}

if ($PSCmdlet.ShouldProcess("npm global prefix", "Install pinned OpenClaw $OpenClawVersion")) {
    Install-CfmiOpenClawPackage -Version $OpenClawVersion
}

if ($PSCmdlet.ShouldProcess("OpenClaw node policy", "Disable host execution and browser proxying")) {
    Invoke-CfmiNativeCommand openclaw @("exec-policy", "preset", "deny-all")
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "nodeHost.browserProxy.enabled", "false", "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "update.auto.enabled", "false", "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @(
        "config", "set", "update.checkOnStart", "false", "--strict-json"
    )
    Invoke-CfmiNativeCommand openclaw @("config", "validate")
}

if ($PSCmdlet.ShouldProcess($NodeName, "Install and start the restricted OpenClaw node service")) {
    $nodeArguments = @(
        "node", "install",
        "--host", $GatewayHost,
        "--port", "$GatewayPort",
        "--display-name", $NodeName
    )
    if ($Tls) {
        $nodeArguments += @("--tls", "--tls-fingerprint", $TlsFingerprint.ToLowerInvariant())
    }
    if ($Force) {
        $nodeArguments += "--force"
    }

    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($GatewayToken)
    $previousGatewayToken = $env:OPENCLAW_GATEWAY_TOKEN
    try {
        $plainGatewayToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
        if ([string]::IsNullOrWhiteSpace($plainGatewayToken)) {
            throw "GatewayToken cannot be empty."
        }

        # The pinned release persists this environment variable in the managed service.
        $env:OPENCLAW_GATEWAY_TOKEN = $plainGatewayToken
        Invoke-CfmiNativeCommand openclaw $nodeArguments
        Invoke-CfmiNativeCommand openclaw @("node", "status", "--json")
    }
    finally {
        $plainGatewayToken = $null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
        if ($null -eq $previousGatewayToken) {
            Remove-Item Env:OPENCLAW_GATEWAY_TOKEN -ErrorAction SilentlyContinue
        }
        else {
            $env:OPENCLAW_GATEWAY_TOKEN = $previousGatewayToken
        }
    }
}

Write-Host ""
Write-Host "Remote command execution is denied at the Gateway and locally; browser proxying is disabled."
Write-Host "On the Gateway, inspect and approve the two distinct requests:"
Write-Host "  openclaw devices list"
Write-Host "  openclaw devices approve <deviceRequestId>"
Write-Host "  openclaw nodes pending"
Write-Host "  openclaw nodes approve <nodeRequestId>"
Write-Host "Then restart this service with: openclaw node restart"
Write-Host "Read connection metadata with: openclaw nodes status --connected --json --timeout 5000"
if ($IsLinux) {
    Write-Warning "A systemd user service stops after logout unless an administrator enables lingering for this account."
}
