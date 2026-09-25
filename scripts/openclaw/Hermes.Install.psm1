Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:MinimumPythonVersion = [Version]"3.11.0"
$script:MaximumPythonVersion = [Version]"3.14.0"

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

function Assert-CfmiHermesVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Version
    )

    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "HermesVersion must be an exact release such as 0.21.5; tags and ranges are not allowed."
    }
}

function Assert-CfmiHermesPrerequisites {
    [CmdletBinding()]
    param()

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python $script:MinimumPythonVersion or newer, but earlier than $script:MaximumPythonVersion, must already be installed."
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git must already be installed."
    }

    $pythonText = (& python -c "import platform; print(platform.python_version())").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the installed Python version."
    }

    $pythonVersion = $null
    if (-not [Version]::TryParse($pythonText, [ref]$pythonVersion)) {
        throw "Python returned an unsupported version string: '$pythonText'."
    }
    if ($pythonVersion -lt $script:MinimumPythonVersion -or $pythonVersion -ge $script:MaximumPythonVersion) {
        throw "Hermes requires Python >= $script:MinimumPythonVersion and < $script:MaximumPythonVersion; found $pythonVersion."
    }
}

function Get-CfmiHermesHome {
    [CmdletBinding()]
    param()

    if ($env:HERMES_HOME) {
        return [IO.Path]::GetFullPath($env:HERMES_HOME)
    }

    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        return Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) "hermes"
    }

    return Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)) ".hermes"
}

function Get-CfmiHermesRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$HermesHome
    )

    $venvPath = Join-Path $HermesHome "cfmi-runtime"
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $pythonPath = Join-Path $venvPath "Scripts\python.exe"
        $hermesPath = Join-Path $venvPath "Scripts\hermes.exe"
    }
    else {
        $pythonPath = Join-Path $venvPath "bin/python"
        $hermesPath = Join-Path $venvPath "bin/hermes"
    }

    return @{
        Venv = $venvPath
        Python = $pythonPath
        Hermes = $hermesPath
        Source = (Join-Path $HermesHome "hermes-agent-src")
    }
}

function Install-CfmiHermesPackage {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Version,

        [Parameter(Mandatory)]
        [ValidatePattern('^[A-Fa-f0-9]{40}$')]
        [string]$Commit,

        [Parameter(Mandatory)]
        [string]$HermesHome,

        [Parameter()]
        [switch]$Force
    )

    Assert-CfmiHermesVersion -Version $Version
    Assert-CfmiHermesPrerequisites

    $runtime = Get-CfmiHermesRuntime -HermesHome $HermesHome
    New-Item -ItemType Directory -Path $HermesHome -Force | Out-Null
    if (-not (Test-Path -LiteralPath $runtime.Python)) {
        Invoke-CfmiNativeCommand python @("-m", "venv", $runtime.Venv)
    }

    $gitConfigCountText = [Environment]::GetEnvironmentVariable("GIT_CONFIG_COUNT")
    $gitConfigCount = 0
    if (
        $gitConfigCountText -and
        (-not [int]::TryParse($gitConfigCountText, [ref]$gitConfigCount) -or $gitConfigCount -lt 0)
    ) {
        throw "GIT_CONFIG_COUNT must be a non-negative integer; found '$gitConfigCountText'."
    }
    $gitConfigKeyName = "GIT_CONFIG_KEY_$gitConfigCount"
    $gitConfigValueName = "GIT_CONFIG_VALUE_$gitConfigCount"
    $gitConfigVariables = @{}
    foreach ($name in @("GIT_CONFIG_COUNT", $gitConfigKeyName, $gitConfigValueName)) {
        $gitConfigVariables[$name] = [Environment]::GetEnvironmentVariable($name)
    }
    try {
        $env:GIT_CONFIG_COUNT = "$($gitConfigCount + 1)"
        Set-Item "Env:$gitConfigKeyName" "core.longpaths"
        Set-Item "Env:$gitConfigValueName" "true"

        if (-not (Test-Path -LiteralPath $runtime.Source)) {
            Invoke-CfmiNativeCommand git @(
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/NousResearch/hermes-agent.git",
                $runtime.Source
            )
        }
        if (-not (Test-Path -LiteralPath (Join-Path $runtime.Source ".git"))) {
            throw "Hermes source path is not a Git checkout: '$($runtime.Source)'."
        }
        $origin = (
            & git -C $runtime.Source remote get-url origin |
            Out-String
        ).Trim()
        if (
            $LASTEXITCODE -ne 0 -or
            $origin -cne "https://github.com/NousResearch/hermes-agent.git"
        ) {
            throw "Hermes source checkout has an unexpected origin: '$origin'."
        }
        Invoke-CfmiNativeCommand git @(
            "-C", $runtime.Source,
            "fetch", "--depth", "1", "origin", $Commit
        )
        Invoke-CfmiNativeCommand git @(
            "-C", $runtime.Source,
            "checkout", "--detach", $Commit
        )
        $sourceCommit = (
            & git -C $runtime.Source rev-parse HEAD |
            Out-String
        ).Trim()
        if (
            $LASTEXITCODE -ne 0 -or
            $sourceCommit -cne $Commit.ToLowerInvariant()
        ) {
            throw "Hermes source checkout did not resolve to the requested commit $Commit."
        }
        $sourceChanges = (
            & git -C $runtime.Source status --porcelain |
            Out-String
        ).Trim()
        if ($LASTEXITCODE -ne 0 -or $sourceChanges) {
            throw "Hermes source checkout contains uncommitted changes."
        }

        $installArguments = @(
            "-m", "pip", "install",
            "--disable-pip-version-check",
            "--upgrade",
            "--editable",
            "$($runtime.Source)[all]"
        )
        if ($Force) {
            $installArguments += "--force-reinstall"
        }
        Invoke-CfmiNativeCommand $runtime.Python $installArguments
    }
    finally {
        foreach ($name in $gitConfigVariables.Keys) {
            $previousValue = $gitConfigVariables[$name]
            if ($null -eq $previousValue) {
                Remove-Item "Env:$name" -ErrorAction SilentlyContinue
            }
            else {
                Set-Item "Env:$name" $previousValue
            }
        }
    }

    $directUrlText = (& $runtime.Python -c "from importlib.metadata import distribution; print(distribution('hermes-agent').read_text('direct_url.json') or '')" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $directUrlText) {
        throw "The Hermes install did not provide VCS provenance for the requested commit $Commit."
    }
    $provenance = ConvertFrom-Json -InputObject $directUrlText
    $installedSourcePath = $null
    try {
        $installedSourceUri = [Uri]$provenance.url
        if ($installedSourceUri.IsFile) {
            $installedSourcePath = [IO.Path]::GetFullPath(
                [Uri]::UnescapeDataString($installedSourceUri.LocalPath)
            )
        }
    }
    catch {
        $installedSourcePath = $null
    }
    $sourceMatches = if (
        [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
    ) {
        $installedSourcePath -ieq $runtime.Source
    }
    else {
        $installedSourcePath -ceq $runtime.Source
    }
    if (
        $null -eq $provenance -or
        $provenance.dir_info.editable -ne $true -or
        -not $sourceMatches
    ) {
        throw "The Hermes install did not originate from the verified editable source checkout."
    }

    $installedVersion = (& $runtime.Hermes --version | Out-String).Trim()
    $versionPattern = "(?<![A-Za-z0-9.+-])v$([Regex]::Escape($Version))(?![A-Za-z0-9.+-])"
    if ($LASTEXITCODE -ne 0 -or $installedVersion -notmatch $versionPattern) {
        throw "The Hermes install did not report the requested version $Version."
    }

    return $runtime
}

function Set-CfmiHermesSafetyDefaults {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$HermesPath,

        [Parameter(Mandatory)]
        [string]$HermesHome
    )

    $env:HERMES_HOME = $HermesHome
    foreach ($setting in @(
        @("approvals.mode", "manual"),
        @("approvals.cron_mode", "deny"),
        @("approvals.single_query_mode", "deny"),
        @("approvals.unattended_mode", "deny")
    )) {
        Invoke-CfmiNativeCommand $HermesPath @("config", "set", $setting[0], $setting[1])
    }
}

Export-ModuleMember -Function @(
    "Get-CfmiHermesHome",
    "Get-CfmiHermesRuntime",
    "Install-CfmiHermesPackage",
    "Invoke-CfmiNativeCommand",
    "Set-CfmiHermesSafetyDefaults"
)
