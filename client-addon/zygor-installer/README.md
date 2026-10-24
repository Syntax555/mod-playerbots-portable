# Zygor Guides Viewer Individual Progression installer

This installer prepares Zygor Guides Viewer Remaster for the matching portable
server and WoW 3.3.5a build 12340. Guides, the Gear Finder and the Talent
Advisor then follow each character's own Individual Progression tier. You do
not need to build the server or install development tools. Internet access and
Windows PowerShell 5.1 or later are required.

1. Extract this ZIP to a writable folder outside your WoW installation.
2. Close WoW completely. Run `Install-Zygor.cmd`.
3. Enter your client's `Interface\AddOns` folder when prompted.
4. Enable Zygor Guides Viewer in the character selection screen. Disable a
   separate `ZygorGuidesViewer` or `ZygorTalentAdvisor` addon if present.

The installer downloads the pinned original archive directly from
`ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK` on GitHub. It checks every file
of the `ZygorGuidesViewerRM` folder and every patched file against SHA-256
hashes before installing `ZygorGuidesViewerRM`. An existing
`ZygorGuidesViewerRM` folder is backed up; account and character
SavedVariables are preserved. Install matching server updates through the
portable launcher's normal update process.

For a noninteractive installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Zygor.ps1 -AddOnsPath 'C:\Games\WoW\Interface\AddOns'
```

`SOURCE_MANIFEST.json` records the original revision and local patch hashes.
`UPSTREAM_FILES.json` lists the original files with their hashes, and
`PATCH_DATA.json` contains only the local changes needed to adapt them. The
upstream addon, guides, graphics and libraries are not redistributed in this
ZIP. Their original terms and notices remain applicable. The included MIT
license covers the installer tooling; it does not relicense Zygor Guides
Viewer or its dependencies.

Automated source and installation checks do not replace an in-game test.
See the [integration guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/zygor-progression.md)
for supported behavior and the remaining live validation.
