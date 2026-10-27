# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) records immutable source revisions
and ordered local patches. The release packages include this manifest and
component source/license notices. An upstream commit alone does not identify
the adapted build; local patch hashes are also part of its identity. Era
Talents and the MultiBot, DragonUI, Questie and Zygor addons are built from
forks instead: their pinned fork commit contains the local changes, and
`upstream` records the original project and the revision the fork is based on.
See [server adaptations](adaptations.md) for the behavior of the local changes.

| Component | Source repository | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) | `3f2969ddb0da` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots with Raid Clear | [buildthehomelab/wow-mod-playerbots](https://github.com/buildthehomelab/wow-mod-playerbots) | `80f2afa04543` | Natural progression, earned auctions, era-aware bots and integrated raid tactics |
| Individual Progression | [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | `4933d455d2f6` | Earned content milestones and expansion access |
| Dungeon Clear | [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) | `fcb680fb279c` | Autonomous earned-era parties and player-led clears without event shortcuts |
| Quest Loot Party | [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) | `c3955915c76d` | Scoped party sharing of naturally dropped quest items |
| World Buff Bots | [Rockhopper1776/mod-world-buff-bots](https://github.com/Rockhopper1776/mod-world-buff-bots) | `baae5656aa6a` | Optional timed Vanilla events with earned-era checks; disabled by default |
| Era Events | [buildthehomelab/wow-mod-era-events](https://github.com/buildthehomelab/wow-mod-era-events) | `cf02786aceb5` | Outdoor encounters at exact earned tiers without cross-era phasing or passive rewards |
| LFG Progression | [buildthehomelab/wow-mod-lfg-progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) | `2615e82902cf` | Always included access guards for optional Dungeon Finder use |
| MultiBot Bridge | [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | `ebfa01a129dd` | Server support for the MultiBot controls |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), fork of [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) at `80148dff3f3a` | `7383260afe2f` | Client bot controls and combat-profile selection |
| Questie-335 | [Syntax555/Questie, branch `335`](https://github.com/Syntax555/Questie/tree/335), fork of [Aldori15/Questie](https://github.com/Aldori15/Questie/tree/335) at `d695e9048e6d` | `98274deeeac1` | Bot quest progress integration; the fork's installer downloads its files from GitHub |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), fork of [ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK) at `9087c457e20f` | `de9461efb1b4` | Prepared Individual Progression integration of the `ZygorGuidesViewerRM/` addon folder |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), fork of [NeticSoul/DragonUI](https://github.com/NeticSoul/DragonUI) at `cde60f02cffc4` | `00e15e78ad00` | Shared talent renderer for historical player and bot trees, plus spellbook catalogue integration |
| Era Talents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), fork of [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) at `0dac15c4a71d` | `5d4b03d46ebf` | Historical server trees, authored random-bot builds and client addon |
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
prepares a separate core copy and module/addon exports, then applies patches in
manifest order. Preparation and packaging checks include patch hashes and
verify addon files against the prepared source.

The Playerbots fork includes Raid Clear in `src/Ai/Raid/RaidClear`; it is built
as part of `mod-playerbots`, without a separate Raid Clear module. Its
`RaidClear.*` settings share `configs/modules/playerbots.conf` and its MIT
license is preserved alongside the Playerbots notices.

LFG Progression follows the same preparation, build and packaging path as every
other module; there is no separate build option. A variant without it would
still require maintaining its pin, patch and tests for supported Finder use,
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

The natural-progression, earned-auctions, earned-bags and era-talents patches
target this pin. Natural progression uses the upstream ammunition checks and
preserves queue-assigned battleground brackets. The era bridge resolves
historical Tree of Life spells when deciding whether a healer should keep
blanketing instead of attacking. The MultiBot fork's role change uses the
canonical class strategy names for commands and status display: Warrior
`prot`, Priest `disc`, and Paladin `holy`, `ret` and `prot`.

The client packager uses IP's locked base archive, merges generated spell and
skill rows and German text, and preserves other entries byte for byte.
`SOURCE_MANIFEST.json` records sources, patches, artifact hashes and the
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

Changes to pins require checking patch applicability, core/module APIs, SQL
migration behavior, server/client generation agreement and earned-play guards.
Local adaptations use native module behavior where it is available, retaining
only earned-progression guards and verified gaps. Remove replaced patch hunks
after pinning and checking their native replacements.
The build workflow checks progression fixtures, launcher behavior and package
integrity before producing the Windows server and matched client packages.
These checks do not certify every encounter tactic or live realm performance;
see the [configuration reference](configuration.md#supported-scope).

Pins follow the core fork's `Playerbot` branch, the Playerbots fork's `evermore`
branch and the `main` branch of MultiBot Bridge, not its GitHub default feature
branch. The Era Talents and addon forks follow `main`, Questie its `335`
branch, and other components their default branch. Upstream updates are merged
into a fork's branch and the merge commit is pinned. MultiBot Chatless and
MultiBot Bridge are checked as a compatible pair. New bridge
endpoints, such as pet creation, glyph application and maintenance, must
preserve natural progression.

The Playerbots pin `80f2afa0` reads `Playerbots.*` configuration names.
Profiles and launcher settings use that prefix. Normal startup migrates legacy
`AiPlayerbot.*` values and their managed baselines before merging profile
updates; existing `Playerbots.*` values take precedence. See
[configuration updates](configuration.md) for migration and backup behavior.
`cmake/tests/TestProfileKeys.py` checks that the prepared sources read every
shipped key and rejects renamed readers and removed keys.
