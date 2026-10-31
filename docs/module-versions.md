# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) is the authoritative source list.
`revision` pins an exact fork commit; `upstream` records the original project
and the revision last imported. `forkChanges` identifies retained behavior
commits exercised by production-source fixtures. Documentation changes can
advance a fork pin without changing its runtime code.

Use [server adaptations](adaptations.md) for behavior and
[configuration](configuration.md) for shipped defaults. Native module templates
can have different defaults from this distribution's managed profile.

## Pinned sources

The core, nine native modules and four separate addon projects use maintained
Syntax555 forks on their configured default branches. The
[contributor guide](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md#changing-the-server)
lists those branches. Builds use the immutable commits below, rather than
whatever a branch happens to contain later.

### Server modules

All nine modules build with the matching core. Being included does not mean
every optional feature is enabled: the Dungeon Finder and simulated world-buff
turn-ins are disabled in the shipped profile.

| Component | Source repository and imported upstream | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [Syntax555/azerothcore-wotlk](https://github.com/Syntax555/azerothcore-wotlk), fork of [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) at `93333d6a9eb0` | `c885c9b1d8fd` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots with Raid Clear | [Syntax555/wow-mod-playerbots](https://github.com/Syntax555/wow-mod-playerbots), fork of [buildthehomelab/wow-mod-playerbots](https://github.com/buildthehomelab/wow-mod-playerbots) at `5283a13e0a5d` | `0cbd35458282` | Natural progression, earned auctions, era-aware bots and integrated raid tactics |
| Individual Progression | [Syntax555/mod-individual-progression](https://github.com/Syntax555/mod-individual-progression), fork of [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) at `4933d455d2f6` | `b58a459a289f` | Earned content milestones and expansion access |
| Era Talents | [Syntax555/azerothcore-mod-era-talents](https://github.com/Syntax555/azerothcore-mod-era-talents), fork of [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) at `0dac15c4a71d` | `98127f118256` | Historical server trees, authored random-bot builds and client addon |
| Dungeon Clear | [Syntax555/mod-dungeon-clear](https://github.com/Syntax555/mod-dungeon-clear), fork of [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) at `7fb6ebdefb80` | `340e5eb1416a` | Autonomous earned-era parties and player-led clears without event shortcuts |
| MultiBot Bridge | [Syntax555/mod-multibot-bridge](https://github.com/Syntax555/mod-multibot-bridge), fork of [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) at `9f0e8ba767c6` | `6147c7856b9e` | Server support for the MultiBot controls |
| Quest Loot Party | [Syntax555/mod-quest-loot-party](https://github.com/Syntax555/mod-quest-loot-party), fork of [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) at `c3955915c76d` | `b558cd259a95` | Scoped party sharing of naturally dropped quest items |
| LFG Progression | [Syntax555/wow-mod-lfg-progression](https://github.com/Syntax555/wow-mod-lfg-progression), fork of [buildthehomelab/wow-mod-lfg-progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) at `2615e82902cf` | `451486aaeff9` | Always included access guards for optional Dungeon Finder use |
| Era Events | [Syntax555/wow-mod-era-events](https://github.com/Syntax555/wow-mod-era-events), fork of [buildthehomelab/wow-mod-era-events](https://github.com/buildthehomelab/wow-mod-era-events) at `cf02786aceb5` | `910af62c3a47` | Outdoor encounters at exact earned tiers without cross-era phasing or passive rewards |
| World Buff Bots | [Syntax555/mod-world-buff-bots](https://github.com/Syntax555/mod-world-buff-bots), fork of [Rockhopper1776/mod-world-buff-bots](https://github.com/Rockhopper1776/mod-world-buff-bots) at `baae5656aa6a` | `6fe255ec8504` | Optional timed Vanilla events with earned-era checks; disabled by default |

### Client addons

EraTalents comes from the module pin above and is included in the server's
matching historical client pack. The following optional addons have separate
fork releases; see [downloads and installation](addons.md#addon-forks).

| Component | Source repository and imported upstream | Locked revision | Role |
| --- | --- | --- | --- |
| MultiBot Chatless | [Syntax555/MultiBot-Chatless](https://github.com/Syntax555/MultiBot-Chatless), fork of [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) at `020210ba849c` | `f7b7a596c376` | Client bot controls and combat-profile selection |
| DragonUI | [Syntax555/DragonUI](https://github.com/Syntax555/DragonUI), fork of [NeticSoul/DragonUI](https://github.com/NeticSoul/DragonUI) at `34bc67d4ca86` | `522f20ce390a` | Shared talent renderer for historical player and bot trees, plus spellbook catalogue integration |
| Questie-335 | [Syntax555/Questie, branch `335`](https://github.com/Syntax555/Questie/tree/335), fork of [Aldori15/Questie](https://github.com/Aldori15/Questie/tree/335) at `908a40b38bd6` | `14423b36cccb` | Bot quest progress integration; the fork's installer downloads its files from GitHub |
| Zygor Guides Viewer Remaster | [Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/Syntax555/ZygorGuidesRemaster-3.3.5a_WOTLK), fork of [ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK) at `d2aae8d0f1f3` | `70c7a44db664` | Prepared Individual Progression integration of the `ZygorGuidesViewerRM/` addon folder |

### Supporting data and tools

| Component | Source repository and imported upstream | Locked revision | Role |
| --- | --- | --- | --- |
| StormLib | [ladislav-zezula/StormLib](https://github.com/ladislav-zezula/StormLib) | `116135c27e8c` | Native MPQ generation and verification |
| CMaNGOS Classic DB | [cmangos/classic-db](https://github.com/cmangos/classic-db) | `ec4f596146be` | Historical class quest and trainer records and 1.12 quest levels |
| CMaNGOS TBC DB | [cmangos/tbc-db](https://github.com/cmangos/tbc-db) | `ebe51a83b0fd` | Historical TBC class quest and trainer records and 2.4.3 quest experience values |
| CMaNGOS Classic core | [cmangos/mangos-classic](https://github.com/cmangos/mangos-classic) | `8ec338a1704e` | Historical spell mechanics and coefficients |
| CMaNGOS TBC core | [cmangos/mangos-tbc](https://github.com/cmangos/mangos-tbc) | `a8ad244bcbce` | Historical TBC spell mechanics and coefficients, quest experience formula |
| German client text | [Haeniken/TrinityCore-3.3.5-data-multilang](https://github.com/Haeniken/TrinityCore-3.3.5-data-multilang) | `b21c94991a28` | German DBC text merged into the client MPQ |

## Bundled runtime

The server ZIP includes these Windows x64 dependencies. The
[release workflow](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/workflows/release.yml)
pins MySQL and OpenSSL archives by version and SHA-256.

| Runtime | Version | Location in the server ZIP |
| --- | --- | --- |
| MySQL Community Server | 8.0.46 | `mysql/` |
| OpenSSL | 3.5.9, FireDaemon build | `libcrypto-3-x64.dll`, `libssl-3-x64.dll` and the `legacy.dll` provider at the root |
| Boost | 1.92.0 | Linked statically into the servers |
| Microsoft Visual C++ runtime | From the build's Visual Studio 2022 | DLLs at the root and in `mysql/bin/` |

## Server data download

The packages omit server DBC, map, vmap and mmap files. First startup downloads
`Data.zip` (about 1.2 GB) from
[wowgaming/client-data v20.0](https://github.com/wowgaming/client-data/releases/tag/v20.0)
and extracts it into `data/`. `--data-url` can select another archive; see
[launcher options](updating.md#launcher-options).

## Source preparation

`cmake -P cmake/PrepareModules.cmake` fetches the locked commits into
`.module-cache/`, creates a separate prepared core and exports module/addon
sources. Native adaptations live in the forks; preparation rejects a source
patch list in the lock.

Raid Clear is part of Playerbots at `src/Ai/Raid/RaidClear`, with its MIT
notice retained. Its `RaidClear.*` settings share
`configs/modules/playerbots.conf`. LFG Progression is always compiled so
existing installations that enable the Finder keep per-member earned-era
checks; the Finder itself remains optional.

Prepared client sources live in `.module-cache/prepared-addons/` and
`.module-cache/prepared-source-addons/`. DragonUI exports its `DragonUI/`
subdirectory and Zygor its `ZygorGuidesViewerRM/` subdirectory. Addon checks
verify the client Interface and TOC paths against those exports.

The historical client pack merges generated spell/skill data and German text
into Individual Progression's locked base archive, preserving other entries.
`SOURCE_MANIFEST.json` records sources, artifact hashes and the matching
server/client generation; see [client setup](era-talents.md#install-the-matching-client-files).

## Addon releases

The server's `EraTalents-client-latest.zip` contains both the addon and its
matching MPQ. The EraTalents fork also publishes an addon-only ZIP for testing;
it does not replace the required client pack.

MultiBot, DragonUI, Questie and Zygor publish their own rolling Latest releases.
Those releases track their fork branches independently; the server manifest
records the revisions checked in the combined build. Package revision files or
installer metadata identify the installed addon source.

Questie and Zygor releases contain installers that download their exact source
commit from GitHub and verify each file. They are not addon-folder ZIPs.
See [addon installation](addons.md),
[Questie](questie-playerbots.md#installation) and
[Zygor](zygor-progression.md#installation).

## Updating dependencies

1. Compare the original project's history with `upstream.revision` and merge
   the chosen upstream commit on the fork's configured default branch.
2. Check API/configuration changes, SQL ordering and earned-play gates. Remove
   local code only when its native replacement passes the affected fixtures.
3. Pin the validated fork commit as `revision` and record the imported original
   commit under `upstream`. Keep fixture-covered `forkChanges` commits reachable;
   never rewrite pinned history.
4. Prepare the sources and run targeted checks for changed code and affected
   integrations. CI runs the complete checks and verifies manual release builds.
   Documentation-only pins require documentation checks and confirmation that
   runtime sources are unchanged.

MultiBot and its Bridge remain a compatible pair. Data changes require matching
EraTalents client files. Updates preserve manual talent choices, personal
configuration, characters and databases. See the
[fork workflow](https://github.com/Syntax555/mod-playerbots-portable/blob/main/CONTRIBUTING.md#changing-the-server).

Playerbots uses the `Playerbots.*` configuration prefix. The launcher migrates
legacy `AiPlayerbot.*` settings before merging managed defaults, with existing
`Playerbots.*` values taking precedence. Profile-key fixtures check that every
shipped key still has a native reader; see [configuration updates](configuration.md).

Dependency licenses and per-file notices remain in effect. See
[third-party notices](../THIRD_PARTY_NOTICES.md) and the package's `licenses/` directory.
