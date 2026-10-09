Prebuilt Windows x64 server for **WoW 3.3.5a (build 12340)**, with Playerbots and individual progression through Vanilla, The Burning Crusade and Wrath of the Lich King.

| Download | Use |
| --- | --- |
| [Server ZIP]({repository_url}/releases/latest/download/mod-playerbots-portable-latest.zip) | Extract and run `startup.exe`. MySQL is included; client data and databases are prepared on first launch. |
| [EraTalents client pack]({repository_url}/releases/latest/download/EraTalents-client-latest.zip) | Required. Install its `Interface/AddOns/EraTalents/` folder and `Data/patch-V.mpq` in your client, then fully restart WoW. |
| [MultiBot addon]({repository_url}/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional bot controls. Install its `MultiBot/` folder in `Interface/AddOns/`. |
| [SHA-256 checksums]({repository_url}/releases/latest/download/SHA256SUMS.txt) | Verify the packages and update manifest. |

Set the client realmlist to `set realmlist 127.0.0.1`. Create your account in the worldserver console with `account create <username> <password>`.

`startup.exe` checks Latest before starting services, shows update progress, downloads changed server files, verifies their hashes and restarts after installation. Configuration defaults merge automatically while preserving custom values, characters, databases, downloaded maps and the selected realm mode.

See the [update guide]({source_url}/docs/updating.md) for manual installation, backups and recovery. Install matching client files separately with WoW closed.

First startup requires Internet access and can take time while preparing data and the bot population. The executables are unsigned; Windows Smart App Control can block them.

[Setup and features]({source_url}/README.md) · [Updates]({source_url}/docs/updating.md) · [Configuration]({source_url}/docs/vanilla-config-audit.md) · [Server adaptations]({source_url}/docs/adaptations.md) · [Client installation]({source_url}/docs/era-talents.md) · [Licenses]({source_url}/THIRD_PARTY_NOTICES.md)

Source: [{revision}]({commit_url}). The server ZIP contains its dependency manifest, applied patches and license notices.
