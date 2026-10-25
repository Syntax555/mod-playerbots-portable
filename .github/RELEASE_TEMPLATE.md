Prebuilt Windows x64 server for **WoW 3.3.5a (build 12340)**, with Playerbots and individual progression through Vanilla, The Burning Crusade and Wrath of the Lich King.

| Download | Use |
| --- | --- |
| [Server ZIP]({repository_url}/releases/latest/download/mod-playerbots-portable-latest.zip) | Extract and run `startup.exe`. MySQL is included; about 1.2 GB of server data and the databases are prepared on first launch. |
| [EraTalents client pack]({repository_url}/releases/latest/download/EraTalents-client-latest.zip) | Required. Install its `Interface/AddOns/EraTalents/` folder and `Data/patch-V.mpq` in your client, then fully restart WoW. |
| [MultiBot addon](https://github.com/Syntax555/MultiBot-Chatless/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional bot controls. Install its `MultiBot/` folder in `Interface/AddOns/`. |
| [DragonUI](https://github.com/Syntax555/DragonUI/releases/latest/download/DragonUI-latest.zip) | Optional interface. Install its `DragonUI/` and `DragonUI_Options/` folders in `Interface/AddOns/`; EraTalents adapts it to each character's era. |
| [Questie-335 installer](https://github.com/Syntax555/Questie/releases/latest/download/Questie-335-latest.zip) | Optional quest addon with bot progress integration. Extract and run `Install-Questie.cmd` with Internet access; see [installation]({source_url}/docs/questie-playerbots.md#installation). |
| [Zygor IP installer](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest/download/Zygor-IP-latest.zip) | Optional Zygor Guides Viewer that follows each character's Individual Progression tier. Extract and run `Install-Zygor.cmd` with Internet access; see [installation]({source_url}/docs/zygor-progression.md#installation). |
| [SHA-256 checksums]({repository_url}/releases/latest/download/SHA256SUMS.txt) | Verify the packages and update manifest. |

Set `set realmlist 127.0.0.1` in the client's `Data/<locale>/realmlist.wtf`. Create your account in the worldserver console with `account create <username> <password>`.

`startup.exe` checks Latest before starting services, shows update progress, downloads changed server files, verifies their hashes and restarts after installation. Configuration defaults merge automatically while preserving custom values, characters, databases, downloaded maps and the selected realm mode.

See the [update guide]({source_url}/docs/updating.md) for manual installation, backups and recovery. Install matching client files separately with WoW closed.

First startup requires Internet access and can take time while preparing data and the bot population. The executables are unsigned; Windows Smart App Control can block them.

[Setup and features]({source_url}/README.md) · [Updates]({source_url}/docs/updating.md) · [Configuration]({source_url}/docs/configuration.md) · [Server adaptations]({source_url}/docs/adaptations.md) · [Client installation]({source_url}/docs/era-talents.md) · [Licenses]({source_url}/THIRD_PARTY_NOTICES.md)

Source: [{revision}]({commit_url}). The server ZIP contains its dependency manifest, applied patches and license notices.
