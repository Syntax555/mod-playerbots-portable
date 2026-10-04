[CmdletBinding()]
param(
    [string]$DistDir = 'dist',
    [string]$VisualStudioPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $DistDir -PathType Container) -or -not (Test-Path (Join-Path $DistDir 'mysql/bin') -PathType Container)) {
    throw 'Build the distribution before copying the Windows runtime.'
}
if (-not $VisualStudioPath) {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { throw 'Visual Studio Installer vswhere.exe was not found.' }
    $VisualStudioPath = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $VisualStudioPath) { throw 'Visual Studio C++ redistributable location not found.' }
}
$crt = Get-ChildItem "$VisualStudioPath\VC\Redist\MSVC\*\x64\Microsoft.VC*.CRT" -Directory |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $crt) { throw 'Visual C++ x64 CRT directory not found.' }
foreach ($required in @('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll')) {
    if (-not (Test-Path (Join-Path $crt.FullName $required))) { throw "Visual C++ runtime is missing $required" }
}
Copy-Item "$($crt.FullName)\*.dll" $DistDir -Force
Copy-Item "$($crt.FullName)\*.dll" (Join-Path $DistDir 'mysql/bin') -Force
Write-Host "Bundled Visual C++ runtime from $($crt.FullName) into $DistDir and mysql/bin."
