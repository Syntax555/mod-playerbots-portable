[CmdletBinding()]
param(
    [string]$AddOnsPath,
    [string]$SourceArchive
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)

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
        throw 'Close World of Warcraft completely before installing Questie.'
    }
}

function Expand-QuestieArchive([string]$ArchivePath, [string]$Destination, [string]$Revision) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $prefix = "Questie-$Revision/"
    [long]$totalSize = 0
    try {
        if ($archive.Entries.Count -gt 100000) { throw 'The Questie archive has too many entries.' }
        foreach ($entry in $archive.Entries) {
            $path = Get-SafeRelativePath $entry.FullName
            if (-not $path.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
                throw "Unexpected root in Questie archive: $path"
            }
            if (-not $seen.Add($path.TrimEnd('/'))) { throw "Duplicate path in Questie archive: $path" }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000 -or
                ($entry.ExternalAttributes -band 0x400) -ne 0) {
                throw "Linked file in Questie archive: $path"
            }
            $relative = $path.Substring($prefix.Length)
            if (-not $relative) { continue }
            $target = Join-Path $Destination $relative
            $totalSize += $entry.Length
            if ($entry.Length -gt 67108864 -or $totalSize -gt 536870912) {
                throw 'The Questie archive exceeds the installation size limit.'
            }
            if ($path.EndsWith('/')) {
                if ($entry.Length -ne 0) { throw "Nonempty directory entry: $path" }
                [void][System.IO.Directory]::CreateDirectory($target)
            } else {
                [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target))
                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
            }
        }
    } finally { $archive.Dispose() }
}

function Apply-QuestieChanges([string]$Destination, $PatchData) {
    if ($PatchData.schemaVersion -ne 1 -or @($PatchData.files).Count -eq 0) { throw 'Invalid Questie patch data.' }
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $PatchData.files) {
        $relative = Get-SafeRelativePath $file.path
        if (-not $seen.Add($relative) -or $relative.EndsWith('/')) { throw "Duplicate or invalid patch path: $relative" }
        $path = Join-Path $Destination $relative
        $original = [System.IO.File]::ReadAllBytes($path)
        Assert-Hash $file.beforeSha256 $original "Original Questie file $relative"
        $lines = [System.Collections.Generic.List[string]]::new()
        $lines.AddRange([string[]]$utf8.GetString($original).Split([char]10))
        $previousStart = $lines.Count + 1
        foreach ($hunk in @($file.hunks | Sort-Object -Property start -Descending)) {
            if ([string]$hunk.start -notmatch '^\d+$' -or [string]$hunk.deleteCount -notmatch '^\d+$') {
                throw "Invalid patch range in $relative"
            }
            $start = [int]$hunk.start
            $count = [int]$hunk.deleteCount
            if ($start -gt $lines.Count -or $count -gt ($lines.Count - $start) -or
                $start -ge $previousStart -or ($start + $count) -gt $previousStart) {
                throw "Overlapping or out-of-range patch in $relative"
            }
            foreach ($line in @($hunk.lines)) {
                if ($line -isnot [string] -or $line.Contains("`n")) { throw "Invalid replacement line in $relative" }
            }
            $lines.RemoveRange($start, $count)
            $lines.InsertRange($start, [string[]]@($hunk.lines))
            $previousStart = $start
        }
        $patched = $utf8.GetBytes([string]::Join("`n", $lines))
        Assert-Hash $file.afterSha256 $patched "Patched Questie file $relative"
        [System.IO.File]::WriteAllBytes($path, $patched)
    }
}

$stage = $null
$backup = $null
$target = $null
try {
    $manifestPath = Join-Path $PSScriptRoot 'SOURCE_MANIFEST.json'
    $manifestBytes = [System.IO.File]::ReadAllBytes($manifestPath)
    $manifest = $utf8.GetString($manifestBytes) | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or $manifest.name -cne 'Questie-335' -or
        $manifest.repository -cne 'https://github.com/Aldori15/Questie.git' -or
        $manifest.revision -cnotmatch '^[a-f0-9]{40}$' -or $manifest.interface -ne 30300 -or
        $manifest.sourceArchive.url -cne "https://github.com/Aldori15/Questie/archive/$($manifest.revision).zip") {
        throw 'The installer has an invalid Questie source manifest.'
    }
    $patchBytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'PATCH_DATA.json'))
    Assert-Hash $manifest.patchDataSha256 $patchBytes 'Questie patch data'
    $patches = @($manifest.patches.PSObject.Properties)
    if ($patches.Count -eq 0) { throw 'The installer has no locked Questie patch.' }
    foreach ($patch in $patches) {
        if ($patch.Name -cnotmatch '^patches/[A-Za-z0-9_.-]+[.]patch$' -or $patch.Value -cnotmatch '^[a-f0-9]{64}$') {
            throw 'Invalid Questie patch provenance in the installer manifest.'
        }
    }
    Assert-WowClosed
    if (-not $AddOnsPath) { $AddOnsPath = Read-Host 'Enter the full path to your WoW 3.3.5a Interface\AddOns folder' }
    $AddOnsPath = [System.IO.Path]::GetFullPath($AddOnsPath.Trim().Trim('"'))
    if (-not [System.IO.Directory]::Exists($AddOnsPath)) { throw 'The selected Interface\AddOns folder does not exist.' }
    $target = Join-Path $AddOnsPath 'Questie-335'
    if ([System.IO.File]::Exists($target)) { throw 'Questie-335 is an existing file, not an addon folder.' }
    if ([System.IO.Directory]::Exists($target) -and
        ((Get-Item -LiteralPath $target -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'The existing Questie-335 folder is a link. Move it aside before installing.'
    }
    $stage = Join-Path $AddOnsPath ('.Questie-install-' + [guid]::NewGuid().ToString('N'))
    [void][System.IO.Directory]::CreateDirectory($stage)
    if ($SourceArchive) {
        $archivePath = (Resolve-Path -LiteralPath $SourceArchive).Path
    } else {
        $archivePath = Join-Path $stage 'upstream.zip'
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
        Write-Host 'Downloading the pinned Questie version directly from its upstream project...'
        # Windows PowerShell 5.1 redraws its progress bar per received block,
        # which slows a large download many times over.
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $manifest.sourceArchive.url -OutFile $archivePath -UseBasicParsing
    }
    Assert-Hash $manifest.sourceArchive.sha256 ([System.IO.File]::ReadAllBytes($archivePath)) 'Questie source archive'
    $payload = Join-Path $stage 'Questie-335'
    [void][System.IO.Directory]::CreateDirectory($payload)
    Expand-QuestieArchive $archivePath $payload $manifest.revision
    Apply-QuestieChanges $payload ($utf8.GetString($patchBytes) | ConvertFrom-Json)
    $toc = [System.IO.File]::ReadAllText((Join-Path $payload 'Questie-335.toc'), $utf8)
    $interfaces = [regex]::Matches($toc, '(?m)^##[ \t]*Interface[ \t]*:[ \t]*(\d+)[ \t]*\r?$')
    if ($interfaces.Count -ne 1 -or $interfaces[0].Groups[1].Value -ne '30300') {
        throw 'Questie must declare the WoW 3.3.5a interface version 30300 exactly once.'
    }
    foreach ($line in ($toc -split '\r?\n')) {
        $asset = $line.Trim().Replace('\', '/')
        if (-not $asset -or $asset.StartsWith('#')) { continue }
        $asset = Get-SafeRelativePath $asset
        if (-not [System.IO.File]::Exists((Join-Path $payload $asset))) { throw "Missing Questie TOC asset: $asset" }
    }
    [System.IO.File]::WriteAllBytes((Join-Path $payload 'SOURCE_MANIFEST.json'), $manifestBytes)
    [System.IO.File]::WriteAllBytes((Join-Path $payload 'SOURCE_REVISION.txt'), $utf8.GetBytes($manifest.revision + "`n"))
    # Both moves stay on the client filesystem. A failed replacement restores the old addon.
    Assert-WowClosed
    if ([System.IO.Directory]::Exists($target)) {
        $backup = Join-Path $AddOnsPath ('Questie-335.backup-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
        [System.IO.Directory]::Move($target, $backup)
    }
    try { [System.IO.Directory]::Move($payload, $target) }
    catch {
        if ($backup -and -not [System.IO.Directory]::Exists($target)) { [System.IO.Directory]::Move($backup, $target) }
        throw
    }
    Write-Host "Installed the matching Questie integration in $target"
    if ($backup) { Write-Host "Previous addon retained in $backup" }
    Write-Host 'Account and character SavedVariables were preserved. Enable Questie when starting WoW.'
} catch {
    [Console]::Error.WriteLine('Questie installation failed: ' + $_.Exception.Message)
    exit 1
} finally {
    if ($stage -and [System.IO.Directory]::Exists($stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
