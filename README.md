# AzerothCore Playerbots Portable

[![Build on main](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/Syntax555/mod-playerbots-portable/actions/workflows/release.yml?query=branch%3Amain)
[![Download](https://img.shields.io/badge/download-Latest-blue)](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
[![Client](https://img.shields.io/badge/client-3.3.5a%20%2812340%29-orange)](#requirements)
[![Launcher license](https://img.shields.io/badge/launcher%20license-MIT-green)](LICENSE)

An independently maintained **Windows x64 distribution** for World of Warcraft
3.3.5a, integrating character-specific progression through Vanilla, The Burning
Crusade and Wrath of the Lich King with
[AzerothCore](https://github.com/azerothcore/azerothcore-wotlk),
[Playerbots](https://github.com/buildthehomelab/wow-mod-playerbots) and community modules.

This project continues [Onur Aslan's portable server project](https://github.com/onur/mod-playerbots-portable)
with earned-play integrations, historical client packages and automatic server
updates. Extract the ZIP and run `startup.exe`; the launcher manages the
database, configuration and first-run setup.

[Downloads](#downloads) · [Quick start](#quick-start) · [Documentation](#documentation) · [Contributing](#contributing)

## Highlights

- **Earned progression:** players and bots unlock content through their own
  milestones, and experience follows each character's era. Bots start at level
  1 with ordinary starter equipment and earn levels, gold and upgrades. See
  [progression](docs/changing-expansions.md).
- **Historical talents:** Era Talents integration selects Vanilla, TBC or Wrath
  talent systems from each character's earned era. Matching client files include
  German and English text and selected restored class spells. See
  [historical talents](docs/era-talents.md).
- **Client addons for earned play:** DragonUI's talent window, spellbook and
  level-up notice follow each character's era and trainer list; MultiBot opens
  and trains controlled altbots' historical trees and shows bot spellbooks in
  DragonUI's book; Questie shows group bots' quest progress; Zygor guides, Gear
  Finder and Talent Advisor follow each character's tier. These addons are
  published by their
  [forks](docs/addons.md#addon-forks), each with its own Latest download.
- **Bot combat profiles:** MultiBot offers automatic talent detection and manual
  specialization choices. Class strategies, role support and equipment scoring
  follow the same profile; bots equip suitable gear from their own bags. See
  [combat profiles and equipment](docs/combat-profiles.md).
- **Autonomous dungeon parties:** nearby random bots form five-member groups for
  audited normal dungeons in their own era and walk to the entrance. See
  [routes and requirements](docs/bot-dungeons.md#autonomous-parties).
- **Player-led raids:** Dungeon Clear, Playerbots and Raid Clear provide group
  control and encounter tactics, including Onyxia's Lair, Molten Core, Blackwing Lair,
  Zul'Gurub and Ahn'Qiraj. Autonomous raid runs remain unavailable.
  See [raid support](docs/bot-dungeons.md#raids).
- **Earned bot economy:** bots train, repair and buy supplies and bags with
  their own gold, and trade owned items through normal auctions and mailbox
  delivery.
  See [auction trading](docs/earned-auctions.md).
- **Automatic server updates:** the launcher downloads changed files, verifies
  hashes and preserves characters, databases and custom settings. Matching
  client packages are installed separately. See [updates](docs/updating.md).
- **Portable Windows setup:** the ZIP includes the server, launcher, MySQL and
  configuration templates. Required server data is downloaded on first start.
- **Companions and world activity:** SelfBot and controlled bot companions,
  earned-era battleground queues, timed [era world events](docs/world-events.md),
  and quest-triggered [world buffs](docs/world-buffs.md) complement individual
  progression.

## Quick start

1. Download the server ZIP and the EraTalents client pack from
   [Downloads](#downloads).
2. Extract the server ZIP to a writable folder outside `Program Files`, such as
   `C:\Games\Playerbots`, and run `startup.exe`. The first start downloads about
   1.2 GB of server data and creates the databases and bots; allow it time.
3. When the console shows `All servers running`, create your account in it:

   ```text
   account create <username> <password>
   ```

4. With WoW closed, copy the client pack's `Interface/AddOns/EraTalents/` folder
   and `Data/patch-V.mpq` into your WoW folder; see
   [client installation](docs/era-talents.md#install-the-matching-client-files).
5. Optionally install MultiBot, DragonUI, Questie or Zygor from
   [Downloads](#downloads).
6. Set `set realmlist 127.0.0.1` in your client's `Data/<locale>/realmlist.wtf`,
   for example `Data/enUS/realmlist.wtf` or `Data/deDE/realmlist.wtf`. Start WoW
   and log in. Bots log in gradually from 30 seconds after you connect.

## Requirements

- **Server:** Windows 10/11 x64, a writable server folder and Internet access
  for the first-run server data download and automatic updates. CPU, memory and
  storage needs grow with the bot population: the default target is 2,500 bots
  while a real player is connected. Lower `Playerbots.MinRandomBots` and
  `Playerbots.MaxRandomBots` to fit the host; see
  [bots and population](docs/configuration.md#bots-and-population).
- **Client:** WoW 3.3.5a, build 12340, in any locale, including for Vanilla and
  TBC progression. German clients receive German talent and spell text.

## Downloads

The [Latest release](https://github.com/Syntax555/mod-playerbots-portable/releases/latest)
contains the server and the matching EraTalents client pack. The optional
addons are published by their forks, each as a rolling Latest release of the
branch the server pins; see [addon forks](docs/addons.md#addon-forks).

| Package | Use |
| --- | --- |
| [Server bundle](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/mod-playerbots-portable-latest.zip) | Portable server, launcher, MySQL and configuration templates. |
| [EraTalents client pack](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/EraTalents-client-latest.zip) | **Required for every player:** historical talents, Individual Progression's Vanilla/TBC spell data, restored class-quest spells and German text. |
| [MultiBot Chatless](https://github.com/Syntax555/MultiBot-Chatless/releases/latest/download/MultiBot-Chatless-latest.zip) | Optional interface for your bot companions. Install its `MultiBot` folder as `Interface/AddOns/MultiBot/`; see [client addons](docs/addons.md). |
| [DragonUI](https://github.com/Syntax555/DragonUI/releases/latest/download/DragonUI-latest.zip) | Optional interface. Install its `DragonUI` and `DragonUI_Options` folders in `Interface/AddOns/`; EraTalents adapts it to each character's era. |
| [Questie-335 installer](https://github.com/Syntax555/Questie/releases/latest/download/Questie-335-latest.zip) | Optional quest addon with bot progress integration. Extract and run `Install-Questie.cmd` with Internet access; see [installation](docs/questie-playerbots.md#installation). |
| [Zygor IP installer](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest/download/Zygor-IP-latest.zip) | Optional Zygor Guides Viewer that follows each character's Individual Progression tier. Extract and run `Install-Zygor.cmd` with Internet access; see [installation](docs/zygor-progression.md#installation). |
| [SHA-256 checksums](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt) | Verify the packages and update manifest. |

## Running the server

`startup.exe` runs MySQL, authserver and worldserver in one console and restarts
any of them that exits, including after the console's `server shutdown`
command. Press **Ctrl+C** in that console to stop the realm.

Each start checks Latest; for a newer release the launcher downloads the
changed server files, verifies them and restarts with them. SQL migrations and
new configuration defaults apply automatically; characters, databases, server
data, custom settings and the realm mode are preserved. Client packages are
installed manually: update the EraTalents client pack with the server, and the
optional addons from their forks' Latest releases. See the
[update guide](docs/updating.md) for manual installation, backups and recovery.

Configurations, databases, logs and server data live in `configs/`,
`mysql/data/`, `logs/` and `data/` of the server folder. A server folder that
is not writable moves them to `%LOCALAPPDATA%\Playerbots` and turns off
automatic updates; see [where your data lives](docs/updating.md#where-your-data-lives).

| Option | Effect |
| --- | --- |
| `--no-update` | Start without checking for a server update. |
| `--show-expansion`, `--set-expansion <mode>` | Show or select the realm mode; see [realm ceilings](docs/changing-expansions.md#optional-realm-ceilings). |
| `--help` | List all options; see [launcher options](docs/updating.md#launcher-options). |

## Configuration

Edit the active files in `configs/` and `configs/modules/` with the realm
stopped. Updates keep custom values; see the
[configuration reference](docs/configuration.md).

| To change | See |
| --- | --- |
| Bot population and player presence | [Bots and population](docs/configuration.md#bots-and-population) |
| Realm mode and expansion ceilings | [Optional realm ceilings](docs/changing-expansions.md#optional-realm-ceilings) |
| Resident level caps and battleground filling | [Bot brackets and PvP](docs/earned-bot-brackets.md) |
| Auction trading | [Auction economy](docs/earned-auctions.md#configuration) |
| Autonomous dungeons and raid tactics | [Bot dungeons and raids](docs/bot-dungeons.md#configuration) |
| Optional world buff simulation | [World buffs](docs/world-buffs.md#configuration) |
| Outdoor world event timers | [Era world events](docs/world-events.md#configuration) |

## Troubleshooting

**Windows blocks `startup.exe`.** The executables are unsigned, so SmartScreen
or Smart App Control can block them. Verify the ZIP against
[SHA256SUMS.txt](https://github.com/Syntax555/mod-playerbots-portable/releases/latest/download/SHA256SUMS.txt).

**`Update check unavailable; starting installed release`.** The launcher could
not reach or verify Latest and starts the installed release. `--no-update`
skips the check; see [failed updates](docs/updating.md#offline-startup-and-failed-updates).

**A port is already in use.** MySQL uses port 3306, authserver 3724 and
worldserver 8085. Stop the other server, or give a new realm another MySQL port
with `--port`; see [launcher options](docs/updating.md#launcher-options).

**No bots are online.** Bots log in gradually from 30 seconds after a real
player connects and log out 60 seconds after the last player leaves; see
[bots and population](docs/configuration.md#bots-and-population).

**The talent window shows Wrath trees or a stale generation.** Characters below
tier 13 need the matching client pack, installed with WoW fully closed. Check it
with `/run print(GetSpellInfo(932999))`; see
[client installation](docs/era-talents.md#install-the-matching-client-files).

**A historical quest is missing or unavailable.** Inspect the affected character
with the core's `.quest status`; see [quest diagnostics](docs/quest-diagnostics.md)
for permissions, prerequisite checks and Individual Progression limits.

**An addon blocked an action.** See
[blocked interactions and Lua errors](docs/addons.md#blocked-interactions-and-lua-errors).

**Playing from another computer.** The servers listen only on `127.0.0.1`, so
only the server PC can connect. The distribution provides no network setup.

**Administrator commands.** Commands such as `.reload config` need a GM account:
run `account set gmlevel <username> 3 -1` in the worldserver console. Play with
an ordinary account; GM accounts are meant for administration.

**Starting a fresh realm.** See
[realm updates](docs/changing-expansions.md#updating-an-existing-realm).

**Reporting a problem.** Copy `logs/` before the next start, because every
server start, including an automatic restart, overwrites `Server.log`,
`Errors.log`, `Playerbots.log` and `Auth.log`. Include the `revision` from
`portable-release.json`; see [contributing](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md).

## Status and limitations

The release workflow runs launcher tests, source fixtures for the earned-play
rules and package verification before publishing. These checks do not establish
complete in-game coverage: full dungeon and raid runs, every class quest, the
2,500-bot target and parts of the DragonUI, Questie and Zygor integrations have
not been verified in game; see the [roadmap](docs/todo.md#gameplay-validation).

The server uses the Wrath core and client. Historical trees use Vanilla 1.12.1
and TBC Classic 2.5.4 data; TBC is not an exact original 2.4.3 simulation.
Selected class spells, riding prices, battleground and experience rules follow
the earned era, while other prices, combat formulas and systems keep core
behavior. Bot questing, navigation and encounter support vary by content, and
some upstream encounter actions use movement or combat shortcuts. Existing
inventories and gold are preserved without verifying their origin. See
[supported scope](docs/configuration.md#supported-scope) and the
[roadmap](docs/todo.md).

## Included modules

These upstream projects provide the underlying systems. Their roles below
include this distribution's local integration and defaults; see
[server adaptations](docs/adaptations.md) and the pinned
[source versions](docs/module-versions.md).

| Module | Default role |
| --- | --- |
| [Playerbots](https://github.com/buildthehomelab/wow-mod-playerbots) | Bot companions, natural progression, earned auction trading and integrated Raid Clear tactics. |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | Character-specific content milestones and expansion unlocks. |
| [Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents) | Earned-era talents and selected class spell variants for players and bots. |
| [Quest Loot Party](https://github.com/pangolp/mod-quest-loot-party) | Shared normal-quality quest-item loot for eligible party members. |
| [World Buff Bots](https://github.com/Rockhopper1776/mod-world-buff-bots) | Optional timed Vanilla buffs; disabled by default in favor of native quest events. |
| [Era Events](https://github.com/buildthehomelab/wow-mod-era-events) | Outdoor AQ, Scourge, Legion and zombie encounters at each character's exact earned tier, with ordinary kill loot. |
| [LFG Progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) | Always included earned-era access guards for the [optional Dungeon Finder](docs/bot-dungeons.md#optional-dungeon-finder), which is disabled by default. |
| [MultiBot Bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | Server support for the MultiBot Chatless interface. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | Autonomous earned-era dungeon parties and player-led clears, with real travel, combat and loot. |

Bot commands are documented in the
[Playerbots wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands).
Commands that grant items, gear, pets, summons or mail are refused here; see
[server adaptations](docs/adaptations.md#playerbots-and-group-play).

## Documentation

| Guide | Topics |
| --- | --- |
| **Players** | |
| [Progression](docs/changing-expansions.md) | Content milestones, expansion modes and realm migration. |
| [EraTalents](docs/era-talents.md) | Client installation, training, talents and compatibility. |
| [Combat profiles](docs/combat-profiles.md) | Automatic or manual bot specializations, class support and owned equipment. |
| [Class quests](docs/class-quests.md) | Historical priest quest rewards, race gates and paid training. |
| [Client addons](docs/addons.md) | MultiBot, DragonUI, the addon forks, curated upstream addons and Lua diagnostics. |
| [Questie bot progress](docs/questie-playerbots.md) | Server-controlled group bot quest counters, installation and validation. |
| [Zygor Individual Progression](docs/zygor-progression.md) | Guides, Gear Finder and Talent Advisor by earned tier, installation and limits. |
| [Bot dungeons and raids](docs/bot-dungeons.md) | Autonomous parties, player-led clears, raid tactics and travel. |
| [Bot brackets and PvP](docs/earned-bot-brackets.md) | Resident levels, battleground eligibility and match rules. |
| [Auction economy](docs/earned-auctions.md) | Trading behavior, settings and market limits. |
| [World buffs](docs/world-buffs.md) | Native quest events, buff conditions and optional Vanilla simulation. |
| [Era world events](docs/world-events.md) | Outdoor encounters, earned tiers, timers and configuration. |
| **Server administration** | |
| [Quest diagnostics](docs/quest-diagnostics.md) | Read-only quest status, acceptance reasons and progression checks. |
| [Running and updating](docs/updating.md) | Updates, data location, launcher options, backups and recovery. |
| [Configuration](docs/configuration.md) | Default settings, module behavior and supported scope. |
| [Server adaptations](docs/adaptations.md) | Distribution-specific gameplay, client and launcher behavior. |
| **Reference** | |
| [Source versions](docs/module-versions.md) | Pinned dependencies, bundled runtime and provenance. |
| [Third-party notices](THIRD_PARTY_NOTICES.md) | Licenses and packaged notice paths. |
| **Development** | |
| [TODO and validation](docs/todo.md) | Open integration work, validation tasks and completion criteria. |
| [Building from source](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md) | Windows build, client package and local checks. |
| [Contributing](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md) | Problem reports, patch and fork workflow, documentation and releases. |

## Contributing

[Report a problem](https://github.com/Syntax555/mod-playerbots-portable/issues)
or propose a change; the
[contributing guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md)
lists what a report needs and how to change pinned sources. Addon changes are
made in the [addon forks](docs/addons.md#addon-forks).

Before committing, run targeted local checks for the changed files and their
affected callers, configuration and integrations. The complete test suite runs
separately in GitHub Actions on code pushes and before a manual build; it does
not need to be repeated locally. See the
[local check guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/building.md#integration-checks).

## License and credits

The portable project was originally created by **Onur Aslan** as
[onur/mod-playerbots-portable](https://github.com/onur/mod-playerbots-portable).
This continuation is maintained in `Syntax555/mod-playerbots-portable`;
original authorship and dependency credits remain part of the project.

The portable launcher and build tooling use the [MIT License](LICENSE).
AzerothCore, modules and addons retain their upstream licenses and notices; see
[third-party notices](THIRD_PARTY_NOTICES.md) for attribution, packaged license
paths and pinned source references.

Built with AzerothCore, Playerbots and the module authors linked above, the
[MultiBot Chatless](https://github.com/Wishmaster117/MultiBot-Chatless),
[DragonUI](https://github.com/NeticSoul/DragonUI),
[Questie-335](https://github.com/Aldori15/Questie) and
[Zygor Guides Viewer Remaster](https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK)
addons, [StormLib](https://github.com/ladislav-zezula/StormLib) and historical class
data from [CMaNGOS](https://github.com/cmangos). First-run server data is
provided by the [wowgaming client-data project](https://github.com/wowgaming/client-data),
and German client text by
[TrinityCore-3.3.5-data-multilang](https://github.com/Haeniken/TrinityCore-3.3.5-data-multilang).
