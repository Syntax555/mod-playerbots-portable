# AzerothCore Playerbots Portable

[![Build](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml/badge.svg)](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml)
[![Download](https://img.shields.io/badge/download-Latest-blue)](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
[![Client](https://img.shields.io/badge/client-3.3.5a%20%2812340%29-orange)](#requirements)
[![Launcher license](https://img.shields.io/badge/launcher%20license-MIT-green)](LICENSE)

A portable **Windows x64** server for World of Warcraft 3.3.5a, built on [AzerothCore](https://github.com/azerothcore/azerothcore-wotlk) and [Playerbots](https://github.com/mod-playerbots/mod-playerbots). Extract the ZIP and run `startup.exe`; the launcher manages server updates, the bundled database, configuration and first-run setup.

## Features

- **Earned progression:** players and bots complete their own content milestones through Vanilla, The Burning Crusade and Wrath of the Lich King.
- **Historical talents:** Vanilla and TBC talent trees follow each character's earned era, with German and English talent/spell text and native Wrath trees after the Wrath unlock.
- **Level 1 bots:** bots earn their levels, equipment and gold. Resident bots remain in selected level brackets after reaching them through gameplay.
- **An earned economy:** bots sell surplus owned loot and buy with their own gold, using normal auction fees and mailbox delivery. A fresh market grows as bots acquire tradable items.
- **Companions and battlegrounds:** bots can join parties, while eligible bots fill real players' battleground queues. AutoBalance adjusts instance difficulty to the party size.

## Download

The [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest) contains matching server and client packages.

| Package | Use |
| --- | --- |
| [Server bundle](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip) | Portable server, launcher, database and configuration templates. |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | **Required** for the default historical talents: addon and merged `patch-V.mpq`. |
| [MultiBot Chatless](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional interface for managing your bot companions. |
| [SHA-256 checksums](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt) | Verify the packages and update manifest. |

Install the server bundle and matching EraTalents client pack. MultiBot is an optional separate download.

## Requirements

- Windows 10/11 x64 and a writable server folder.
- A WoW **3.3.5a client, build 12340**, including for Vanilla and TBC progression.
- Internet access for automatic server updates and the first-run server-data download.
- Sufficient CPU, memory and storage for your selected bot population. The default target is **2,500 bots while a real player is connected**; capacity depends on your hardware and active content.

The executables are unsigned and may be blocked by Windows Smart App Control.

## Installation

1. Extract the server bundle and run `startup.exe`. The launcher checks for updates, downloads required server data and initializes the realm automatically. Allow time for initial setup and bot creation.
2. Create a player account in the worldserver console:

   ```text
   account create <username> <password>
   ```

3. Close WoW completely. Extract the client pack into your client folder so it contains:

   ```text
   Interface/AddOns/EraTalents/EraTalents.toc
   Data/patch-V.mpq
   ```

   Use both the addon and the client pack's `patch-V.mpq`. Install with WoW fully closed.
4. Set the client's realmlist to `set realmlist 127.0.0.1`, restart WoW and log in.

Services bind locally by default. Use an ordinary player account for progression. See [EraTalents installation](docs/era-talents.md#install-the-matching-client-files) for client checks and [configuration](docs/vanilla-config-audit.md) to customize the realm.

### Optional MultiBot interface

With WoW closed, remove `Interface/AddOns/MultiBot/` if present, then extract the separate ZIP's `MultiBot` folder into `Interface/AddOns/`. The final path is `Interface/AddOns/MultiBot/MultiBot.toc`. Restart WoW, enable the addon and open it with `/multibot`, `/mbot` or `/mb`.

Open its settings with `/mbopt` or **Interface → AddOns → MultiBot**. The settings cover the minimap button, layout, frame layering and update intervals.

## Updates

Start `startup.exe` normally to check [Latest](https://github.com/Syntax555/mod-playerbots-portable/releases/latest), download changed server files and restart after verified installation. SQL migrations and configuration updates run automatically. Characters, databases, downloaded map data, custom settings and the selected realm mode are preserved.

See the [update guide](docs/updating.md) for manual installation, backups, offline startup and recovery. Install matching client packages for each player with WoW closed.

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

Battleground and arena access follows earned progression; see [PvP rules](docs/earned-bot-brackets.md). Bot questing, navigation and encounter support varies by content, and some upstream encounters use movement or combat shortcuts. Existing inventories and gold are preserved without verifying their origin. See [supported scope](docs/vanilla-config-audit.md#supported-scope) for gameplay limits.

## Documentation

| Guide | Topics |
| --- | --- |
| [Progression](docs/changing-expansions.md) | Content milestones, expansion modes and realm migration. |
| [EraTalents](docs/era-talents.md) | Client installation, training, talents and compatibility. |
| [Bot brackets](docs/earned-bot-brackets.md) | Resident levels, population and battleground eligibility. |
| [Auction economy](docs/earned-auctions.md) | Trading behavior, settings and market limits. |
| [Configuration](docs/vanilla-config-audit.md) | Default settings, module behavior and supported scope. |
| [Updates](docs/updating.md) | Automatic updates, manual installation, backups and recovery. |
| [Source versions](docs/module-versions.md) | Pinned dependencies and reproducible adaptations. |
| [Building from source](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md) | Windows build requirements and package generation. |

Bot commands are documented in the [Playerbots wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands).

## Contributing

[Report a problem](https://github.com/Syntax555/mod-playerbots-portable/issues) with your source manifest, relevant configuration, logs and steps to reproduce. Pull requests are welcome; use the [build guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md) to reproduce the bundled sources and validate changes.

## License and credits

The portable launcher and build tooling use the [MIT License](LICENSE). AzerothCore, modules and addons retain their upstream licenses and notices; see [third-party notices](THIRD_PARTY_NOTICES.md) for attribution, packaged license paths and pinned source references.

Built with AzerothCore, Playerbots and the module authors linked above. First-run server data is provided by the [wowgaming client-data project](https://github.com/wowgaming/client-data).
