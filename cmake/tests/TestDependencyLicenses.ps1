param([string]$SourceDir = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$scriptPath = Join-Path $SourceDir 'scripts/CopyDependencyLicenses.ps1'
$fixture = Join-Path ([System.IO.Path]::GetTempPath()) ("dependency licenses [fixture] " + [guid]::NewGuid().ToString('N'))
$mysql = Join-Path $fixture 'MySQL'
$opensslPackage = Join-Path $fixture 'OpenSSL'
$openssl = Join-Path $opensslPackage 'x64'
$boost = Join-Path $fixture 'Boost'
$dist = Join-Path $fixture 'dist'

function Write-Fixture([string]$Path, [string]$Text) {
    [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($Path))
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}
function Assert-SameBytes([string]$Source, [string]$Target) {
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf) -or
        (Get-FileHash -LiteralPath $Source).Hash -ne (Get-FileHash -LiteralPath $Target).Hash) {
        throw "Notice was not preserved byte for byte: $Target"
    }
}
function Assert-Fails([scriptblock]$Action, [string]$Message) {
    $failed = $false
    try { & $Action } catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
        $failed = $true
    }
    if (-not $failed) { throw "Expected failure containing: $Message" }
}

try {
    [void][System.IO.Directory]::CreateDirectory($mysql)
    Copy-Item -LiteralPath (Join-Path $SourceDir 'licenses/GPL-2.0.txt') -Destination (Join-Path $mysql 'LICENSE')
    Write-Fixture (Join-Path $mysql 'docs/INFO_BIN') "MySQL build provenance`r`n"
    Write-Fixture (Join-Path $mysql 'docs/INFO_SRC') "MySQL source provenance`n"
    Write-Fixture (Join-Path $mysql 'docs/third-party/NOTICE.txt') "Original third-party notices`r`n"
    Write-Fixture (Join-Path $mysql 'bin/mysql.exe') 'Not a license'
    Write-Fixture (Join-Path $boost 'LICENSE_1_0.txt') "Boost Software License - Version 1.0`r`nUnmodified fixture text`r`n"
    Write-Fixture (Join-Path $openssl 'include/openssl/opensslv.h') '#define OPENSSL_VERSION_TEXT "OpenSSL 3.5.7 9 Jun 2026"'
    Write-Fixture (Join-Path $opensslPackage 'LICENSE.txt') "Separate provider terms`r`nDo not replace or infer a grant.`r`n"
    $apacheText = "Apache License`nVersion 2.0, January 2004`nTERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION`n"
    $apacheFile = Join-Path $opensslPackage 'docs/LICENSE_OPENSSL.txt'
    Write-Fixture $apacheFile $apacheText

    & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork
    foreach ($relative in @('LICENSE', 'docs/INFO_BIN', 'docs/INFO_SRC', 'docs/third-party/NOTICE.txt')) {
        Assert-SameBytes (Join-Path $mysql $relative) (Join-Path $dist "licenses/mysql/$relative")
    }
    Assert-SameBytes (Join-Path $opensslPackage 'LICENSE.txt') (Join-Path $dist 'licenses/openssl/LICENSE.txt')
    Assert-SameBytes $apacheFile (Join-Path $dist 'licenses/openssl/docs/LICENSE_OPENSSL.txt')
    Assert-SameBytes (Join-Path $boost 'LICENSE_1_0.txt') (Join-Path $dist 'licenses/boost/LICENSE_1_0.txt')
    if (Test-Path -LiteralPath (Join-Path $dist 'licenses/mysql/bin/mysql.exe')) { throw 'Copied a runtime binary as a license.' }

    # Reassembly removes stale notices while keeping unrelated licenses intact.
    Write-Fixture (Join-Path $dist 'licenses/mysql/stale.txt') 'Stale license'
    Write-Fixture (Join-Path $dist 'licenses/unrelated/NOTICE.txt') 'Keep this notice'
    & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork
    if (Test-Path -LiteralPath (Join-Path $dist 'licenses/mysql/stale.txt')) { throw 'Stale dependency notice survived reassembly.' }
    if (-not (Test-Path -LiteralPath (Join-Path $dist 'licenses/unrelated/NOTICE.txt'))) { throw 'Unrelated notices were removed.' }

    # Missing or empty source notices fail before existing output is replaced.
    Write-Fixture (Join-Path $dist 'licenses/mysql/sentinel.txt') 'Existing output'
    Move-Item -LiteralPath (Join-Path $boost 'LICENSE_1_0.txt') -Destination (Join-Path $boost 'saved.bsl')
    Assert-Fails { & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork } 'Boost license is missing'
    Move-Item -LiteralPath (Join-Path $boost 'saved.bsl') -Destination (Join-Path $boost 'LICENSE_1_0.txt')
    Move-Item -LiteralPath (Join-Path $mysql 'LICENSE') -Destination (Join-Path $mysql 'saved.gpl')
    Assert-Fails { & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork } 'MySQL GPL version 2 license text is missing'
    if (-not (Test-Path -LiteralPath (Join-Path $dist 'licenses/mysql/sentinel.txt'))) { throw 'Validation failure replaced existing output.' }
    Move-Item -LiteralPath (Join-Path $mysql 'saved.gpl') -Destination (Join-Path $mysql 'LICENSE')
    Write-Fixture (Join-Path $mysql 'docs/NOTICE.empty') ''
    Assert-Fails { & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork } 'Dependency notice is empty'
    Remove-Item -LiteralPath (Join-Path $mysql 'docs/NOTICE.empty')

    # A provider license alone does not satisfy OpenSSL's license requirement.
    Remove-Item -LiteralPath $apacheFile
    Assert-Fails { & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork } 'network fallback is disabled'
    Write-Fixture (Join-Path $openssl 'include/openssl/opensslv.h') '#define OPENSSL_VERSION_TEXT "OpenSSL 3.5.8 9 Jun 2026"'
    Assert-Fails { & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost -NoNetwork } 'only to OpenSSL 3.5.7'
    Write-Fixture (Join-Path $openssl 'include/openssl/opensslv.h') '#define OPENSSL_VERSION_TEXT "OpenSSL 3.5.7 9 Jun 2026"'

    # Exercise fallback without network access, retaining separate provider terms.
    $global:DependencyLicenseFixtureResponse = $apacheText
    $global:DependencyLicenseFixtureCalls = 0
    function global:Invoke-WebRequest {
        param([string]$Uri, [int]$TimeoutSec)
        if ($Uri -cne 'https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.7/LICENSE.txt') {
            throw "Unexpected license download: $Uri"
        }
        $global:DependencyLicenseFixtureCalls++
        return [pscustomobject]@{ Content = $global:DependencyLicenseFixtureResponse }
    }
    & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost
    if ($global:DependencyLicenseFixtureCalls -ne 1) { throw 'OpenSSL fallback was not requested exactly once.' }
    Assert-SameBytes (Join-Path $opensslPackage 'LICENSE.txt') (Join-Path $dist 'licenses/openssl/LICENSE.txt')
    if ([System.IO.File]::ReadAllText((Join-Path $dist 'licenses/openssl/upstream/LICENSE.txt')) -cne $apacheText) { throw 'Upstream fallback text changed.' }
    $global:DependencyLicenseFixtureResponse = '<html>Not a license</html>'
    Assert-Fails { & $scriptPath -DistDir $dist -MySQLRootDir $mysql -OpenSSLRootDir $openssl -BoostRootDir $boost } 'did not contain the Apache version 2 license'

    Write-Host 'Dependency license packaging checks passed.'
} finally {
    Remove-Item Function:\Invoke-WebRequest -ErrorAction SilentlyContinue
    Remove-Variable DependencyLicenseFixtureResponse, DependencyLicenseFixtureCalls -Scope Global -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
