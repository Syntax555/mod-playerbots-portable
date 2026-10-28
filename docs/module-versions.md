# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) records immutable source revisions.
The release packages include this manifest and component source/license
notices. The core, all nine native server modules and the MultiBot, DragonUI,
Questie and Zygor addons are built from maintained forks: each pinned fork
commit contains its local changes. `upstream` records the original project and
the original revision imported last; `forkChanges` names the commits exercised
by regression fixtures. Exact source revisions form part of the adapted build's
identity.
See [server adaptations](adaptations.md) for the behavior of the local changes.

## Pinned sources

The core and native module forks use their configured default branches. The
manifest records each original upstream and its imported revision; the table
lists the exact commits integrated with the core, client addons and supporting
data.

| Component | Source repository | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [Syntax555/azerothcore-wotlk](https://github.com/Syntax555/azerothcore-wotlk), fork of [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) at `3f2969ddb0da` | `dc4d2647696c` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots with Raid Clear | [Syntax555/wow-mod-playerbots](https://github.com/Syntax555/wow-mod-playerbots), fork of [buildthehomelab/wow-mod-playerbots](https://github.com/buildthehomelab/wow-mod-playerbots) at `80f2afa04543` | `6be95a7feedc` | Natural progression, earned auctions, era-aware bots and integrated raid tactics |
| Individual Progression | [Syntax555/mod-individual-progression](https://github.com/Syntax555/mod-individual-progression), fork of [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) at `4933d455d2f6` | `2f10fb0ad85a` | Earned content milestones and expansion access |
| Dungeon Clear | [Syntax555/mod-dungeon-clear](https://github.com/Syntax555/mod-dungeon-clear), fork of [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) at `fcb680fb279c` | `bf490e9da7e0` | Autonomous earned-era parties and player-led clears without event shortcuts |
| Quest Loot Party | [Syntax555/mod-quest-loot-party](https://github.com/Syntax555/mod-quest-loot-party), fork of [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) at `c3955915c76d` | `25ee77143d2d` | Scoped party sharing of naturally dropped quest items |
| World Buff Bots | [Syntax555/mod-world-buff-bots](https://github.com/Syntax555/mod-world-buff-bots), fork of [Rockhopper1776/mod-world-buff-bots](https://github.com/Rockhopper1776/mod-world-buff-bots) at `baae5656aa6a` | `ce0984a28960` | Optional timed Vanilla events with earned-era checks; disabled by default |
| Era Events | [Syntax555/wow-mod-era-events](https://github.com/Syntax555/wow-mod-era-events), fork of [buildthehomelab/wow-mod-era-events](https://github.com/buildthehomelab/wow-mod-era-events) at `cf02786aceb5` | `cc5387687044` | Outdoor encounters at exact earned tiers without cross-era phasing or passive rewards |
| LFG Progression | [Syntax555/wow-mod-lfg-progression](https://github.com/Syntax555/wow-mod-lfg-progression), fork of [buildthehomelab/wow-mod-lfg-progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) at `2615e82902cf` | `7ed58ca9b0ac` | Always included access guards for optional Dungeon Finder use |
| MultiBot Bridge | [Syntax555/mod-multibot-bridge](https://github.com/Syntax555/mod-multibot-bridge), fork of [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) at `ebfa01a129dd` | `a718f3e3407d` | Server support for the MultiBot controls |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), fork of [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) at `80148dff3f3a` | `3b84ccc4d157` | Client bot controls and combat-profile selection |
| Questie-335 | [Syntax555/Questie, branch `335`](https://github.com/Syntax555/Questie/tree/335), fork of [Aldori15/Questie](https://github.com/Aldori15/Questie/tree/335) at `d695e9048e6d` | `98274deeeac1` | Bot quest progress integration; the fork's installer downloads its files from GitHub |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), fork of [ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK) at `9087c457e20f` | `de9461efb1b4` | Prepared Individual Progression integration of the `ZygorGuidesViewerRM/` addon folder |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), fork of [NeticSoul/DragonUI](https://github.com/NeticSoul/DragonUI) at `834bd108fba6` | `362b26d26aa4` | Shared talent renderer for historical player and bot trees, plus spellbook catalogue integration |
| Era Talents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), fork of [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) at `0dac15c4a71d` | `c0276a5342f2` | Historical server trees, authored random-bot builds and client addon |
| StormLib | [ladislav-zezula/StormLib](https://github.com/ladislav-zezula/StormLib) | `116135c27e8c` | Native MPQ generation and verification |
| CMaNGOS Classic DB | [cmangos/classic-db](https://github.com/cmangos/classic-db) | `ec4f596146be` | Historical class quest and trainer records and 1.12 quest levels |
| CMaNGOS TBC DB | [cmangos/tbc-db](https://github.com/cmangos/tbc-db) | `ebe51a83b0fd` | Historical TBC class quest and trainer records and 2.4.3 quest experience values |
| CMaNGOS Classic core | [cmangos/mangos-classic](https://github.com/cmangos/mangos-classic) | `8ec338a1704e` | Historical spell mechanics and coefficients |
| CMaNGOS TBC core | [cmangos/mangos-tbc](https://github.com/cmangos/mangos-tbc) | `a8ad244bcbce` | Historical TBC spell mechanics and coefficients, quest experience formula |
| German client text | [Haeniken/TrinityCore-3.3.5-data-multilang](https://github.com/Haeniken/TrinityCore-3.3.5-data-multilang) | `b21c94991a28` | German DBC text merged into the client MPQ |

## Bundled runtime

The server ZIP bundles these Windows x64 runtime dependencies. The
[release workflow](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/workflows/release.yml)
pins the MySQL and OpenSSL archives with their SHA-256 hashes.

| Runtime | Version | Location in the server ZIP |
| --- | --- | --- |
| MySQL Community Server | 8.0.46 | `mysql/` |
| OpenSSL | 3.5.9, FireDaemon build | `libcrypto-3-x64.dll`, `libssl-3-x64.dll` and the `legacy.dll` provider at the root |
| Boost | 1.92.0 | Linked statically into the servers |
| Microsoft Visual C++ runtime | From the build's Visual Studio 2022 | DLLs at the root and in `mysql/bin/` |

## Server data download

The packages do not contain the server's DBC, map, vmap and mmap files. On first
start the launcher downloads `Data.zip` (about 1.2 GB) from the
[wowgaming/client-data v20.0 release](https://github.com/wowgaming/client-data/releases/tag/v20.0)
and extracts it into `data/`. `--data-url` selects another copy of that archive;
see [launcher options](updating.md#launcher-options).

## Source preparation

CMake fetches the locked core, module and addon commits into `.module-cache/`,
prepares a separate core copy and exports the pinned module/addon commits.
Preparation and packaging checks use exact fork revisions and verify addon
files against the prepared source.

The Playerbots fork includes Raid Clear in `src/Ai/Raid/RaidClear`; it is built
as part of `mod-playerbots`, without a separate Raid Clear module. Its
`RaidClear.*` settings share `configs/modules/playerbots.conf` and its MIT
license is preserved alongside the Playerbots notices.

LFG Progression follows the same preparation, build and packaging path as every
other module; there is no separate build option. A variant without it would
still require maintaining its fork pin and tests for supported Finder use,
plus module-selection and upgrade handling. Existing installations may have
enabled the Finder, and updates preserve their personal `.conf` files. Omitting
the module would leave those queues without their earned-era guards. Keeping
one package preserves those checks with less maintenance; see
[Finder configuration](bot-dungeons.md#optional-dungeon-finder).

The Playerbots pin contains `5dc162f3` (safe item lifetimes), `45112ef7`
(queued chat commands resolve their sender when they run), `c583bc22`
(addon messages do not command bots) and `c9398d16` (RPG quest-giver search
skips despawned quest givers). The regression fixture checks all four fixes
against the prepared sources.

Surplus Soul Shard disposal consumes one shard through the core's item-count
handler and preserves the remainder of a stack. The regression fixture checks
backpack and bag stacks while leaving other items and bank contents untouched.

Core and Playerbots use the matching asynchronous module-database API. The
core's auth migration converts existing numeric account locales to language
codes; accounts and characters are retained. Registered locales are shared
with Playerbots. Hunter traps use the corrected native targeting and spell
finish handling, and battleground reputation follows the native bracket rules.

Playerbots includes controlled-bot queue exclusions, arena bracket and queue
locking fixes and revised TBC encounter tactics. Natural progression retains
ordinary movement and refuses encounter position-rescue teleports. The
MultiBot Bridge resolves strategy aliases to their native canonical names
before applying and verifying role commands.

Individual Progression offers the Scarab Gong's next quest only through its
personal Scepter and native quest-acceptance checks. Raid Clear prioritizes
mutated scarabs and scorpions during the Twin Emperors encounter. LFG
Progression supplies read-only queue diagnostics using every group member's
own earned era; it does not unlock content.

Dungeon Clear includes route, encounter-loot and recovery improvements. Its
new BRD and Upper Blackrock Spire event controllers remain subject to the
earned-action audit; unaudited controllers do not enable autonomous routes.
Rocknot's ale event requires the bot's own mugs and native quest eligibility,
without the upstream unpaid reward fallback.

The Playerbots fork includes the natural-progression, earned-auctions,
earned-bags and era-talents changes as commits. Natural progression uses the
upstream ammunition checks and preserves queue-assigned battleground brackets.
The era bridge resolves historical Tree of Life spells when deciding whether
a healer should keep blanketing instead of attacking. The MultiBot fork's role
change uses the canonical class strategy names for commands and status display: Warrior
`prot`, Priest `disc`, and Paladin `holy`, `ret` and `prot`.

The client packager uses IP's locked base archive, merges generated spell and
skill rows and German text, and preserves other entries byte for byte.
`SOURCE_MANIFEST.json` records sources, artifact hashes and the
server/client generation. See [client setup](era-talents.md#install-the-matching-client-files).

The addons are not part of the server's packages. Each fork publishes its
own rolling Latest release from the branch the server pins, so an addon can be
tried without a server build; the server's fixtures check the pinned commit:

| Fork | Latest asset | Contents |
| --- | --- | --- |
| [MultiBot Chatless](https://github.com/Syntax555/MultiBot-Chatless/releases/latest) | `MultiBot-Chatless-latest.zip` | The addon at `MultiBot/MultiBot.toc` with `SOURCE_REVISION.txt` |
| [DragonUI](https://github.com/Syntax555/DragonUI/releases/latest) | `DragonUI-latest.zip` | `DragonUI/` and `DragonUI_Options/` with `SOURCE_REVISION.txt` |
| [Era Talents](https://github.com/Syntax555/azerothcore-mod-era-talents/releases/latest) | `EraTalents-addon-latest.zip` | The client addon only, for quick tests; players install the server's `EraTalents-client-latest.zip` with the matching MPQ |
| [Questie](https://github.com/Syntax555/Questie/releases/latest) | `Questie-335-latest.zip` | An installer with the file list of its commit, not the addon |
| [Zygor](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK/releases/latest) | `Zygor-IP-latest.zip` | An installer with the file list of its commit, not the addon |

The Questie and Zygor installers download GitHub's source archive of the commit
they were built from and install `Questie-335/` or `ZygorGuidesViewerRM/` only
when every file matches the SHA-256 hash of that commit's Git tree; see
[Questie installation](questie-playerbots.md#installation) and
[Zygor installation](zygor-progression.md#installation). The MultiBot Bridge
reads the bots' native quest state and supplies the existing Questie
communication path. No additional quest bridge module is required.

Preparation exports the pinned addons into `.module-cache/prepared-addons/` and
`.module-cache/prepared-source-addons/` for the fixtures. Zygor's entry names
the repository's `ZygorGuidesViewerRM/` folder and DragonUI's its `DragonUI/`
folder; the TOCs are checked without regard to case, as the client loads them.
`forkChanges` names the fork commit of each fixture-covered change: the
fixtures revert and reapply its diff, so they fail when a pinned commit loses
the change.

Dependencies keep their own license terms and per-file notices; see
[third-party notices](../THIRD_PARTY_NOTICES.md) and each package's `licenses/`
directory.

## Updating dependencies

Changes to pins require checking core/module APIs, SQL migration behavior,
server/client generation agreement and earned-play guards.
Local adaptations use native module behavior where it is available, retaining
only earned-progression guards and verified gaps. Remove superseded fork code
after checking its native replacement.
The build workflow checks progression fixtures, launcher behavior and package
integrity before producing the Windows server and matched client packages.
These checks do not certify every encounter tactic or live realm performance;
see the [configuration reference](configuration.md#supported-scope).

Make source changes on each fork's configured default branch, listed in the
contributor guide.
For each update, compare the original project's history from the manifest's
`upstream.revision`, merge the chosen original commit into the maintained fork
and pin the tested fork commit as `revision`. Record the imported original
commit as `upstream.revision`, preserve the original `upstream.url` and keep
fixture-covered commits reachable under `forkChanges`. Native fork CI runs
selected server fixtures against its proposed commit; the complete native
build and integration use this server's pinned core and all modules. Forks
preserve original authorship, Git history and source licenses. See
[the contributor workflow](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md#changing-the-server).

MultiBot Chatless and MultiBot Bridge are checked as a compatible pair. New
bridge endpoints, such as pet creation, glyph application and maintenance,
must preserve natural progression. Module and addon updates retain manual
talent choices, personal configuration, characters and databases.

The pinned Playerbots sources read `Playerbots.*` configuration names.
Profiles and launcher settings use that prefix. Normal startup migrates legacy
`AiPlayerbot.*` values and their managed baselines before merging profile
updates; existing `Playerbots.*` values take precedence. See
[configuration updates](configuration.md) for migration and backup behavior.
`cmake/tests/TestProfileKeys.py` checks that the prepared sources read every
shipped key and rejects renamed readers and removed keys.
