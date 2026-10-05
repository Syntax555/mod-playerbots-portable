[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$AddonName,
    [string]$RepositoryRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$lock = Get-Content (Join-Path $RepositoryRoot 'versions.lock.json') -Raw | ConvertFrom-Json
if ($lock.schemaVersion -ne 1) { throw 'Unsupported versions.lock.json schema.' }
$addons = @($lock.clientAddons | Where-Object { $_.name -ceq $AddonName })
if ($addons.Count -ne 1) { throw "Expected one locked client addon named $AddonName." }
$addon = $addons[0]
if ($AddonName -cnotmatch '^[A-Za-z0-9_-]+$' -or $addon.toc -cne "$AddonName.toc" -or
    $addon.license -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or
    $addon.revision -cnotmatch '^[a-f0-9]{40}$' -or $addon.interface -ne 30300) {
    throw "Invalid pinned WotLK client addon: $AddonName"
}
$source = Join-Path $RepositoryRoot ".module-cache/prepared-addons/$AddonName"
if (-not (Test-Path (Join-Path $source '.portable-source') -PathType Leaf)) {
    throw "Prepared client addon source is missing: $AddonName"
}

function Read-ZipText([System.IO.Compression.ZipArchiveEntry]$Entry) {
    $reader = [System.IO.StreamReader]::new($Entry.Open())
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}

$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ZipPath).Path)
try {
    $entries = [System.Collections.Generic.Dictionary[string, System.IO.Compression.ZipArchiveEntry]]::new([System.StringComparer]::Ordinal)
    $paths = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $archive.Entries) {
        $path = $entry.FullName
        # Reject traversal, alternate separators, case collisions and foreign roots.
        if ($path.Contains('\') -or $path.Contains(':') -or $path.StartsWith('/') -or
            $path -match '(^|/)\.{1,2}(/|$)|//' -or
            $path -match '(^|/)(\.git|\.github|\.portable-source)(/|$)' -or
            -not $path.StartsWith("$AddonName/", [System.StringComparison]::Ordinal)) {
            throw "Unexpected path in client addon ZIP: $path"
        }
        $key = $path.TrimEnd('/')
        if (-not $paths.Add($key)) { throw "Duplicate path in client addon ZIP: $path" }
        $unixType = ($entry.ExternalAttributes -shr 16) -band 0xF000
        if ($unixType -eq 0xA000) { throw "Symbolic link in client addon ZIP: $path" }
        if ($path.EndsWith('/')) {
            if ($entry.Length -ne 0) { throw "Nonempty directory entry in client addon ZIP: $path" }
            $relative = $path.Substring($AddonName.Length + 1).TrimEnd('/')
            $directory = if ($relative) { Join-Path $source $relative } else { $source }
            if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
                throw "Unexpected directory in client addon ZIP: $path"
            }
            continue
        }
        $entries.Add($path, $entry)
    }

    foreach ($relative in @($addon.toc, $addon.license, 'README.md', 'SOURCE_REVISION.txt')) {
        $path = "$AddonName/$relative"
        if (-not $entries.ContainsKey($path) -or $entries[$path].Length -eq 0) {
            throw "Client addon ZIP is missing required nonempty file $path"
        }
    }
    $revision = (Read-ZipText $entries["$AddonName/SOURCE_REVISION.txt"]).Trim()
    if ($revision -cne $addon.revision) { throw "Client addon $AddonName differs from its locked source revision." }
    $tocText = Read-ZipText $entries["$AddonName/$($addon.toc)"]
    $interfaces = [regex]::Matches($tocText, '(?m)^##[ \t]*Interface[ \t]*:[ \t]*(\d+)[ \t]*\r?$')
    if ($interfaces.Count -ne 1 -or $interfaces[0].Groups[1].Value -ne '30300') {
        throw "Client addon $AddonName must declare WotLK Interface 30300 exactly once."
    }
    foreach ($line in ($tocText -split '\r?\n')) {
        $asset = $line.Trim().Replace('\', '/')
        if (-not $asset -or $asset.StartsWith('#')) { continue }
        if ($asset.StartsWith('/') -or $asset.Contains(':') -or $asset -match '(^|/)\.{1,2}(/|$)|//' -or
            -not $entries.ContainsKey("$AddonName/$asset") -or $entries["$AddonName/$asset"].Length -eq 0) {
            throw "Client addon $AddonName has a missing or invalid TOC asset: $asset"
        }
    }

    # Verify every prepared asset byte-for-byte via SHA-256, including binary textures.
    $expected = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        foreach ($item in Get-ChildItem -LiteralPath $source -Recurse -Force) {
            $relative = [System.IO.Path]::GetRelativePath($source, $item.FullName).Replace('\', '/')
            if ($relative -match '(^|/)(\.git|\.github|\.portable-source)(/|$)') { continue }
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Symbolic link in prepared client addon: $relative"
            }
            if ($item.PSIsContainer) { continue }
            $path = "$AddonName/$relative"
            [void]$expected.Add($path)
            if (-not $entries.ContainsKey($path)) { throw "Client addon ZIP is missing asset $path" }
            $entry = $entries[$path]
            if ($entry.Length -ne $item.Length) { throw "Packaged client addon asset differs from prepared source: $path" }
            $stream = $entry.Open()
            try { $packagedHash = [System.BitConverter]::ToString($sha256.ComputeHash($stream)) } finally { $stream.Dispose() }
            $stream = [System.IO.File]::OpenRead($item.FullName)
            try { $sourceHash = [System.BitConverter]::ToString($sha256.ComputeHash($stream)) } finally { $stream.Dispose() }
            if ($packagedHash -cne $sourceHash) { throw "Packaged client addon asset differs from prepared source: $path" }
        }
    } finally {
        $sha256.Dispose()
    }
    foreach ($path in $entries.Keys) {
        if (-not $expected.Contains($path)) { throw "Unexpected asset in client addon ZIP: $path" }
    }
    Write-Host "Verified standalone client addon ZIP: $AddonName, $($entries.Count) files matching prepared assets, WotLK TOC, license and source revision."
} finally {
    $archive.Dispose()
}
