param(
    [switch]$SkipRegister,
    [switch]$SkipDeploy,
    [switch]$Minimal
)

$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$proj = Join-Path $here "ProBridge.csproj"
$out = Join-Path $here "bin\Release"
$stage = Join-Path $here ("bin\stage_" + (Get-Date -Format "HHmmssfff"))
$zip = Join-Path $here "bin\ProBridge.esriAddinX"
$tmpZip = Join-Path $here "bin\ProBridge.zip"

$guid = "{8b1d4e2a-6f3c-4a19-9d7e-2c5b8f0a1e34}"
$addinDir = Join-Path $env:USERPROFILE "Documents\ArcGIS\AddIns\ArcGISPro\$guid"
$cacheDir = Join-Path $env:LOCALAPPDATA "ESRI\ArcGISPro\AssemblyCache\$guid"

$extra = @()
if ($Minimal) { $extra = @("-p:Minimal=true") }

dotnet build $proj -c Release -v m @extra
if ($LASTEXITCODE -ne 0) { throw "build failed" }

New-Item -ItemType Directory -Path (Join-Path $stage "Install") -Force | Out-Null
Copy-Item (Join-Path $out "Config.daml") $stage -Force
Copy-Item (Join-Path $out "ProBridge.dll") (Join-Path $stage "Install") -Force
if (Test-Path (Join-Path $out "Images")) {
    Copy-Item (Join-Path $out "Images") $stage -Recurse -Force
}

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $tmpZip -Force
Move-Item $tmpZip $zip -Force

Write-Host "packaged: $zip"

if (-not $SkipRegister) {
    $reg = "C:\Program Files\ArcGIS\Pro\bin\RegisterAddIn.exe"
    if (-not (Test-Path $reg)) { throw "RegisterAddIn.exe not found" }
    & $reg $zip /s
    Write-Host "registered (exit $LASTEXITCODE)"
}

# Pro loads the add-in assembly from AssemblyCache, NOT from Install\.
# Close ArcGIS Pro before deploying, otherwise the copy fails.
if (-not $SkipDeploy) {
    New-Item -ItemType Directory -Path (Join-Path $addinDir "Install") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $addinDir "Images") -Force | Out-Null
    New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

    Copy-Item (Join-Path $out "Config.daml") $addinDir -Force
    Copy-Item (Join-Path $out "ProBridge.dll") (Join-Path $addinDir "Install") -Force
    if (Test-Path (Join-Path $out "Images")) {
        Copy-Item (Join-Path $out "Images\*") (Join-Path $addinDir "Images") -Force
    }
    Copy-Item (Join-Path $out "ProBridge.dll") $cacheDir -Force

    Write-Host "deployed to: $addinDir"
    Write-Host "deployed to: $cacheDir"
}
