# Run with PowerShell 7+: pwsh -File cmake/tests/TestPortableZip.ps1 -CMake cmake
# Uses small temporary source/distribution fixtures; no server build or download.
[CmdletBinding()]
param([string]$CMake = 'cmake')

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Add-Type -AssemblyName System.IO.Compression.FileSystem
$cmakeRoot = Split-Path $PSScriptRoot -Parent
$verifier = Join-Path $cmakeRoot 'VerifyPortableZip.ps1'
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('portable-zip-tests-' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $temporaryRoot 'source with spaces'
$dist = Join-Path $temporaryRoot 'distribution with spaces'
$script:passed = 0

function Write-FixtureFile([string]$Path, [byte[]]$Bytes) {
    [void][System.IO.Directory]::CreateDirectory((Split-Path $Path -Parent))
    [System.IO.File]::WriteAllBytes($Path, $Bytes)
}

function Write-FixtureText([string]$Path, [string]$Text = "fixture`n") {
    Write-FixtureFile $Path ([System.Text.Encoding]::UTF8.GetBytes($Text))
}

function Assert-Condition([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Invoke-Assembly {
    & $CMake "-DPORTABLE_SOURCE_DIR=$source" "-DPORTABLE_DIST_DIR=$dist" "-DPORTABLE_RELEASE_REVISION=$revision" "-DPACKAGE_VERSION=latest" -P (Join-Path $cmakeRoot 'AssembleDistribution.cmake')
    if ($LASTEXITCODE -ne 0) { throw "Fixture assembly failed: $LASTEXITCODE" }
}

function New-FixtureZip(
    [string]$Path,
    [hashtable]$Replacements = @{},
    [string[]]$Omit = @(),
    [object[]]$ExtraEntries = @(),
    [string]$Prefix = ''
) {
    $archive = [System.IO.Compression.ZipFile]::Open($Path, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($name in $script:baseline.Keys) {
            if ($name -cin $Omit) { continue }
            $bytes = $script:baseline[$name]
            if ($Replacements.ContainsKey($name)) { $bytes = $Replacements[$name] }
            $entry = $archive.CreateEntry("$Prefix$name")
            $stream = $entry.Open()
            try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
        }
        foreach ($extra in $ExtraEntries) {
            $entry = $archive.CreateEntry($extra.Name)
            if ($extra.ContainsKey('Attributes')) { $entry.ExternalAttributes = $extra.Attributes }
            $bytes = [byte[]]@()
            if ($extra.ContainsKey('Bytes')) { $bytes = $extra.Bytes }
            $stream = $entry.Open()
            try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
        }
    } finally {
        $archive.Dispose()
    }
}

function Test-Zip([string]$Name, [string]$ZipPath, [string]$ExpectedError = '') {
    $failure = ''
    try { & $verifier -ZipPath $ZipPath -RepositoryRoot $source -ExpectedRevision ('a' * 40) } catch { $failure = $_.Exception.Message }
    if ($ExpectedError) {
        if (-not $failure -or $failure -notmatch $ExpectedError) {
            throw "$Name expected '$ExpectedError', got '$failure'"
        }
    } elseif ($failure) {
        throw "$Name failed: $failure"
    }
    $script:passed++
    Write-Host "PASS: $Name"
}

function Test-NegativeZip(
    [string]$Name,
    [string]$ExpectedError,
    [hashtable]$Replacements = @{},
    [string[]]$Omit = @(),
    [object[]]$ExtraEntries = @()
) {
    $zip = Join-Path $temporaryRoot ('negative-' + [guid]::NewGuid().ToString('N') + '.zip')
    New-FixtureZip $zip $Replacements $Omit $ExtraEntries
    Test-Zip $Name $zip $ExpectedError
}

try {
    $revision = 'a' * 40
    $lock = [ordered]@{
        schemaVersion = 1
        core = @{ name = 'azerothcore-wotlk'; revision = $revision; source = 'azerothcore-wotlk' }
        modules = @(@{ name = 'mod-fixture'; revision = $revision; patches = @('patches/fixture.patch') })
        clientAddons = @(@{ name = 'MultiBot'; revision = $revision; toc = 'MultiBot.toc'; license = 'LICENSE'; interface = 30300 })
    }
    Write-FixtureText (Join-Path $source 'versions.lock.json') ($lock | ConvertTo-Json -Depth 5)
    foreach ($name in @('README.md', 'LICENSE', 'docs/vanilla-config-audit.md', 'docs/module-versions.md',
        'docs/changing-expansions.md', 'docs/earned-bot-brackets.md', 'docs/earned-auctions.md',
        'patches/fixture.patch', 'CONTRIBUTING.md', 'docs/building.md')) {
        Write-FixtureText (Join-Path $source $name)
    }
    [void][System.IO.Directory]::CreateDirectory((Join-Path $source 'licenses'))
    $profiles = @('playerbots', 'worldserver', 'individualProgression', 'AutoBalance', 'mod_ahbot',
        'mod_dungeon_clear', 'mod-quest-loot-party', 'MultiBotBridge', 'mod_token_turnin')
    foreach ($profile in $profiles) {
        Write-FixtureText (Join-Path $source "cmd/startup/profiles/$profile.conf") "$profile = fixture`n"
    }
    Write-FixtureText (Join-Path $source 'azerothcore-wotlk/LICENSE')
    foreach ($app in @('authserver', 'worldserver')) {
        Write-FixtureText (Join-Path $source "azerothcore-wotlk/src/server/apps/$app/$app.conf.dist")
    }
    foreach ($name in @('base/db_auth/base.sql', 'base/db_world/base.sql', 'updates/db_world/current.sql')) {
        Write-FixtureText (Join-Path $source "azerothcore-wotlk/data/sql/$name") "SELECT 1;`n"
    }
    $moduleSql = Join-Path $source 'azerothcore-wotlk/modules/mod-fixture/data/sql/db_world/current.sql'
    Write-FixtureText $moduleSql "SELECT 1;`n"
    Write-FixtureText (Join-Path $source 'azerothcore-wotlk/modules/mod-fixture/src/fixture.cpp')
    Write-FixtureText (Join-Path $source 'azerothcore-wotlk/modules/mod-fixture/conf/mod_fixture.conf.dist')
    Write-FixtureText (Join-Path $source 'azerothcore-wotlk/modules/mod-fixture/LICENSE')
    $addon = Join-Path $source '.module-cache/prepared-addons/MultiBot'
    Write-FixtureText (Join-Path $addon 'MultiBot.toc') "## Interface: 30300`nCore\MultiBot.lua`n"
    Write-FixtureText (Join-Path $addon 'Core/MultiBot.lua') "print('good')`n"
    Write-FixtureText (Join-Path $addon 'README.md')
    Write-FixtureText (Join-Path $addon 'LICENSE')
    Write-FixtureText (Join-Path $addon 'SOURCE_REVISION.txt') "$revision`n"
    Write-FixtureText (Join-Path $addon '.portable-source') 'generated fixture'
    Write-FixtureFile (Join-Path $addon 'Textures/icon.blp') ([byte[]]@(0, 255, 128, 0))
    Write-FixtureFile (Join-Path $addon '.hidden.bin') ([byte[]]@(1, 2, 3))
    Write-FixtureFile (Join-Path $addon 'empty.txt') ([byte[]]@())

    # Reusing an existing distribution must remove obsolete SQL, including removed
    # modules, without deleting non-SQL module data, live databases or user configs.
    foreach ($name in @('src/data/sql/updates/db_world/obsolete.sql',
        'src/modules/mod-fixture/data/sql/db_world/obsolete.sql',
        'src/modules/mod-removed/data/sql/db_world/obsolete.sql', 'addons/OldAddon/OldAddon.lua',
        'defaults/worldserver.conf', 'licenses/MultiBot/LICENSE', 'CONTRIBUTING.md', 'docs/building.md')) {
        Write-FixtureText (Join-Path $dist $name) 'obsolete export'
    }
    $preserved = @('mysql/data/user.db', 'mysql/my.cnf', 'configs/worldserver.conf',
        'configs/modules/mod_fixture.conf', 'src/modules/mod-removed/keep.txt')
    foreach ($name in $preserved) { Write-FixtureText (Join-Path $dist $name) "preserve $name" }
    $oldCoreSql = Join-Path $dist 'src/data/sql/updates/db_world/current.sql'
    $oldModuleSql = Join-Path $dist 'src/modules/mod-fixture/data/sql/db_world/current.sql'
    Write-FixtureText $oldCoreSql "SELECT 2;`n"
    Write-FixtureText $oldModuleSql "SELECT 2;`n"
    $sameTimestamp = [datetime]::UtcNow.AddDays(-2)
    foreach ($path in @($oldCoreSql, $oldModuleSql,
        (Join-Path $source 'azerothcore-wotlk/data/sql/updates/db_world/current.sql'), $moduleSql)) {
        [System.IO.File]::SetLastWriteTimeUtc($path, $sameTimestamp)
    }
    Invoke-Assembly
    foreach ($name in @('src/data/sql/updates/db_world/obsolete.sql',
        'src/modules/mod-fixture/data/sql/db_world/obsolete.sql',
        'src/modules/mod-removed/data/sql/db_world/obsolete.sql', 'addons', 'defaults',
        'licenses/MultiBot', 'CONTRIBUTING.md', 'docs/building.md')) {
        Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $dist $name))) "Assembly retained $name"
    }
    foreach ($path in @($oldCoreSql, $oldModuleSql)) {
        Assert-Condition ([System.IO.File]::ReadAllText($path) -ceq "SELECT 1;`n") "Assembly retained stale equal-timestamp SQL: $path"
    }
    foreach ($name in $preserved) {
        Assert-Condition ([System.IO.File]::ReadAllText((Join-Path $dist $name)) -ceq "preserve $name") "Assembly modified $name"
    }
    Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $dist 'addons'))) 'Assembly duplicated standalone client addons'
    Remove-Item -LiteralPath (Join-Path $source '.module-cache/prepared-addons') -Recurse -Force
    Remove-Item -LiteralPath (Join-Path $source 'azerothcore-wotlk/modules/mod-fixture/data/sql') -Recurse -Force
    Invoke-Assembly
    Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $dist 'src/modules/mod-fixture/data/sql'))) 'Assembly retained SQL after the module stopped supplying it'
    Write-FixtureText $moduleSql "SELECT 1;`n"
    Invoke-Assembly
    # User data is preserved by assembly, but must never enter a downloadable ZIP.
    foreach ($name in $preserved) { Remove-Item -LiteralPath (Join-Path $dist $name) -Force }
    Remove-Item -LiteralPath (Join-Path $dist 'mysql/data') -Recurse -Force
    Write-Host 'PASS: clean runtime exports preserve user data and need no prepared addon files'
    $script:passed++

    # Stub the Windows runtime files; this suite tests packaging, not PE execution.
    $runtimeFiles = @('startup.exe', 'authserver.exe', 'worldserver.exe',
        'mysql/bin/mysqld.exe', 'mysql/bin/mysql.exe', 'mysql/bin/mysqladmin.exe',
        'libmysql.dll', 'libcrypto-3-x64.dll', 'libssl-3-x64.dll',
        'vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
        'mysql/bin/vcruntime140.dll', 'mysql/bin/vcruntime140_1.dll', 'mysql/bin/msvcp140.dll')
    foreach ($name in $runtimeFiles) { Write-FixtureText (Join-Path $dist $name) }
    foreach ($profile in $profiles | Where-Object { $_ -ne 'worldserver' }) {
        Write-FixtureText (Join-Path $dist "configs/modules/$profile.conf.dist")
    }
    Write-FixtureText (Join-Path $dist 'mysql/bin/mysqldump.exe')
    Write-FixtureText (Join-Path $dist 'mysql/bin/dependency.dll')
    $optionalFiles = @('dbimport.exe', 'map_extractor.exe', 'vmap4_extractor.exe',
        'vmap4_assembler.exe', 'mmaps_generator.exe', 'mmaps-config.yaml',
        'configs/dbimport.conf.dist', 'dbimport.conf.dist')
    foreach ($name in $optionalFiles) { Write-FixtureText (Join-Path $dist $name) }
    & $CMake "-DPORTABLE_DIST_DIR=$dist" -P (Join-Path $cmakeRoot 'PrunePortableDistribution.cmake')
    if ($LASTEXITCODE -ne 0) { throw 'Fixture pruning failed.' }
    Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $dist 'mysql/bin/mysqldump.exe'))) 'Unused MySQL executable survived pruning'
    Assert-Condition (Test-Path -LiteralPath (Join-Path $dist 'mysql/bin/dependency.dll')) 'MySQL runtime dependency was pruned'
    foreach ($name in $optionalFiles) {
        Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $dist $name))) "Unused tool survived pruning: $name"
    }
    $script:baseline = [System.Collections.Generic.Dictionary[string, byte[]]]::new([System.StringComparer]::Ordinal)
    foreach ($file in Get-ChildItem -LiteralPath $dist -Recurse -File -Force) {
        $relative = [System.IO.Path]::GetRelativePath($dist, $file.FullName).Replace('\', '/')
        $script:baseline.Add($relative, [System.IO.File]::ReadAllBytes($file.FullName))
    }
    $plainZip = Join-Path $temporaryRoot 'plain.zip'
    New-FixtureZip $plainZip -ExtraEntries @(@{ Name = 'licenses/empty/' })
    Test-Zip 'plain archive contains server runtime and no duplicate client files' $plainZip

    $fallbackZip = Join-Path $temporaryRoot 'cmake-fallback.zip'
    Push-Location $dist
    try {
        & $CMake -E tar cf $fallbackZip --format=zip .
        if ($LASTEXITCODE -ne 0) { throw 'CMake ZIP fallback failed.' }
    } finally { Pop-Location }
    Test-Zip 'actual CMake ZIP fallback' $fallbackZip
    # CMake/libarchive versions differ in whether they preserve the ./ entries.
    $prefixedZip = Join-Path $temporaryRoot 'prefixed.zip'
    New-FixtureZip $prefixedZip -Prefix './' -ExtraEntries @(@{ Name = './' }, @{ Name = './docs/' })
    Test-Zip 'literal ./ prefix including ./ root directory' $prefixedZip

    foreach ($unsafe in @('../README.md', '/README.md', './/README.md', '././README.md',
        'docs/../README.md', 'docs/./README.md', 'docs\README.md', 'C:/README.md',
        'README.md:stream', 'docs//README.md', 'docs/name./README.md', 'docs/name /README.md',
        'docs/CON.txt', 'docs/bad?.txt')) {
        Test-NegativeZip "unsafe path $unsafe" 'Unsafe path' -ExtraEntries @(@{ Name = $unsafe })
    }
    Test-NegativeZip 'traversal README cannot satisfy required root README' 'Unsafe path' -Omit @('README.md') -ExtraEntries @(@{ Name = '../README.md'; Bytes = $script:baseline['README.md'] })
    foreach ($duplicate in @('README.md', './README.md', 'readme.md', './readme.md')) {
        Test-NegativeZip "duplicate normalized path $duplicate" 'Duplicate path' -ExtraEntries @(@{ Name = $duplicate })
    }
    Test-NegativeZip 'file and directory duplicate' 'Duplicate path' -ExtraEntries @(@{ Name = 'README.md/' })
    Test-NegativeZip 'file shadows an asset directory' 'File/directory collision' -ExtraEntries @(@{ Name = 'docs'; Bytes = [byte[]]@(1) })
    Test-NegativeZip 'nonempty directory entry' 'Nonempty directory' -ExtraEntries @(@{ Name = 'extra/'; Bytes = [byte[]]@(1) })
    $symlinkAttributes = [int](([int64]0xA1FF -shl 16) - 0x100000000)
    Test-NegativeZip 'Unix symbolic link' 'Symbolic link' -ExtraEntries @(@{ Name = 'link'; Bytes = [byte[]]@(1); Attributes = $symlinkAttributes })
    Test-NegativeZip 'Windows reparse point' 'Symbolic link' -ExtraEntries @(@{ Name = 'link'; Attributes = 0x400 })
    foreach ($forbidden in @('.git/config', './.git/config', 'mysql/bin/debug.pdb', 'library.lib', 'installer.msix')) {
        Test-NegativeZip "existing metadata/debug guard $forbidden" 'Unexpected source/debug/installer' -ExtraEntries @(@{ Name = $forbidden })
    }

    foreach ($redundant in @('addons/MultiBot/Core.lua', 'defaults/worldserver.conf',
        'CONTRIBUTING.md', 'docs/building.md', 'mysql/include/mysql.h', 'mysql/bin/mysqldump.exe') + $optionalFiles) {
        Test-NegativeZip "redundant file $redundant" 'Redundant development/client' -ExtraEntries @(@{ Name = $redundant; Bytes = [byte[]]@(1) })
    }
    foreach ($live in @('configs/worldserver.conf', 'mysql/data/user.db', 'mysql/my.cnf',
        'mysql/my.ini', 'logs/world.log', 'data/dbc/Spell.dbc', 'configs/.portable-profiles.json', 'configs/realm-phase.txt')) {
        Test-NegativeZip "protected user file $live" 'Live user data/configuration' -ExtraEntries @(@{ Name = $live; Bytes = [byte[]]@(1) })
    }
    Test-NegativeZip 'missing release identity' 'missing portable-release.json' -Omit @('portable-release.json')
    $wrongIdentity = @{ schema = 1; revision = ('b' * 40); package = 'mod-playerbots-portable-latest.zip'; version = 'latest' } | ConvertTo-Json
    Test-NegativeZip 'release identity belongs to another commit' 'Invalid or mismatched portable release identity' -Replacements @{ 'portable-release.json' = [System.Text.Encoding]::UTF8.GetBytes($wrongIdentity) }
    Test-NegativeZip 'missing one core database while another remains' 'missing core SQL' -Omit @('src/data/sql/base/db_auth/base.sql')
    Test-NegativeZip 'missing module migration' 'missing module migration' -Omit @('src/modules/mod-fixture/data/sql/db_world/current.sql')
    foreach ($obsolete in @('src/data/sql/updates/db_world/obsolete.sql',
        'src/modules/mod-fixture/data/sql/db_world/obsolete.sql',
        'src/modules/mod-removed/data/sql/db_world/obsolete.sql')) {
        Test-NegativeZip "obsolete SQL $obsolete" 'Unexpected SQL file' -ExtraEntries @(@{ Name = $obsolete; Bytes = [byte[]]@(1) })
    }
    # Core adaptations must package from the generated checkout, while older
    # manifests above continue to use the pristine submodule.
    $preparedCore = Join-Path $source '.module-cache/prepared-core'
    [void][System.IO.Directory]::CreateDirectory((Split-Path $preparedCore -Parent))
    Copy-Item -LiteralPath (Join-Path $source 'azerothcore-wotlk') -Destination $preparedCore -Recurse
    Write-FixtureText (Join-Path $source 'azerothcore-wotlk/data/sql/updates/db_world/unprepared.sql')
    Write-FixtureText (Join-Path $source 'patches/core-fixture.patch')
    $lock.core.patches = @('patches/core-fixture.patch')
    Write-FixtureText (Join-Path $source 'versions.lock.json') ($lock | ConvertTo-Json -Depth 5)
    Invoke-Assembly
    $script:baseline.Clear()
    foreach ($file in Get-ChildItem -LiteralPath $dist -Recurse -File -Force) {
        $relative = [System.IO.Path]::GetRelativePath($dist, $file.FullName).Replace('\', '/')
        $script:baseline.Add($relative, [System.IO.File]::ReadAllBytes($file.FullName))
    }
    $patchedZip = Join-Path $temporaryRoot 'patched-core.zip'
    New-FixtureZip $patchedZip
    Test-Zip 'patched core selects generated SQL and retains original source' $patchedZip
    Assert-Condition (-not $script:baseline.ContainsKey('src/data/sql/updates/db_world/unprepared.sql')) 'Original core SQL leaked into generated export'
    Test-NegativeZip 'missing core adaptation patch' 'missing core source patch' -Omit @('patches/core-fixture.patch')
    Test-NegativeZip 'missing generated core SQL' 'missing core SQL' -Omit @('src/data/sql/base/db_auth/base.sql')
    Write-Host "Passed $script:passed portable assembly/ZIP regression checks."
} finally {
    if (Test-Path -LiteralPath $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force }
}
