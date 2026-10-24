[CmdletBinding()]
param(
    [string]$AddOnsPath,
    [string]$SourceArchive
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$addonName = 'ZygorGuidesViewerRM'
$repository = 'https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK.git'
$archiveBase = 'https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK/archive/'

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
        throw 'Close World of Warcraft completely before installing Zygor Guides Viewer.'
    }
}

# Extracts the addon folder of the upstream archive. Every file must match the
# pinned Git tree exactly; the rest of the repository is checked and skipped.
function Expand-ZygorArchive([string]$ArchivePath, [string]$Destination, [string]$Revision, $Expected) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $found = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $root = "ZygorGuidesRemaster-3.3.5a_WOTLK-$Revision/"
    $prefix = "$root$addonName/"
    [long]$totalSize = 0
    try {
        if ($archive.Entries.Count -gt 100000) { throw 'The Zygor archive has too many entries.' }
        foreach ($entry in $archive.Entries) {
            $path = Get-SafeRelativePath $entry.FullName
            if (-not $path.StartsWith($root, [System.StringComparison]::Ordinal)) {
                throw "Unexpected root in Zygor archive: $path"
            }
            if (-not $seen.Add($path.TrimEnd('/'))) { throw "Duplicate path in Zygor archive: $path" }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000 -or
                ($entry.ExternalAttributes -band 0x400) -ne 0) {
                throw "Linked file in Zygor archive: $path"
            }
            if (-not $path.StartsWith($prefix, [System.StringComparison]::Ordinal)) { continue }
            $relative = $path.Substring($prefix.Length)
            if (-not $relative) { continue }
            $target = Join-Path $Destination $relative
            if ($path.EndsWith('/')) {
                if ($entry.Length -ne 0) { throw "Nonempty directory entry: $path" }
                [void][System.IO.Directory]::CreateDirectory($target)
                continue
            }
            if (-not $Expected.ContainsKey($relative)) { throw "Unexpected file in the Zygor archive: $relative" }
            $totalSize += $entry.Length
            if ($entry.Length -gt 67108864 -or $totalSize -gt 536870912) {
                throw 'The Zygor archive exceeds the installation size limit.'
            }
            [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target))
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
            Assert-Hash $Expected[$relative] ([System.IO.File]::ReadAllBytes($target)) "Upstream Zygor file $relative"
            [void]$found.Add($relative)
        }
    } finally { $archive.Dispose() }
    if ($found.Count -ne $Expected.Count) { throw 'The Zygor archive is missing files of the pinned version.' }
}

function Set-ZygorLines([string]$Relative, [byte[]]$Original, $Hunks) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.AddRange([string[]]$utf8.GetString($Original).Split([char]10))
    $previousStart = $lines.Count + 1
    foreach ($hunk in @($Hunks | Sort-Object -Property start -Descending)) {
        if ([string]$hunk.start -notmatch '^\d+$' -or [string]$hunk.deleteCount -notmatch '^\d+$') {
            throw "Invalid patch range in $Relative"
        }
        $start = [int]$hunk.start
        $count = [int]$hunk.deleteCount
        if ($start -gt $lines.Count -or $count -gt ($lines.Count - $start) -or
            $start -ge $previousStart -or ($start + $count) -gt $previousStart) {
            throw "Overlapping or out-of-range patch in $Relative"
        }
        foreach ($line in @($hunk.lines)) {
            if ($line -isnot [string] -or $line.Contains("`n")) { throw "Invalid replacement line in $Relative" }
        }
        $lines.RemoveRange($start, $count)
        $lines.InsertRange($start, [string[]]@($hunk.lines))
        $previousStart = $start
    }
    return $utf8.GetBytes([string]::Join("`n", $lines))
}

# Applies the local integration: changed upstream files and new files.
function Apply-ZygorChanges([string]$Destination, $PatchData, $Expected) {
    if ($PatchData.schemaVersion -ne 1 -or @($PatchData.files).Count -eq 0) { throw 'Invalid Zygor patch data.' }
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $PatchData.files) {
        $relative = Get-SafeRelativePath $file.path
        if (-not $seen.Add($relative) -or $relative.EndsWith('/')) { throw "Duplicate or invalid patch path: $relative" }
        $path = Join-Path $Destination $relative
        if ($file.created -eq $true) {
            if ($Expected.ContainsKey($relative) -or [System.IO.File]::Exists($path) -or [System.IO.Directory]::Exists($path)) {
                throw "A new Zygor file already exists: $relative"
            }
            $original = [byte[]]@()
        } else {
            if (-not $Expected.ContainsKey($relative)) { throw "Patch for a file outside the pinned version: $relative" }
            $original = [System.IO.File]::ReadAllBytes($path)
            Assert-Hash $file.beforeSha256 $original "Original Zygor file $relative"
        }
        $patched = Set-ZygorLines $relative $original $file.hunks
        Assert-Hash $file.afterSha256 $patched "Patched Zygor file $relative"
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path))
        [System.IO.File]::WriteAllBytes($path, $patched)
    }
}

function Assert-ZygorToc([string]$Payload) {
    $toc = [System.IO.File]::ReadAllText((Join-Path $Payload "$addonName.toc"), $utf8)
    $interfaces = [regex]::Matches($toc, '(?m)^##[ \t]*Interface[ \t]*:[ \t]*(\d+)[ \t]*\r?$')
    if ($interfaces.Count -ne 1 -or $interfaces[0].Groups[1].Value -ne '30300') {
        throw 'Zygor Guides Viewer must declare the WoW 3.3.5a interface version 30300 exactly once.'
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
        if (-not $files.Contains($asset)) { throw "Missing Zygor TOC asset: $asset" }
    }
}

$stage = $null
$backup = $null
$target = $null
try {
    $manifestPath = Join-Path $PSScriptRoot 'SOURCE_MANIFEST.json'
    $manifestBytes = [System.IO.File]::ReadAllBytes($manifestPath)
    $manifest = $utf8.GetString($manifestBytes) | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or $manifest.name -cne $addonName -or
        $manifest.repository -cne $repository -or
        $manifest.revision -cnotmatch '^[a-f0-9]{40}$' -or $manifest.interface -ne 30300 -or
        $manifest.sourceArchive.url -cne "$archiveBase$($manifest.revision).zip") {
        throw 'The installer has an invalid Zygor source manifest.'
    }
    $patchBytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'PATCH_DATA.json'))
    Assert-Hash $manifest.patchDataSha256 $patchBytes 'Zygor patch data'
    $filesBytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'UPSTREAM_FILES.json'))
    Assert-Hash $manifest.upstreamFilesSha256 $filesBytes 'Zygor upstream file list'
    $patches = @($manifest.patches.PSObject.Properties)
    if ($patches.Count -eq 0) { throw 'The installer has no locked Zygor patch.' }
    foreach ($patch in $patches) {
        if ($patch.Name -cnotmatch '^patches/[A-Za-z0-9_.-]+[.]patch$' -or $patch.Value -cnotmatch '^[a-f0-9]{64}$') {
            throw 'Invalid Zygor patch provenance in the installer manifest.'
        }
    }
    $upstream = $utf8.GetString($filesBytes) | ConvertFrom-Json
    if ($upstream.schemaVersion -ne 1 -or $upstream.root -cne $addonName) { throw 'Invalid Zygor upstream file list.' }
    $expected = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::Ordinal)
    $folded = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $upstream.files.PSObject.Properties) {
        $relative = Get-SafeRelativePath $file.Name
        if (-not $folded.Add($relative) -or $file.Value -cnotmatch '^[a-f0-9]{64}$') { throw "Invalid upstream file entry: $relative" }
        $expected.Add($relative, $file.Value)
    }
    if (-not $expected.ContainsKey("$addonName.toc")) { throw 'The upstream file list has no addon TOC.' }

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
    $stage = Join-Path $AddOnsPath ('.Zygor-install-' + [guid]::NewGuid().ToString('N'))
    [void][System.IO.Directory]::CreateDirectory($stage)
    if ($SourceArchive) {
        $archivePath = (Resolve-Path -LiteralPath $SourceArchive).Path
    } else {
        $archivePath = Join-Path $stage 'upstream.zip'
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
        Write-Host 'Downloading the pinned Zygor Guides Viewer version directly from its upstream project...'
        # Windows PowerShell 5.1 redraws its progress bar per received block,
        # which slows a large download many times over.
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $manifest.sourceArchive.url -OutFile $archivePath -UseBasicParsing
    }
    $payload = Join-Path $stage $addonName
    [void][System.IO.Directory]::CreateDirectory($payload)
    Expand-ZygorArchive $archivePath $payload $manifest.revision $expected
    Apply-ZygorChanges $payload ($utf8.GetString($patchBytes) | ConvertFrom-Json) $expected
    Assert-ZygorToc $payload
    [System.IO.File]::WriteAllBytes((Join-Path $payload 'SOURCE_MANIFEST.json'), $manifestBytes)
    [System.IO.File]::WriteAllBytes((Join-Path $payload 'SOURCE_REVISION.txt'), $utf8.GetBytes($manifest.revision + "`n"))
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
    Write-Host "Installed the matching Zygor Guides Viewer integration in $target"
    if ($backup) { Write-Host "Previous addon retained in $backup" }
    foreach ($standalone in 'ZygorGuidesViewer', 'ZygorTalentAdvisor') {
        if ([System.IO.Directory]::Exists((Join-Path $AddOnsPath $standalone))) {
            Write-Warning "Disable the separate $standalone addon; $addonName already contains its guide viewer and Talent Advisor."
        }
    }
    Write-Host 'Account and character SavedVariables were preserved. Enable Zygor Guides Viewer when starting WoW.'
} catch {
    [Console]::Error.WriteLine('Zygor Guides Viewer installation failed: ' + $_.Exception.Message)
    exit 1
} finally {
    if ($stage -and [System.IO.Directory]::Exists($stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
