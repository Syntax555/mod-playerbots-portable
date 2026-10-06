[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [string]$RepositoryRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path

function Assert-AddonFileMatchesSource(
    [System.IO.Compression.ZipArchiveEntry]$Entry,
    [System.IO.FileInfo]$SourceFile,
    [System.Security.Cryptography.SHA256]$Sha256,
    [string]$Name
) {
    if ($Entry.Length -ne $SourceFile.Length) {
        throw "Packaged client addon asset differs from prepared source: $Name"
    }
    $stream = $Entry.Open()
    try { $packagedHash = [System.BitConverter]::ToString($Sha256.ComputeHash($stream)) } finally { $stream.Dispose() }
    $stream = [System.IO.File]::OpenRead($SourceFile.FullName)
    try { $sourceHash = [System.BitConverter]::ToString($Sha256.ComputeHash($stream)) } finally { $stream.Dispose() }
    if ($packagedHash -cne $sourceHash) {
        throw "Packaged client addon asset differs from prepared source: $Name"
    }
}

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
    $expectedAddonFiles = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($addon in @($lock.clientAddons)) {
        $prefix = "addons/$($addon.name)"
        $tocPath = "$prefix/$($addon.toc)"
        foreach ($name in @($tocPath, "$prefix/$($addon.license)", "$prefix/README.md", "$prefix/SOURCE_REVISION.txt", "licenses/$($addon.name)/$($addon.license)")) {
            if (-not $files.Contains($name)) { throw "Portable ZIP is missing client addon file $name" }
        }
        $reader = [System.IO.StreamReader]::new($entries["$prefix/SOURCE_REVISION.txt"].Open())
        try { $addonRevision = $reader.ReadToEnd().Trim() } finally { $reader.Dispose() }
        if ($addonRevision -ne $addon.revision) { throw "Client addon $($addon.name) does not match its locked source revision." }
        $reader = [System.IO.StreamReader]::new($entries[$tocPath].Open())
        try { $tocText = $reader.ReadToEnd() } finally { $reader.Dispose() }
        $interface = [regex]::Match($tocText, '(?m)^##\s*Interface\s*:\s*(\d+)\s*$')
        if (-not $interface.Success -or $interface.Groups[1].Value -ne '30300' -or $addon.interface -ne 30300) {
            throw "Client addon $($addon.name) must declare WotLK Interface 30300."
        }
        foreach ($line in ($tocText -split '\r?\n')) {
            $asset = $line.Trim().Replace('\', '/')
            if (-not $asset -or $asset.StartsWith('#')) { continue }
            if ($asset.StartsWith('/') -or $asset -match '(^|/)\.\.(/|$)' -or -not $files.Contains("$prefix/$asset")) {
                throw "Client addon $($addon.name) has a missing or invalid TOC asset: $asset"
            }
        }
        # Match all prepared bytes, including hidden files and textures outside the TOC.
        $addonSource = Join-Path $RepositoryRoot ".module-cache/prepared-addons/$($addon.name)"
        if (-not (Test-Path -LiteralPath $addonSource -PathType Container)) { throw "Prepared client addon source is missing: $($addon.name)" }
        if ((Get-Item -LiteralPath $addonSource -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Symbolic link in prepared client addon: $($addon.name)"
        }
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            foreach ($sourceFile in Get-ChildItem -LiteralPath $addonSource -Recurse -Force) {
                if ($sourceFile.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    throw "Symbolic link in prepared client addon: $($sourceFile.FullName)"
                }
                $relative = [System.IO.Path]::GetRelativePath($addonSource, $sourceFile.FullName).Replace('\', '/')
                if ($relative -match '(^|/)\.portable-source(/|$)' -or $sourceFile.PSIsContainer) { continue }
                $name = "$prefix/$relative"
                [void]$expectedAddonFiles.Add($name)
                if (-not $entries.ContainsKey($name)) { throw "Portable ZIP is missing client addon asset $name" }
                Assert-AddonFileMatchesSource $entries[$name] $sourceFile $sha256 $name
            }
            $licensePath = "licenses/$($addon.name)/$($addon.license)"
            Assert-AddonFileMatchesSource $entries[$licensePath] (Get-Item -LiteralPath (Join-Path $addonSource $addon.license)) $sha256 $licensePath
        } finally {
            $sha256.Dispose()
        }
    }
    foreach ($name in $entries.Keys) {
        if ($name.StartsWith('addons/', [System.StringComparison]::OrdinalIgnoreCase) -and -not $expectedAddonFiles.Contains($name)) {
            throw "Unexpected client addon asset in portable ZIP: $name"
        }
    }

    $required = @(
        'startup.exe', 'authserver.exe', 'worldserver.exe',
        'map_extractor.exe', 'vmap4_extractor.exe', 'vmap4_assembler.exe', 'mmaps_generator.exe', 'dbimport.exe',
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
        'defaults/playerbots.conf', 'defaults/worldserver.conf', 'defaults/individualProgression.conf',
        'defaults/AutoBalance.conf', 'defaults/mod_ahbot.conf', 'defaults/mod_dungeon_clear.conf',
        'defaults/mod-quest-loot-party.conf',
        'defaults/MultiBotBridge.conf', 'defaults/mod_token_turnin.conf',
        'versions.lock.json', 'README.md', 'docs/vanilla-config-audit.md', 'docs/module-versions.md',
        'docs/changing-expansions.md', 'docs/earned-bot-brackets.md', 'docs/earned-auctions.md',
        'LICENSE', 'licenses/azerothcore-wotlk.txt'
    )
    foreach ($name in $required) {
        if (-not $files.Contains($name)) { throw "Portable ZIP is missing $name" }
    }
    $textSources = [ordered]@{
        'README.md' = 'README.md'
        'docs/vanilla-config-audit.md' = 'docs/vanilla-config-audit.md'
        'docs/module-versions.md' = 'docs/module-versions.md'
        'docs/changing-expansions.md' = 'docs/changing-expansions.md'
        'docs/earned-bot-brackets.md' = 'docs/earned-bot-brackets.md'
        'docs/earned-auctions.md' = 'docs/earned-auctions.md'
        'defaults/playerbots.conf' = 'cmd/startup/profiles/playerbots.conf'
        'defaults/worldserver.conf' = 'cmd/startup/profiles/worldserver.conf'
        'defaults/individualProgression.conf' = 'cmd/startup/profiles/individualProgression.conf'
        'defaults/AutoBalance.conf' = 'cmd/startup/profiles/AutoBalance.conf'
        'defaults/mod_ahbot.conf' = 'cmd/startup/profiles/mod_ahbot.conf'
        'defaults/mod_dungeon_clear.conf' = 'cmd/startup/profiles/mod_dungeon_clear.conf'
        'defaults/mod-quest-loot-party.conf' = 'cmd/startup/profiles/mod-quest-loot-party.conf'
        'defaults/MultiBotBridge.conf' = 'cmd/startup/profiles/MultiBotBridge.conf'
        'defaults/mod_token_turnin.conf' = 'cmd/startup/profiles/mod_token_turnin.conf'
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
    $coreSqlSource = Join-Path $RepositoryRoot 'azerothcore-wotlk/data/sql'
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
        $sqlSource = Join-Path $RepositoryRoot "azerothcore-wotlk/modules/$($module.name)/data/sql"
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
    Write-Host "Verified portable ZIP: $($files.Count) nonempty files, required runtime/configs, matching client addon assets and exact SQL file sets."
} finally {
    $archive.Dispose()
}
