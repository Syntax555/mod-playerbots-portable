Prebuilt Windows x64 server for **WoW 3.3.5a (build 12340)**, with Playerbots and individual progression through Vanilla, The Burning Crusade and Wrath of the Lich King.

| Download | Use |
| --- | --- |
| [Server ZIP]({repository_url}/releases/latest/download/mod-playerbots-portable-latest.zip) | Extract and run `startup.exe`. MySQL is included; client data and databases are prepared on first launch. |
| [EraTalents client pack]({repository_url}/releases/latest/download/EraTalents-client-latest.zip) | Required. Install its `Interface/AddOns/EraTalents/` folder and `Data/patch-V.mpq` in your client, then fully restart WoW. |
| [MultiBot addon]({repository_url}/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional bot controls. Install its `MultiBot/` folder in `Interface/AddOns/`. |
| [SHA-256 checksums]({repository_url}/releases/latest/download/SHA256SUMS.txt) | Verify the downloaded ZIPs. |

Set the client realmlist to `set realmlist 127.0.0.1`. Create your account in the worldserver console with `account create <username> <password>`.

For an existing realm, stop the servers, install the complete server ZIP and matching client pack, then run these commands separately:

```powershell
.\startup.exe --set-expansion individual
.\startup.exe --apply-profiles
```

Existing characters and databases are preserved. First startup requires Internet access and can take time while preparing data and the bot population.

[Setup and features]({source_url}/README.md) · [Configuration]({source_url}/docs/vanilla-config-audit.md) · [Client installation]({source_url}/docs/era-talents.md) · [Licenses]({source_url}/THIRD_PARTY_NOTICES.md)

Source: [{revision}]({commit_url}). The server ZIP contains its dependency manifest, applied patches and license notices.
