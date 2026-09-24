Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:MinimumNodeVersion = [Version]"24.16.0"

function Invoke-CfmiNativeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter()]
        [string[]]$ArgumentList = @()
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "'$FilePath' exited with code $LASTEXITCODE."
    }
}

function Assert-CfmiExactVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Version
    )

    if ($Version -notmatch '^\d{4}\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
        throw "OpenClawVersion must be an exact release such as 2026.6.34; tags and ranges are not allowed."
    }
}

function Assert-CfmiOpenClawPrerequisites {
    [CmdletBinding()]
    param()

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $nodeCommand -or -not $npmCommand) {
        throw "Node.js $script:MinimumNodeVersion or newer and npm must already be installed."
    }

    $nodeText = (& node --version).TrimStart("v")
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the installed Node.js version."
    }

    $nodeVersion = $null
    if (-not [Version]::TryParse($nodeText, [ref]$nodeVersion)) {
        throw "Node.js returned an unsupported version string: '$nodeText'."
    }
    if ($nodeVersion -lt $script:MinimumNodeVersion) {
        throw "Node.js $script:MinimumNodeVersion or newer is required; found $nodeVersion."
    }
}

function Install-CfmiOpenClawPackage {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Version
    )

    Assert-CfmiExactVersion -Version $Version
    Assert-CfmiOpenClawPrerequisites

    $npmText = (& npm --version).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the installed npm version."
    }

    $npmVersion = $null
    if (-not [Version]::TryParse($npmText, [ref]$npmVersion)) {
        throw "npm returned an unsupported version string: '$npmText'."
    }

    $arguments = @("install", "--global", "openclaw@$Version")
    if ($npmVersion.Major -ge 12 -or ($npmVersion.Major -eq 11 -and $npmVersion.Minor -ge 16)) {
        $arguments += "--allow-scripts=openclaw"
    }
    Invoke-CfmiNativeCommand -FilePath "npm" -ArgumentList $arguments

    $installedVersion = (& openclaw --version | Out-String).Trim()
    $expectedVersion = "^OpenClaw $([Regex]::Escape($Version))(?: \([0-9a-f]{7}\))?$"
    if ($LASTEXITCODE -ne 0 -or $installedVersion -notmatch $expectedVersion) {
        throw "The OpenClaw install did not report the requested version $Version."
    }
}

function Get-CfmiOpenClawStateDirectory {
    [CmdletBinding()]
    param()

    if ($env:OPENCLAW_STATE_DIR) {
        return [IO.Path]::GetFullPath($env:OPENCLAW_STATE_DIR)
    }

    $homeDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    return Join-Path $homeDirectory ".openclaw"
}

function Protect-CfmiSecretFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if ($IsWindows) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $identity,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
        return
    }

    Invoke-CfmiNativeCommand -FilePath "chmod" -ArgumentList @("600", $Path)
}

function Write-CfmiJsonFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [hashtable]$Value
    )

    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = Join-Path $directory ".$([IO.Path]::GetFileName($Path)).$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporaryPath -Encoding utf8NoBOM
        Protect-CfmiSecretFile -Path $temporaryPath
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
        Protect-CfmiSecretFile -Path $Path
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

Export-ModuleMember -Function @(
    "Assert-CfmiExactVersion",
    "Assert-CfmiOpenClawPrerequisites",
    "Get-CfmiOpenClawStateDirectory",
    "Install-CfmiOpenClawPackage",
    "Invoke-CfmiNativeCommand",
    "Write-CfmiJsonFile"
)
