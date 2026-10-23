# Questie Playerbots installer

This installer prepares Questie for the matching portable server and WoW
3.3.5a build 12340. You do not need to build the server or install development
tools. Internet access and Windows PowerShell 5.1 or later are required.

1. Extract this ZIP to a writable folder outside your WoW installation.
2. Close WoW completely. Run `Install-Questie.cmd`.
3. Enter your client's `Interface\AddOns` folder when prompted.
4. Enable Questie in the character selection screen. Enable **Show party
   quest objectives** in Questie to display other group members' quest markers.

The installer downloads the pinned original Questie archive directly from
`Aldori15/Questie` on GitHub. It checks the archive and patched file hashes
before installing `Questie-335`. An existing `Questie-335` folder is backed up;
account and character SavedVariables are preserved. Install matching server
updates through the portable launcher's normal update process.

For a noninteractive installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Questie.ps1 -AddOnsPath 'C:\Games\WoW\Interface\AddOns'
```

`SOURCE_MANIFEST.json` records the original revision, archive checksum and
local patch hashes. `PATCH_DATA.json` contains only the local changes needed
to adapt the downloaded original. The complete upstream addon, graphics and
libraries are not redistributed in this ZIP. Their original terms and notices
remain applicable. The included MIT license covers the installer tooling;
it does not relicense Questie or its dependencies.

Automated source and installation checks do not replace an in-game test.
See the [integration guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/questie-playerbots.md)
for supported behavior and the remaining live validation.
