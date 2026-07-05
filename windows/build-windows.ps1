<#
.SYNOPSIS
  Build frame for Windows as a single, self-contained .exe (no runtime install).

.EXAMPLE
  ./build-windows.ps1
  ./build-windows.ps1 -Runtime win-arm64
#>
param(
    [string]$Runtime = "win-x64",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$proj = Join-Path $PSScriptRoot "Wpeek/Wpeek.csproj"

Write-Host "Building Frame ($Runtime, $Configuration)..." -ForegroundColor Cyan

dotnet publish $proj `
    -c $Configuration `
    -r $Runtime `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:EnableCompressionInSingleFile=true

$out = Join-Path $PSScriptRoot "Wpeek/bin/$Configuration/net8.0-windows10.0.19041.0/$Runtime/publish/frame.exe"
if (Test-Path $out) {
    Write-Host "`nDone. Single-file executable:" -ForegroundColor Green
    Write-Host "  $out"
    Write-Host "`nCopy it anywhere and run it — no dependencies required."
} else {
    Write-Warning "Build finished but frame.exe was not found at the expected path."
}
