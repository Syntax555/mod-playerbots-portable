# AzerothCore Playerbots Portable

[![Build](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml/badge.svg)](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml)
[![Download](https://img.shields.io/badge/download-Latest-blue)](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
[![Client](https://img.shields.io/badge/client-3.3.5a%20%2812340%29-orange)](#requirements)
[![Launcher license](https://img.shields.io/badge/launcher%20license-MIT-green)](LICENSE)

A portable **Windows x64** server for World of Warcraft 3.3.5a, built on [AzerothCore](https://github.com/azerothcore/azerothcore-wotlk) and [Playerbots](https://github.com/mod-playerbots/mod-playerbots). Extract the ZIP and run `startup.exe`; the launcher manages the bundled database, server configuration and first-run setup.

## Features

- **Earned progression:** players and bots complete their own content milestones through Vanilla, The Burning Crusade and Wrath of the Lich King.
- **Historical talents:** Vanilla and TBC talent trees follow each character's earned era, with native Wrath trees after the Wrath unlock.
- **Level 1 bots:** bots earn their levels, equipment and gold. Resident bots remain in selected level brackets after reaching them through gameplay.
- **An earned economy:** bots sell surplus owned loot and buy with their own gold, using normal auction fees and mailbox delivery. A fresh market grows as bots acquire tradable items.
- **Companions and battlegrounds:** bots can join parties, while eligible bots fill real players' battleground queues. AutoBalance adjusts instance difficulty to the party size.

## Download

The [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest) contains matching server and client packages.

| Package | Use |
| --- | --- |
| [Server bundle](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip) | Portable server, launcher, database and configuration defaults. |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | **Required** for the default historical talents: addon and merged `patch-V.mpq`. |
| [MultiBot Chatless](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional interface for managing your bot companions. |
| [SHA-256 checksums](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt) | Verify the downloaded ZIPs. |

Download the server and client pack together when installing or updating.

## Requirements

- Windows 10/11 x64 and a writable server folder.
- A WoW **3.3.5a client, build 12340**, including for Vanilla and TBC progression.
- Internet access for the first-run client-data download.
- Sufficient CPU, memory and storage for your selected bot population. The default target is **2,500 bots while a real player is connected**; capacity depends on your hardware and active content.

## Get started

1. Extract the server bundle and run `startup.exe`. On first launch, it downloads missing DBC/maps/vmaps/mmaps, initializes the database and applies server SQL. Initial setup and bot creation can take considerable time.
2. Create a player account in the worldserver console:

   ```text
   account create <username> <password>
   ```

3. Close WoW completely. Extract the client pack into your client folder so it contains:

   ```text
   Interface/AddOns/EraTalents/EraTalents.toc
   Data/patch-V.mpq
   ```

   Replace an existing Individual Progression `patch-V.mpq` with the matching merged file. Both the addon and MPQ are required; `/reload` cannot load an MPQ.
4. Set the client's realmlist to `set realmlist 127.0.0.1`, restart WoW and log in.

Services bind locally by default. Use an ordinary player account for progression. See [EraTalents installation](docs/era-talents.md#install-the-matching-client-files) for client checks and [configuration](docs/vanilla-config-audit.md) to customize the realm.

### Optional MultiBot interface

Extract the addon ZIP's `MultiBot` folder into `Interface/AddOns/`. Its final path must be `Interface/AddOns/MultiBot/MultiBot.toc`. The server bundle also includes a copy under `addons/MultiBot/`.

When updating, remove the old client `MultiBot` folder before copying the new one. Restart WoW, enable the addon and open it with `/multibot`, `/mbot` or `/mb`. The interface uses [MultiBot Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) with the bundled bridge; server progression rules also apply to addon requests.

## Updating an existing realm

Back up your databases and configuration, stop the launcher and servers, and install the complete server bundle. Update each player's matching EraTalents client files, then run these commands separately from PowerShell in the server folder:

```powershell
.\startup.exe --set-expansion individual
.\startup.exe --apply-profiles
```

Start `startup.exe` normally afterwards. Characters, inventories, money and databases are preserved. Changed configuration files are backed up; database credentials, paths and unrelated custom settings remain intact. The commands select earned individual progression and apply the bundled defaults to an existing installation.

Existing possessions retain their history; an update cannot establish that older equipment or gold was earned. See [realm migration](docs/changing-expansions.md#updating-an-existing-realm) and [talent migration](docs/era-talents.md#updating-an-existing-realm) before changing an established realm's progression rules.

## Included modules

| Module | Default role |
| --- | --- |
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | Bot companions, natural progression and earned auction trading. |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | Character-specific content milestones and expansion unlocks. |
| [Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents) | Earned-era talents and selected class spell variants for players and bots. |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | Instance scaling for the players and bots present. |
| [Quest Loot Party](https://github.com/pangolp/mod-quest-loot-party) | Shared normal-quality quest-item loot for eligible party members. |
| [MultiBot Bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | Server support for the MultiBot Chatless interface. |
| [Token Turn-in](https://github.com/Zerathane/mod-token-turnin) | Token inventory checks; rewards still require the ordinary NPC exchange. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | Optional dungeon routes; disabled in the earned-play profile. |
| [AH Bot Plus](https://github.com/NathanHandley/mod-ah-bot-plus) | Optional generated market; seller and buyer disabled in the earned economy. |

## Supported scope

The server uses the Wrath core and client. Historical trees use **Vanilla 1.12.1** and **TBC Classic 2.5.4** data; TBC is not an exact original 2.4.3 simulation. Selected class spells, riding prices and battleground rules follow the earned era, while other world prices, combat formulas and systems retain core behavior.

Bots fill Warsong Gulch, Arathi Basin and Alterac Valley, then unlock Eye of the Storm with TBC and Isle of Conquest with Wrath. Bot Strand of the Ancients, random battleground and arena queues are disabled. Humans unlock those activities through progression; TBC arenas are skirmishes only, and rated arenas require earned Wrath and level 80. Matches still need enough eligible participants.

Bot questing, navigation and encounter support varies by content. Bots can get stuck or lack supplies, and some upstream encounter scripts retain special movement or combat shortcuts. Historical balance and completion of every raid are not guaranteed. See [supported scope and configuration](docs/vanilla-config-audit.md#supported-scope) for the current limits.

## Documentation

| Guide | Topics |
| --- | --- |
| [Progression](docs/changing-expansions.md) | Content milestones, expansion modes and realm migration. |
| [EraTalents](docs/era-talents.md) | Client installation, training, talents and compatibility. |
| [Bot brackets](docs/earned-bot-brackets.md) | Resident levels, population and battleground eligibility. |
| [Auction economy](docs/earned-auctions.md) | Trading behavior, settings and market limits. |
| [Configuration](docs/vanilla-config-audit.md) | Default settings, module behavior and supported scope. |
| [Source versions](docs/module-versions.md) | Pinned dependencies and reproducible adaptations. |
| [Building from source](docs/building.md) | Windows build requirements and package generation. |

Bot commands are documented in the [Playerbots wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands).

## Contributing

[Report a problem](https://github.com/Syntax555/mod-playerbots-portable/issues) with your source manifest, relevant configuration, logs and steps to reproduce. Pull requests are welcome; use the [build guide](docs/building.md) to reproduce the bundled sources and validate changes.

## License and credits

The portable launcher and build tooling use the [MIT License](LICENSE). AzerothCore, modules and addons retain their upstream licenses and notices; see [third-party notices](THIRD_PARTY_NOTICES.md) for attribution, packaged license paths and pinned source references.

Built with AzerothCore, Playerbots and the module authors linked above. First-run server data is provided by the [wowgaming client-data project](https://github.com/wowgaming/client-data).
