[CmdletBinding()]
param(
    [string]$AddOnsPath,
    [string]$SourceArchive
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$addonName = '@@NAME@@'
$title = '@@TITLE@@'
# Separate addons this one already contains; loading both conflicts.
$containedAddons = @(@@CONTAINED@@)

function Get-Sha256([byte[]]$Bytes) {
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try { return ([System.BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

function Assert-Hash([string]$Expected, [byte[]]$Bytes, [string]$Description) {
    if ($Expected -cnotmatch '^[a-f0-9]{64}$' -or (Get-Sha256 $Bytes) -cne $Expected) {
        throw "$Description failed its SHA-256 check. Keep the existing addon and download the installer again."
    }
}

function Get-SafeRelativePath([string]$Path) {
    if (-not $Path -or $Path.Contains('\') -or $Path.Contains(':') -or $Path.StartsWith('/') -or
        $Path -match '(^|/)\.{1,2}(/|$)|//|\x00') {
        throw "Unsafe relative path: $Path"
    }
    return $Path
}

function Assert-WowClosed {
    if (@(Get-Process -Name 'Wow', 'Wow-64', 'WowClassic', 'WowClassicT' -ErrorAction SilentlyContinue).Count -gt 0) {
        throw "Close World of Warcraft completely before installing $title."
    }
}

# Extracts the addon folder of the fork's GitHub archive. Every file must match
# the packaged Git tree exactly; the rest of the repository is checked and skipped.
function Expand-AddonArchive([string]$ArchivePath, [string]$Destination, [string]$Root, [string]$Prefix, $Expected) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $found = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    [long]$totalSize = 0
    try {
        if ($archive.Entries.Count -gt 100000) { throw "The $title archive has too many entries." }
        foreach ($entry in $archive.Entries) {
            $path = Get-SafeRelativePath $entry.FullName
            if (-not $path.StartsWith($Root, [System.StringComparison]::Ordinal)) {
                throw "Unexpected root in $title archive: $path"
            }
            if (-not $seen.Add($path.TrimEnd('/'))) { throw "Duplicate path in $title archive: $path" }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000 -or
                ($entry.ExternalAttributes -band 0x400) -ne 0) {
                throw "Linked file in $title archive: $path"
            }
            if (-not $path.StartsWith($Prefix, [System.StringComparison]::Ordinal)) { continue }
            $relative = $path.Substring($Prefix.Length)
            # Repository tooling, this installer included, is not part of the addon.
            if (-not $relative -or $relative.Split('/')[0] -ceq '.github') { continue }
            if ($path.EndsWith('/')) {
                if ($entry.Length -ne 0) { throw "Nonempty directory entry: $path" }
                continue
            }
            if (-not $Expected.ContainsKey($relative)) { throw "Unexpected file in the $title archive: $relative" }
            $totalSize += $entry.Length
            if ($entry.Length -gt 67108864 -or $totalSize -gt 536870912) {
                throw "The $title archive exceeds the installation size limit."
            }
            $target = Join-Path $Destination $relative
            [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target))
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
            Assert-Hash $Expected[$relative] ([System.IO.File]::ReadAllBytes($target)) "$title file $relative"
            [void]$found.Add($relative)
        }
    } finally { $archive.Dispose() }
    if ($found.Count -ne $Expected.Count) { throw "The $title archive is missing files of the packaged version." }
}

function Assert-AddonToc([string]$Payload) {
    $toc = [System.IO.File]::ReadAllText((Join-Path $Payload "$addonName.toc"), $utf8)
    $interfaces = [regex]::Matches($toc, '(?m)^##[ \t]*Interface[ \t]*:[ \t]*(\d+)[ \t]*\r?$')
    if ($interfaces.Count -ne 1 -or $interfaces[0].Groups[1].Value -ne '30300') {
        throw "$title must declare the WoW 3.3.5a interface version 30300 exactly once."
    }
    # The client resolves TOC paths without regard to case.
    $files = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $root = [System.IO.Path]::GetFullPath($Payload).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    foreach ($file in [System.IO.Directory]::EnumerateFiles($Payload, '*', [System.IO.SearchOption]::AllDirectories)) {
        [void]$files.Add([System.IO.Path]::GetFullPath($file).Substring($root.Length).Replace('\', '/'))
    }
    foreach ($line in ($toc -split '\r?\n')) {
        $asset = $line.Trim().Replace('\', '/')
        if (-not $asset -or $asset.StartsWith('#')) { continue }
        $asset = Get-SafeRelativePath $asset
        if (-not $files.Contains($asset)) { throw "Missing $title TOC asset: $asset" }
    }
}

$stage = $null
$backup = $null
$target = $null
try {
    $manifestBytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'SOURCE_MANIFEST.json'))
    $manifest = $utf8.GetString($manifestBytes) | ConvertFrom-Json
    $repository = [string]$manifest.repository
    $revision = [string]$manifest.revision
    $archiveRoot = [string]$manifest.sourceArchive.root
    $addonPath = [string]$manifest.sourceArchive.path
    if ($manifest.schemaVersion -ne 2 -or $manifest.name -cne $addonName -or
        $repository -cnotmatch '^https://github[.]com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+$' -or
        $revision -cnotmatch '^[a-f0-9]{40}$' -or $manifest.interface -ne 30300 -or
        $manifest.sourceArchive.url -cne "$repository/archive/$revision.zip" -or
        $archiveRoot -cnotmatch ('^[A-Za-z0-9_.-]+-' + $revision + '/$') -or
        $addonPath -cnotmatch '^([A-Za-z0-9_-][A-Za-z0-9_.-]*/)*$') {
        throw "The installer has an invalid $title source manifest."
    }
    $filesBytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'ADDON_FILES.json'))
    Assert-Hash $manifest.addonFilesSha256 $filesBytes "$title file list"
    $listed = $utf8.GetString($filesBytes) | ConvertFrom-Json
    if ($listed.schemaVersion -ne 1 -or $listed.root -cne $addonName) { throw "Invalid $title file list." }
    $expected = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::Ordinal)
    $folded = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $listed.files.PSObject.Properties) {
        $relative = Get-SafeRelativePath $file.Name
        if (-not $folded.Add($relative) -or $file.Value -cnotmatch '^[a-f0-9]{64}$') { throw "Invalid file list entry: $relative" }
        $expected.Add($relative, $file.Value)
    }
    if (-not $expected.ContainsKey("$addonName.toc")) { throw "The $title file list has no addon TOC." }

    Assert-WowClosed
    if (-not $AddOnsPath) { $AddOnsPath = Read-Host 'Enter the full path to your WoW 3.3.5a Interface\AddOns folder' }
    $AddOnsPath = [System.IO.Path]::GetFullPath($AddOnsPath.Trim().Trim('"'))
    if (-not [System.IO.Directory]::Exists($AddOnsPath)) { throw 'The selected Interface\AddOns folder does not exist.' }
    $target = Join-Path $AddOnsPath $addonName
    if ([System.IO.File]::Exists($target)) { throw "$addonName is an existing file, not an addon folder." }
    if ([System.IO.Directory]::Exists($target) -and
        ((Get-Item -LiteralPath $target -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "The existing $addonName folder is a link. Move it aside before installing."
    }
    $stage = Join-Path $AddOnsPath ('.' + $addonName + '-install-' + [guid]::NewGuid().ToString('N'))
    [void][System.IO.Directory]::CreateDirectory($stage)
    if ($SourceArchive) {
        $archivePath = (Resolve-Path -LiteralPath $SourceArchive).Path
    } else {
        $archivePath = Join-Path $stage 'source.zip'
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
        Write-Host "Downloading $title $($revision.Substring(0, 12)) directly from $repository ..."
        # Windows PowerShell 5.1 redraws its progress bar per received block,
        # which slows a large download many times over.
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $manifest.sourceArchive.url -OutFile $archivePath -UseBasicParsing
    }
    $payload = Join-Path $stage $addonName
    [void][System.IO.Directory]::CreateDirectory($payload)
    Expand-AddonArchive $archivePath $payload $archiveRoot ($archiveRoot + $addonPath) $expected
    Assert-AddonToc $payload
    [System.IO.File]::WriteAllBytes((Join-Path $payload 'SOURCE_MANIFEST.json'), $manifestBytes)
    [System.IO.File]::WriteAllBytes((Join-Path $payload 'SOURCE_REVISION.txt'), $utf8.GetBytes($revision + "`n"))
    # Both moves stay on the client filesystem. A failed replacement restores the old addon.
    Assert-WowClosed
    if ([System.IO.Directory]::Exists($target)) {
        $backup = Join-Path $AddOnsPath ($addonName + '.backup-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
        [System.IO.Directory]::Move($target, $backup)
    }
    try { [System.IO.Directory]::Move($payload, $target) }
    catch {
        if ($backup -and -not [System.IO.Directory]::Exists($target)) { [System.IO.Directory]::Move($backup, $target) }
        throw
    }
    Write-Host "Installed $title $($revision.Substring(0, 12)) in $target"
    if ($backup) { Write-Host "Previous addon retained in $backup" }
    foreach ($contained in $containedAddons) {
        if ([System.IO.Directory]::Exists((Join-Path $AddOnsPath $contained))) {
            Write-Warning "Disable the separate $contained addon; $addonName already contains it."
        }
    }
    Write-Host "Account and character SavedVariables were preserved. Enable $title when starting WoW."
} catch {
    [Console]::Error.WriteLine("$title installation failed: " + $_.Exception.Message)
    exit 1
} finally {
    if ($stage -and [System.IO.Directory]::Exists($stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
