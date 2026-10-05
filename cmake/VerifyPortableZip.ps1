[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [string]$RepositoryRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $ZipPath))
try {
    $files = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $entries = [System.Collections.Generic.Dictionary[string, System.IO.Compression.ZipArchiveEntry]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $lockEntry = $null
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\', '/').TrimStart('./')
        if ($entry.Length -gt 0) { [void]$files.Add($name) }
        $entries[$name] = $entry
        if ($name -eq 'versions.lock.json') { $lockEntry = $entry }
        if ($name -match '(^|/)\.git(/|$)' -or $name -match '\.(pdb|lib|exp|ilk|msix|msixupload)$') {
            throw "Unexpected source/debug/installer file in portable ZIP: $name"
        }
    }

    $lock = Get-Content (Join-Path $RepositoryRoot 'versions.lock.json') -Raw | ConvertFrom-Json
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
        # Include all images/textures as well as the Lua files named in the TOC.
        $addonSource = Join-Path $RepositoryRoot ".module-cache/prepared-addons/$($addon.name)"
        if (-not (Test-Path $addonSource -PathType Container)) { throw "Prepared client addon source is missing: $($addon.name)" }
        foreach ($sourceFile in Get-ChildItem $addonSource -Recurse -File) {
            if ($sourceFile.Name -eq '.portable-source') { continue }
            $relative = [System.IO.Path]::GetRelativePath($addonSource, $sourceFile.FullName).Replace('\', '/')
            if (-not $files.Contains("$prefix/$relative")) { throw "Portable ZIP is missing client addon asset $prefix/$relative" }
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
        'defaults/playerbots.conf', 'defaults/worldserver.conf', 'defaults/individualProgression.conf',
        'defaults/AutoBalance.conf', 'defaults/mod_ahbot.conf', 'defaults/mod_dungeon_clear.conf',
        'versions.lock.json', 'README.md', 'docs/vanilla-config-audit.md', 'LICENSE', 'licenses/azerothcore-wotlk.txt'
    )
    foreach ($name in $required) {
        if (-not $files.Contains($name)) { throw "Portable ZIP is missing $name" }
    }
    $textSources = [ordered]@{
        'README.md' = 'README.md'
        'docs/vanilla-config-audit.md' = 'docs/vanilla-config-audit.md'
        'defaults/playerbots.conf' = 'cmd/startup/profiles/playerbots.conf'
        'defaults/worldserver.conf' = 'cmd/startup/profiles/worldserver.conf'
        'defaults/individualProgression.conf' = 'cmd/startup/profiles/individualProgression.conf'
        'defaults/AutoBalance.conf' = 'cmd/startup/profiles/AutoBalance.conf'
        'defaults/mod_ahbot.conf' = 'cmd/startup/profiles/mod_ahbot.conf'
        'defaults/mod_dungeon_clear.conf' = 'cmd/startup/profiles/mod_dungeon_clear.conf'
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

    foreach ($module in $lock.modules) {
        foreach ($patch in @($module.patches)) {
            if ($patch -and -not $files.Contains($patch)) { throw "Portable ZIP is missing source patch $patch" }
        }
        $sqlSource = Join-Path $RepositoryRoot "azerothcore-wotlk/modules/$($module.name)/data/sql"
        if (Test-Path $sqlSource) {
            foreach ($sql in Get-ChildItem $sqlSource -Recurse -File -Filter '*.sql') {
                $relative = [System.IO.Path]::GetRelativePath($sqlSource, $sql.FullName).Replace('\', '/')
                $name = "src/modules/$($module.name)/data/sql/$relative"
                if (-not $files.Contains($name)) { throw "Portable ZIP is missing module migration $name" }
            }
        }
        if (-not ($files | Where-Object { $_ -like "licenses/$($module.name)/*" -or $_ -like "licenses/$($module.name).*" })) {
            throw "Portable ZIP is missing the $($module.name) license."
        }
    }

    $reader = [System.IO.StreamReader]::new($lockEntry.Open())
    try { $packagedLock = $reader.ReadToEnd() } finally { $reader.Dispose() }
    $expectedLock = Get-Content (Join-Path $RepositoryRoot 'versions.lock.json') -Raw
    if ($packagedLock.Trim() -ne $expectedLock.Trim()) { throw 'Packaged dependency lock differs from build sources.' }
    Write-Host "Verified portable ZIP: $($files.Count) nonempty files, all executables, runtime DLLs, module configs, SQL and client addons present."
} finally {
    $archive.Dispose()
}
