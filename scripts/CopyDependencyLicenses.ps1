[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DistDir,
    [string]$MySQLRootDir = $env:MYSQL_ROOT_DIR,
    [string]$OpenSSLRootDir = $env:OPENSSL_ROOT_DIR,
    [string]$BoostRootDir = $env:BOOST_ROOT_DIR,
    [switch]$NoNetwork
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Resolve-DependencyDirectory([string]$Path, [string]$Name) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Name dependency directory is missing: $Path"
    }
    return (Get-Item -LiteralPath $Path).FullName
}

function Get-NoticeFiles([string]$Directory, [bool]$Recurse = $true) {
    return @(Get-ChildItem -LiteralPath $Directory -File -Recurse:$Recurse |
        Where-Object { $_.Name -match '^(?:(?:LICEN[CS]E|COPYING|NOTICE|COPYRIGHT)(?:[._-].*)?|INFO_(?:BIN|SRC))$' } |
        Sort-Object FullName -Unique)
}

function Test-LicenseText($Files, [string]$License) {
    foreach ($file in $Files) {
        $text = [System.IO.File]::ReadAllText($file.FullName)
        if ($License -eq 'GPL2' -and $text -match 'GNU\s+GENERAL\s+PUBLIC\s+LICENSE' -and
            $text -match 'Version\s+2,\s+June\s+1991' -and $text -match 'TERMS\s+AND\s+CONDITIONS') { return $true }
        if ($License -eq 'Apache2' -and $text -match 'Apache\s+License' -and
            $text -match 'Version\s+2[.]0' -and $text -match 'TERMS\s+AND\s+CONDITIONS') { return $true }
    }
    return $false
}

function Copy-Notices($Files, [string]$SourceDirectory, [string]$Destination) {
    foreach ($file in $Files) {
        if ($file.Length -eq 0) { throw "Dependency notice is empty: $($file.FullName)" }
        $relative = [System.IO.Path]::GetRelativePath($SourceDirectory, $file.FullName)
        $target = Join-Path $Destination $relative
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target))
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }
}

$mysqlRoot = Resolve-DependencyDirectory $MySQLRootDir 'MySQL'
$opensslRoot = Resolve-DependencyDirectory $OpenSSLRootDir 'OpenSSL'
$boostRoot = Resolve-DependencyDirectory $BoostRootDir 'Boost'

$boostLicense = Join-Path $boostRoot 'LICENSE_1_0.txt'
if (-not (Test-Path -LiteralPath $boostLicense -PathType Leaf)) {
    throw "Boost license is missing: $boostLicense"
}
$boostText = [System.IO.File]::ReadAllText($boostLicense)
if ($boostText -notmatch 'Boost\s+Software\s+License' -or $boostText -notmatch 'Version\s+1[.]0') {
    throw "Boost LICENSE_1_0.txt does not contain the Boost Software License: $boostLicense"
}

$mysqlNotices = @(Get-NoticeFiles $mysqlRoot)
if (-not (Test-LicenseText $mysqlNotices 'GPL2')) {
    throw "MySQL GPL version 2 license text is missing from $mysqlRoot. Retain the original package's license files."
}

# Windows packages commonly place notices beside the x64 directory. Only search
# that package parent for an architecture root; do not scan arbitrary ancestors.
$opensslPackageRoot = $opensslRoot
if ([System.IO.Path]::GetFileName($opensslRoot) -match '^(?:x64|x86|win64|win32|arm64)$') {
    $opensslPackageRoot = [System.IO.Path]::GetDirectoryName($opensslRoot)
}
$opensslNotices = @(Get-NoticeFiles $opensslPackageRoot)
$upstreamLicense = $null
$upstreamLicenseUrl = 'https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.7/LICENSE.txt'
if (-not (Test-LicenseText $opensslNotices 'Apache2')) {
    $header = Join-Path $opensslRoot 'include/openssl/opensslv.h'
    if (-not (Test-Path -LiteralPath $header -PathType Leaf)) {
        throw "OpenSSL license is missing and its version header is unavailable: $header"
    }
    $versionHeader = [System.IO.File]::ReadAllText($header)
    if ($versionHeader -notmatch 'OPENSSL_VERSION_TEXT\s+"OpenSSL\s+3[.]5[.]7(?:\s|\")') {
        throw 'OpenSSL package lacks its Apache license. The available fallback applies only to OpenSSL 3.5.7.'
    }
    if ($NoNetwork) { throw 'OpenSSL Apache license is missing; network fallback is disabled.' }
    # Preserve provider notices separately. The upstream license supplies only
    # OpenSSL's terms and does not license any additional provider material.
    $upstreamLicense = (Invoke-WebRequest -Uri $upstreamLicenseUrl -TimeoutSec 60).Content
    if ($upstreamLicense -is [byte[]]) { $upstreamLicense = [System.Text.Encoding]::UTF8.GetString($upstreamLicense) }
    if ($upstreamLicense -notmatch 'Apache\s+License' -or $upstreamLicense -notmatch 'Version\s+2[.]0' -or
        $upstreamLicense -notmatch 'TERMS\s+AND\s+CONDITIONS') {
        throw 'The OpenSSL upstream download did not contain the Apache version 2 license.'
    }
}

# Validate every selected notice before replacing any previously packaged files.
foreach ($file in @($mysqlNotices) + @($opensslNotices) + @(Get-Item -LiteralPath $boostLicense)) {
    if ($file.Length -eq 0) { throw "Dependency notice is empty: $($file.FullName)" }
}

$licenseRoot = Join-Path ([System.IO.Path]::GetFullPath($DistDir)) 'licenses'
foreach ($name in @('mysql', 'openssl', 'boost')) {
    $destination = Join-Path $licenseRoot $name
    if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Recurse -Force }
    [void][System.IO.Directory]::CreateDirectory($destination)
}
Copy-Notices $mysqlNotices $mysqlRoot (Join-Path $licenseRoot 'mysql')
Copy-Notices $opensslNotices $opensslPackageRoot (Join-Path $licenseRoot 'openssl')
Copy-Item -LiteralPath $boostLicense -Destination (Join-Path $licenseRoot 'boost/LICENSE_1_0.txt') -Force
if ($null -ne $upstreamLicense) {
    $upstreamDirectory = Join-Path $licenseRoot 'openssl/upstream'
    [void][System.IO.Directory]::CreateDirectory($upstreamDirectory)
    [System.IO.File]::WriteAllText((Join-Path $upstreamDirectory 'LICENSE.txt'), $upstreamLicense, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $upstreamDirectory 'SOURCE.txt'), "$upstreamLicenseUrl`n", [System.Text.UTF8Encoding]::new($false))
}
Write-Host "Preserved MySQL, OpenSSL and Boost license notices under $licenseRoot."
