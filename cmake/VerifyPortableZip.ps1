[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [string]$RepositoryRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$ExpectedRevision = ''
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path

$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ZipPath).Path)
try {
    $files = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $entries = [System.Collections.Generic.Dictionary[string, System.IO.Compression.ZipArchiveEntry]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $paths = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $lockEntry = $null
    foreach ($entry in $archive.Entries) {
        # CMake's ZIP fallback emits a literal ./ prefix, including a ./ root entry.
        # Do not rewrite other separators or strip arbitrary leading dots/slashes.
        $name = $entry.FullName
        if ($name.StartsWith('./', [System.StringComparison]::Ordinal)) { $name = $name.Substring(2) }
        if (($name.Length -eq 0 -and $entry.FullName -cne './') -or $name.StartsWith('/') -or
            $name -match '[\\:<>"|?*\x00-\x1f]|(^|/)\.{1,2}(/|$)|//|[. ](/|$)' -or
            $name -match '(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|/|$)') {
            throw "Unsafe path in portable ZIP: $($entry.FullName)"
        }
        if (-not $paths.Add($name.TrimEnd('/'))) { throw "Duplicate path in portable ZIP: $($entry.FullName)" }
        $unixType = ($entry.ExternalAttributes -shr 16) -band 0xF000
        if ($unixType -eq 0xA000 -or ($entry.ExternalAttributes -band 0x400)) {
            throw "Symbolic link in portable ZIP: $($entry.FullName)"
        }
        if ($name -match '(^|/)\.git(/|$)' -or $name -match '\.(pdb|lib|exp|ilk|msix|msixupload)$') {
            throw "Unexpected source/debug/installer file in portable ZIP: $name"
        }
        if ($name -match '^(addons|defaults)(/|$)|^CONTRIBUTING[.]md$|^docs/building[.]md$' -or
            $name -match '^mysql/(include|docs)(/|$)|^mysql/bin/(?!mysqld[.]exe$|mysql[.]exe$|mysqladmin[.]exe$)[^/]+[.]exe$' -or
            $name -match '^(dbimport|map_extractor|vmap4_extractor|vmap4_assembler|mmaps_generator)[.]exe$|^mmaps-config[.]yaml$|^(configs/)?dbimport[.]conf[.]dist$') {
            throw "Redundant development/client file in portable ZIP: $name"
        }
        if ($name -match '^(data|logs|mysql/data|mysql-files)(/|$)|[.]conf$|(^|/)(my[.]cnf|my[.]ini)$|(^|/)[.]portable-|^configs/realm-phase[.]txt$') {
            throw "Live user data/configuration in portable ZIP: $name"
        }
        if ($name.Length -eq 0 -or $name.EndsWith('/')) {
            if ($entry.Length -ne 0) { throw "Nonempty directory entry in portable ZIP: $($entry.FullName)" }
            continue
        }
        if ($entry.Length -gt 0) { [void]$files.Add($name) }
        $entries.Add($name, $entry)
        if ($name -eq 'versions.lock.json') { $lockEntry = $entry }
    }
    foreach ($path in $paths) {
        $separator = $path.LastIndexOf('/')
        while ($separator -ge 0) {
            $parent = $path.Substring(0, $separator)
            if ($entries.ContainsKey($parent)) { throw "File/directory collision in portable ZIP: $parent" }
            $separator = $parent.LastIndexOf('/')
        }
    }

    $lock = Get-Content (Join-Path $RepositoryRoot 'versions.lock.json') -Raw | ConvertFrom-Json
    $required = @(
        'startup.exe', 'authserver.exe', 'worldserver.exe',
        'mysql/bin/mysqld.exe', 'mysql/bin/mysql.exe', 'mysql/bin/mysqladmin.exe',
        'libmysql.dll', 'libcrypto-3-x64.dll', 'libssl-3-x64.dll',
        'vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
        'mysql/bin/vcruntime140.dll', 'mysql/bin/vcruntime140_1.dll', 'mysql/bin/msvcp140.dll',
        'configs/authserver.conf.dist', 'configs/worldserver.conf.dist',
        'configs/modules/playerbots.conf.dist', 'configs/modules/AutoBalance.conf.dist',
        'configs/modules/individualProgression.conf.dist', 'configs/modules/mod_ahbot.conf.dist',
        'configs/modules/mod_dungeon_clear.conf.dist',
        'configs/modules/mod-quest-loot-party.conf.dist',
        'configs/modules/MultiBotBridge.conf.dist', 'configs/modules/mod_token_turnin.conf.dist',
        'portable-release.json', 'versions.lock.json', 'README.md', 'docs/vanilla-config-audit.md', 'docs/module-versions.md',
        'docs/changing-expansions.md', 'docs/earned-bot-brackets.md', 'docs/earned-auctions.md',
        'LICENSE', 'licenses/azerothcore-wotlk.txt'
    )
    foreach ($name in $required) {
        if (-not $files.Contains($name)) { throw "Portable ZIP is missing $name" }
    }
    $reader = [System.IO.StreamReader]::new($entries['portable-release.json'].Open())
    try { $identity = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($identity.schema -ne 1 -or $identity.revision -cnotmatch '^[0-9a-f]{40}$' -or
        $identity.version -cnotmatch '^[A-Za-z0-9._-]+$' -or
        $identity.package -cne "mod-playerbots-portable-$($identity.version).zip" -or
        ($ExpectedRevision -and $identity.revision -cne $ExpectedRevision)) {
        throw 'Invalid or mismatched portable release identity.'
    }
    $textSources = [ordered]@{
        'README.md' = 'README.md'
        'docs/vanilla-config-audit.md' = 'docs/vanilla-config-audit.md'
        'docs/module-versions.md' = 'docs/module-versions.md'
        'docs/changing-expansions.md' = 'docs/changing-expansions.md'
        'docs/earned-bot-brackets.md' = 'docs/earned-bot-brackets.md'
        'docs/earned-auctions.md' = 'docs/earned-auctions.md'

    }
    foreach ($document in @('THIRD_PARTY_NOTICES.md')) {
        if (Test-Path (Join-Path $RepositoryRoot $document) -PathType Leaf) {
            if (-not $files.Contains($document)) { throw "Portable ZIP is missing $document" }
            $textSources[$document] = $document
        }
    }
    if (@($lock.modules | Where-Object { $_.name -eq 'mod-era-talents' }).Count -gt 0) {
        foreach ($name in @('docs/era-talents.md', 'configs/modules/mod_era_talents.conf.dist')) {
            if (-not $files.Contains($name)) { throw "Portable ZIP is missing $name" }
        }
        $textSources['docs/era-talents.md'] = 'docs/era-talents.md'
    }
    foreach ($name in $textSources.Keys) {
        $reader = [System.IO.StreamReader]::new($entries[$name].Open())
        try { $packagedText = $reader.ReadToEnd() } finally { $reader.Dispose() }
        $sourceText = Get-Content (Join-Path $RepositoryRoot $textSources[$name]) -Raw
        if ($packagedText -cne $sourceText) { throw "Packaged documentation/profile differs from build sources: $name" }
    }
    if (-not ($files | Where-Object { $_ -like 'src/data/sql/base/*/*.sql' })) {
        throw 'Portable ZIP is missing AzerothCore base database SQL.'
    }

    $expectedSql = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $preparedCore = if (@($lock.core.patches | Where-Object { $_ }).Count -gt 0) {
        Join-Path $RepositoryRoot '.module-cache/prepared-core'
    } else {
        Join-Path $RepositoryRoot $lock.core.source
    }
    foreach ($patch in @($lock.core.patches)) {
        if ($patch -and -not $files.Contains($patch)) { throw "Portable ZIP is missing core source patch $patch" }
    }
    $coreSqlSource = Join-Path $preparedCore 'data/sql'
    if (-not (Test-Path -LiteralPath $coreSqlSource -PathType Container)) { throw 'AzerothCore SQL source is missing.' }
    foreach ($sql in Get-ChildItem -LiteralPath $coreSqlSource -Recurse -File -Force -Filter '*.sql') {
        $relative = [System.IO.Path]::GetRelativePath($coreSqlSource, $sql.FullName).Replace('\', '/')
        $name = "src/data/sql/$relative"
        [void]$expectedSql.Add($name)
        if (-not $entries.ContainsKey($name)) { throw "Portable ZIP is missing core SQL $name" }
    }
    foreach ($module in $lock.modules) {
        foreach ($patch in @($module.patches)) {
            if ($patch -and -not $files.Contains($patch)) { throw "Portable ZIP is missing source patch $patch" }
        }
        $sqlSource = Join-Path $preparedCore "modules/$($module.name)/data/sql"
        if (Test-Path -LiteralPath $sqlSource -PathType Container) {
            foreach ($sql in Get-ChildItem -LiteralPath $sqlSource -Recurse -File -Force -Filter '*.sql') {
                $relative = [System.IO.Path]::GetRelativePath($sqlSource, $sql.FullName).Replace('\', '/')
                $name = "src/modules/$($module.name)/data/sql/$relative"
                [void]$expectedSql.Add($name)
                if (-not $files.Contains($name)) { throw "Portable ZIP is missing module migration $name" }
            }
        }
        if (-not ($files | Where-Object { $_ -like "licenses/$($module.name)/*" -or $_ -like "licenses/$($module.name).*" })) {
            throw "Portable ZIP is missing the $($module.name) license."
        }
    }
    foreach ($name in $entries.Keys) {
        if ($name -match '^src/data/sql/.*\.sql$|^src/modules/[^/]+/data/sql/.*\.sql$' -and -not $expectedSql.Contains($name)) {
            throw "Unexpected SQL file in portable ZIP: $name"
        }
    }

    $reader = [System.IO.StreamReader]::new($lockEntry.Open())
    try { $packagedLock = $reader.ReadToEnd() } finally { $reader.Dispose() }
    $expectedLock = Get-Content (Join-Path $RepositoryRoot 'versions.lock.json') -Raw
    if ($packagedLock.Trim() -ne $expectedLock.Trim()) { throw 'Packaged dependency lock differs from build sources.' }
    Write-Host "Verified portable ZIP: $($files.Count) nonempty files, required runtime/configs, release identity, separate client downloads and exact SQL file sets."
} finally {
    $archive.Dispose()
}
