[CmdletBinding()]
param(
    [string]$Python,
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoRoot "dist"
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)

if (-not $Python) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $venvPython -PathType Leaf) { $venvPython } else { "python" }
}

$pyproject = Join-Path $repoRoot "pyproject.toml"
$configExample = Join-Path $repoRoot "config.example.toml"
$modelNotice = Join-Path $repoRoot "THIRD_PARTY_MODELS.md"
foreach ($requiredPath in @($pyproject, $configExample, $modelNotice)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required runtime source is missing: $requiredPath"
    }
}

$versionLine = Select-String -LiteralPath $pyproject -Pattern '^version\s*=\s*"([^"]+)"$' | Select-Object -First 1
if (-not $versionLine) {
    throw "Project version was not found in $pyproject"
}
$version = $versionLine.Matches[0].Groups[1].Value
$bundleName = "huhac-media-runtime-$version"
$bundlePath = Join-Path $outputRoot "$bundleName.zip"

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("huhac-media-runtime-" + [guid]::NewGuid().ToString("N"))
$wheelDirectory = Join-Path $stagingRoot "wheel"
$bundleDirectory = Join-Path $stagingRoot $bundleName

try {
    New-Item -ItemType Directory -Path $wheelDirectory, $bundleDirectory -Force | Out-Null

    & $Python -m pip wheel --no-deps --no-build-isolation --wheel-dir $wheelDirectory $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Wheel build failed with exit code $LASTEXITCODE"
    }

    $wheels = @(Get-ChildItem -LiteralPath $wheelDirectory -File -Filter "huhac_media-*.whl")
    if ($wheels.Count -ne 1) {
        throw "Expected one huhac-media wheel, found $($wheels.Count)"
    }
    $wheel = $wheels[0]

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $wheelZip = [System.IO.Compression.ZipFile]::OpenRead($wheel.FullName)
    try {
        $wheelNames = @($wheelZip.Entries | ForEach-Object FullName)
        $unwanted = @($wheelNames | Where-Object { $_ -match '(^|/)(tests?|docs?|\.git|__pycache__)(/|$)|\.(pyc|pyo)$' })
        if ($unwanted.Count -gt 0) {
            throw "Forbidden development content in wheel: $($unwanted[0..([Math]::Min(19, $unwanted.Count - 1))] -join ', ')"
        }
        foreach ($required in @("huhac_media/cli.py", "media_desk/static/library.js", "media_desk/templates/library.html")) {
            if (-not ($wheelNames -contains $required)) {
                throw "Required runtime content missing from wheel: $required"
            }
        }
        foreach ($entry in $wheelZip.Entries) {
            $entryStream = $entry.Open()
            try { $entryStream.CopyTo([System.IO.Stream]::Null) }
            finally { $entryStream.Dispose() }
        }
        Write-Output "Validated runtime wheel: $($wheelNames.Count) entries"
    }
    finally {
        $wheelZip.Dispose()
    }

    Copy-Item -LiteralPath $wheel.FullName -Destination $bundleDirectory
    Copy-Item -LiteralPath $configExample -Destination (Join-Path $bundleDirectory "config.example.toml")
    Copy-Item -LiteralPath $modelNotice -Destination (Join-Path $bundleDirectory "THIRD_PARTY_MODELS.md")

    $installText = @"
HUHAC Media runtime bundle $version
==================================

Requires Python 3.11 or newer.

1. Create and activate a clean virtual environment:

   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1

2. Install the required runtime profile:

   Core ingest:
   python -m pip install ".\$($wheel.Name)"

   Media Desk:
   python -m pip install ".\$($wheel.Name)[media-desk]"

   Optional processors can use [video-keyframes] or [faces].

3. Start Media Desk, for example:

   media-desk --workspace "D:\HUHAC\Workspace"

ExifTool and FFmpeg/ffprobe are external executables and must be installed
separately when the selected component requires them.

This bundle intentionally excludes tests, development dependencies, Git data,
documentation sources, virtual environments, caches, local media, workspaces,
and generated output.
"@
    Set-Content -LiteralPath (Join-Path $bundleDirectory "INSTALL.txt") -Value $installText -Encoding UTF8

    $revision = (& git -C $repoRoot rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -ne 0) { $revision = $null }
    $dirty = $false
    if ($revision) {
        $gitStatus = @(& git -C $repoRoot status --porcelain --untracked-files=normal)
        $dirty = $gitStatus.Count -gt 0
    }
    $wheelHash = (Get-FileHash -LiteralPath $wheel.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest = [ordered]@{
        bundle_format = 1
        project = "huhac-media"
        version = $version
        generated_at_utc = [DateTime]::UtcNow.ToString("o")
        source_revision = $revision
        source_dirty = $dirty
        wheel = $wheel.Name
        wheel_sha256 = $wheelHash
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $bundleDirectory "manifest.json") -Encoding UTF8

    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    if (Test-Path -LiteralPath $bundlePath) {
        Remove-Item -LiteralPath $bundlePath -Force
    }
    Compress-Archive -LiteralPath $bundleDirectory -DestinationPath $bundlePath -CompressionLevel Optimal

    $bundleZip = [System.IO.Compression.ZipFile]::OpenRead($bundlePath)
    try {
        $outerNames = @($bundleZip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
        $expectedFiles = @($wheel.Name, "config.example.toml", "THIRD_PARTY_MODELS.md", "INSTALL.txt", "manifest.json")
        foreach ($expected in $expectedFiles) {
            if (-not ($outerNames -contains "$bundleName/$expected")) {
                throw "Runtime bundle is missing $expected"
            }
        }
        if ($outerNames | Where-Object { $_ -match '(^|/)(tests?|docs?|\.git|__pycache__)(/|$)|\.(pyc|pyo)$' }) {
            throw "Runtime bundle contains forbidden development content"
        }
    }
    finally {
        $bundleZip.Dispose()
    }

    $bundleHash = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output "Runtime bundle: $bundlePath"
    Write-Output "SHA256: $bundleHash"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
