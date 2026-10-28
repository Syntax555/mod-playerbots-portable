# AzerothCore Playerbots Portable

[![Build on main](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml?query=branch%3Amain)
[![Download](https://img.shields.io/badge/download-Latest-blue)](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
[![Client](https://img.shields.io/badge/client-3.3.5a%20%2812340%29-orange)](#requirements)
[![Launcher license](https://img.shields.io/badge/launcher%20license-MIT-green)](LICENSE)

A **Windows x64 server bundle for WoW 3.3.5a (build 12340)** with Playerbots and
individual progression through Vanilla, The Burning Crusade and Wrath of the
Lich King. Extract the server ZIP and run `startup.exe`; the launcher manages
MySQL, configuration, server data and server updates.

Each character earns its own content unlocks. Bots gain levels, equipment and
gold through ordinary play; controlled companions and SelfBots keep their
owner's talent choices. The server uses the Wrath core and client with selected
historical rules, rather than a complete recreation of each earlier expansion.

[Quick start](#quick-start) · [Downloads](#downloads) · [Configuration](#configuration) · [Documentation](#documentation)

## Highlights

- **Personal progression and historical talents:** earned milestones select
  content, level caps and Vanilla/TBC/Wrath talent trees. Matching client files
  provide historical spells and English/German text.
- **Bot companions and combat profiles:** MultiBot controls altbots and
  SelfBots; native class strategies and equipment scoring follow automatic or
  manually selected profiles. Talent spending for controlled characters stays manual.
- **Dungeons and raids:** nearby random bots can form groups for audited normal
  dungeons. Player-led groups use Dungeon Clear and native Raid Clear tactics.
  Autonomous routes require ordinary travel and supported event controllers;
  selected encounter shortcuts are guarded.
- **Earned world activity:** personal-era battlegrounds, ordinary auction
  trading, outdoor events and native quest-triggered world buffs.
- **Optional client interfaces:** DragonUI, Questie and Zygor reuse their native
  windows, quest display and guide/gear systems with the character's own data.
  See [addon installation and compatibility](docs/addons.md).

## Quick start

1. Download the **server ZIP and required EraTalents client pack** from
   [Downloads](#downloads).
2. Extract the server to a writable folder outside `Program Files`, such as
   `C:\Games\Playerbots`, and run `startup.exe`. First launch downloads about
   1.2 GB of server data and prepares databases and bot characters; allow it time.
3. When the console shows `All servers running`, create your account:

   ```text
   account create <username> <password>
   ```

4. Close WoW completely. Copy the client pack's
   `Interface/AddOns/EraTalents/` folder and `Data/patch-V.mpq` into your WoW
   folder; follow the [client setup guide](docs/era-talents.md#install-the-matching-client-files).
5. Install any [optional addons](docs/addons.md#addon-forks) with WoW closed.
   Questie and Zygor downloads are installers; they download the addon files
   from GitHub and need Internet access.
6. Set `set realmlist 127.0.0.1` in `Data/<locale>/realmlist.wtf`, such as
   `Data/enUS/realmlist.wtf`, then start WoW and log in. Bots begin logging in
   gradually from 30 seconds after a real player connects.

## Requirements

- **Server:** Windows 10/11 x64, a writable folder and Internet access for
  initial data and updates. The default target is **2,500 online bots** while
  a real player is connected; this is a configuration target, not a verified
  hardware capacity. Reduce `Playerbots.MinRandomBots` and
  `Playerbots.MaxRandomBots` for your host; see [population settings](docs/configuration.md#bots-and-population).
- **Client:** WoW 3.3.5a, build 12340, with the matching client pack, including
  for Vanilla and TBC progression. German clients receive German talent/spell text.
- The default configuration allows connections from the server PC. LAN or
  public hosting requires separate network configuration, which this package
  does not set up.

## Downloads

The server's [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
contains verified server and matching historical client packages. Optional
addons have their own releases and update independently.

| Package | Contents and installation |
| --- | --- |
| [Server bundle](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip) | Server, launcher, MySQL and configuration templates. Extract and run `startup.exe`. |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | **Required for every player.** Matching `EraTalents/` addon and `Data/patch-V.mpq`. |
| [MultiBot Chatless](https://github.com/Syntax555/MultiBot-Chatless/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional bot controls. Install `MultiBot/` in `Interface/AddOns/`. |
| [DragonUI](https://github.com/Syntax555/DragonUI/releases/latest/download/DragonUI-latest.zip) | Optional interface. Install both `DragonUI/` and `DragonUI_Options/`. |
| [Questie installer](https://github.com/Syntax555/Questie/releases/latest/download/Questie-335-latest.zip) | Extract outside WoW and run `Install-Questie.cmd`; [instructions](docs/questie-playerbots.md#installation). |
| [Zygor installer](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest/download/Zygor-IP-latest.zip) | Extract outside WoW and run `Install-Zygor.cmd`; [instructions](docs/zygor-progression.md#installation). |
| [SHA-256 checksums](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt) | Package and update-manifest hashes. |

## Running the server

`startup.exe` runs MySQL, authserver and worldserver and restarts a service if
it exits. Use **Ctrl+C in the launcher console** to stop the realm completely;
`server shutdown` alone allows the launcher to restart worldserver.

Startup checks Latest, verifies changed server files and installs updates.
Characters, databases, downloaded data and custom configuration are preserved.
**Client files update separately** with WoW closed. Before a manual update or
realm migration, follow the [backup and update guide](docs/updating.md).

Writable installations keep configuration, databases, logs and server data in
`configs/`, `mysql/data/`, `logs/` and `data/`. A non-writable installation uses
`%LOCALAPPDATA%\Playerbots` and disables automatic server updates; see
[data locations](docs/updating.md#where-your-data-lives).

| Launcher option | Purpose |
| --- | --- |
| `--no-update` | Start the installed release without an update check. |
| `--show-expansion`, `--set-expansion <mode>` | Inspect or select the [realm ceiling](docs/changing-expansions.md#optional-realm-ceilings). |
| `--help` | Show [all launcher options](docs/updating.md#launcher-options). |

## Configuration

Stop the realm before editing active files in `configs/` and
`configs/modules/`. Updates change managed defaults only when their previous
managed value is still present; explicit custom values are retained.

The [configuration reference](docs/configuration.md) covers population,
progression and shipped defaults. Use the dedicated guides for
[bot combat profiles](docs/combat-profiles.md),
[dungeons and the optional Dungeon Finder](docs/bot-dungeons.md#configuration),
[auctions](docs/earned-auctions.md#configuration),
[world buffs](docs/world-buffs.md#configuration) and
[outdoor events](docs/world-events.md#configuration).

## Troubleshooting

| Symptom | First check |
| --- | --- |
| Windows blocks `startup.exe` | Executables are unsigned. Verify the package against `SHA256SUMS.txt`; SmartScreen or Smart App Control may block it. |
| Update check is unavailable | The installed release starts. See [offline startup and failed updates](docs/updating.md#offline-startup-and-failed-updates). |
| Port is already in use | Defaults are MySQL 3306, authserver 3724 and worldserver 8085; see [launcher options](docs/updating.md#launcher-options). |
| Bots are offline | They log in gradually while a real player is connected and log out 60 seconds after the last player leaves; check [population settings](docs/configuration.md#bots-and-population). |
| Talents show Wrath trees or a stale generation | Install the matching client pack with WoW closed; see [client setup](docs/era-talents.md#install-the-matching-client-files). |
| Quest is missing or unavailable | Check that character's own prerequisites; see [quest diagnostics](docs/quest-diagnostics.md). |
| Addon blocks an action or raises Lua errors | Follow [addon diagnostics](docs/addons.md#blocked-interactions-and-lua-errors). |

For administration, grant a separate account GM access with
`account set gmlevel <username> 3 -1` in the worldserver console. Use an ordinary
account for gameplay. For a fresh realm or changed expansion ceiling, follow
[realm migration](docs/changing-expansions.md#updating-an-existing-realm).

When reporting a problem, copy `logs/` **before restarting**: each server start,
including automatic restarts, overwrites the server logs. Include the
`revision` from `portable-release.json` and a short reproduction; see
[reporting problems](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md#reporting-problems).

## Status and limitations

Automated checks cover launcher behavior, production-source rules and package
integrity. They do not verify every live encounter, client window or loaded
realm. Complete dungeon/raid runs, all class quests, sustained 2,500-bot load
and parts of the addon interfaces still need [in-game validation](docs/todo.md#gameplay-validation).

Historical talents use Vanilla 1.12.1 and TBC Classic 2.5.4 data. Selected
spells, experience, riding and battleground rules follow the earned era; other
systems retain Wrath core behavior. Autonomous raids are unavailable, and
unaudited dungeon routes, including Blackfathom Deeps and Stratholme, are not
recruited automatically. Some upstream encounter actions retain movement or
combat shortcuts. Existing inventories and gold are kept without an origin
audit. See [supported scope](docs/configuration.md#supported-scope).

## Included modules

The bundle builds the maintained Playerbots core with **nine native modules**:
Playerbots with integrated Raid Clear, Individual Progression, Era Talents,
Dungeon Clear, MultiBot Bridge, Quest Loot Party, LFG Progression, Era Events
and World Buff Bots. Runtime defaults and optional features differ from the
original projects' templates.

See the [module catalog and pinned sources](docs/module-versions.md#server-modules)
and [server adaptations](docs/adaptations.md). The
[Playerbots command reference](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands)
describes native commands; commands that grant gear, items, pets or summons, and bot mail commands, are
refused under the shipped earned-play policy.

## Documentation

| Guide | Use |
| --- | --- |
| [Progression](docs/changing-expansions.md) | Milestones, expansion ceilings, experience and realm migration. |
| [Historical talents and client setup](docs/era-talents.md) | Required files, manual talents, paid training and DragonUI. |
| [Client addons](docs/addons.md) | Downloads, compatibility and diagnostics for the optional interfaces. |
| [Combat profiles](docs/combat-profiles.md) | Class choices, SelfBots and equipment scoring. |
| [Dungeons and raids](docs/bot-dungeons.md) | Autonomous eligibility, player-led clears and encounter limits. |
| [Questie progress](docs/questie-playerbots.md) · [Zygor progression](docs/zygor-progression.md) | Bot quest display, guides and inspected-bot equipment recommendations. |
| [Class quests](docs/class-quests.md) · [Quest diagnostics](docs/quest-diagnostics.md) | Historical rewards, prerequisites and read-only diagnosis. |
| [Bot brackets and PvP](docs/earned-bot-brackets.md) · [Auctions](docs/earned-auctions.md) | Earned population and economy rules. |
| [World buffs](docs/world-buffs.md) · [World events](docs/world-events.md) | Native turn-ins, optional simulation and outdoor encounters. |
| [Running and updating](docs/updating.md) · [Configuration](docs/configuration.md) | Backups, updates, active files and defaults. |
| [Source versions](docs/module-versions.md) · [Third-party notices](THIRD_PARTY_NOTICES.md) | Exact sources, runtime versions and licenses. |
| [Roadmap](docs/todo.md) | Open implementation and validation work. |
| [Building](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md) · [Contributing](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md) | Source builds, fork workflow and targeted local checks. |

## Contributing

[Report an issue](https://github.com/Syntax555/mod-playerbots-portable/issues)
or follow the [contributing guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md).
Changes to native components and addons belong in their maintained forks;
the server pins the tested commits. Run relevant local checks before committing;
GitHub Actions runs the full suite and verifies manual release builds.

## License and credits

This continuation of [Onur Aslan's portable project](https://github.com/onur/mod-playerbots-portable)
is maintained by Syntax555. The launcher and build tooling use the
[MIT License](LICENSE); the core, modules, addons and source data retain their
own terms. [Third-party notices](THIRD_PARTY_NOTICES.md) preserve the original
authors, licenses and packaged notice locations.
