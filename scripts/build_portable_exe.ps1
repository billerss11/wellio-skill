$ErrorActionPreference = "Stop"

$skillDir = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $skillDir "runtime"
$runtimeSource = Join-Path $skillDir "runtime\src"
$entryPoint = Join-Path $runtimeSource "wellio\__main__.py"
$workDir = Join-Path $skillDir "build\pyinstaller"
$distDir = Join-Path $skillDir "scripts"
$environmentName = "wellio-skill"
$ownerMarkerName = ".wellio-skill-environment"
$primaryIndex = "https://pypi.tuna.tsinghua.edu.cn/simple"
$fallbackIndex = "https://pypi.org/simple"

$conda = Get-Command conda -ErrorAction SilentlyContinue
if (-not $conda) {
    throw "Conda is required to build wellio.exe."
}

function Invoke-Conda {
    param([string[]]$CondaArguments)

    & $conda.Source @CondaArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Conda command failed: conda $($CondaArguments -join ' ')"
    }
}

function Find-WellioEnvironment {
    $json = & $conda.Source env list --json
    if ($LASTEXITCODE -ne 0) {
        throw "Could not list Conda environments."
    }
    $matches = @(
        ($json | Out-String | ConvertFrom-Json).envs |
            Where-Object {
                (Split-Path -Leaf $_.TrimEnd('\', '/')) -ieq $environmentName
            }
    )
    if ($matches.Count -gt 1) {
        throw "Multiple Conda environments are named '$environmentName': $($matches -join ', ')"
    }
    return $matches | Select-Object -First 1
}

$environmentPath = Find-WellioEnvironment
if (-not $environmentPath) {
    Invoke-Conda @(
        "create", "--name", $environmentName, "python=3.12", "pip", "-y"
    )
    $environmentPath = Find-WellioEnvironment
    if (-not $environmentPath) {
        throw "Conda created '$environmentName' but its path could not be resolved."
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $environmentPath $ownerMarkerName),
        "Managed by the Wellio Codex skill.`n"
    )
}

$ownerMarker = Join-Path $environmentPath $ownerMarkerName
if (-not (Test-Path -LiteralPath $ownerMarker -PathType Leaf)) {
    throw "Refusing to modify unmanaged Conda environment: $environmentPath"
}

$primaryInstallArguments = @(
    "run", "-n", $environmentName,
    "python", "-m", "pip", "install", "--upgrade",
    "--index-url", $primaryIndex,
    $runtimeDir, "PyInstaller>=6.22,<7"
)
& $conda.Source @primaryInstallArguments
if ($LASTEXITCODE -ne 0) {
    Write-Warning "The primary package index failed; retrying official PyPI."
    Invoke-Conda @(
        "run", "-n", $environmentName,
        "python", "-m", "pip", "install", "--upgrade",
        "--index-url", $fallbackIndex,
        $runtimeDir, "PyInstaller>=6.22,<7"
    )
}

Invoke-Conda @(
    "run", "-n", $environmentName,
    "python", "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "wellio",
    "--paths", $runtimeSource,
    "--workpath", $workDir,
    "--distpath", $distDir,
    "--specpath", $workDir,
    "--collect-all", "dlisio",
    $entryPoint
)

$executable = Join-Path $distDir "wellio.exe"
$sizeMiB = [Math]::Round((Get-Item -LiteralPath $executable).Length / 1MB, 1)
$sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
Write-Host "Built $executable ($sizeMiB MiB)"
Write-Host "SHA-256: $sha256"
