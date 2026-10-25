# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) records immutable source revisions
and ordered local patches. The release packages include this manifest and
component source/license notices. An upstream commit alone does not identify
the adapted build; local patch hashes are also part of its identity.
See [server adaptations](adaptations.md) for the behavior of the local changes.

| Component | Upstream repository | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) | `3f2969ddb0da` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots | [mod-playerbots/mod-playerbots](https://github.com/mod-playerbots/mod-playerbots) | `e88cc4099e69` | Natural progression, earned auctions and era-aware bots |
| Individual Progression | [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | `4933d455d2f6` | Earned content milestones and expansion access |
| Dungeon Clear | [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) | `fcb680fb279c` | Autonomous earned-era parties and player-led clears without event shortcuts |
| Raid Clear | [buildthehomelab/wow-mod-raid-clear](https://github.com/buildthehomelab/wow-mod-raid-clear) | `c9dbb3471e9b` | Boss and trash mechanics for Onyxia's Lair, Molten Core, Blackwing Lair, Zul'Gurub and Ahn'Qiraj |
| Quest Loot Party | [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) | `c3955915c76d` | Scoped party sharing of naturally dropped quest items |
| World Buff Bots | [Rockhopper1776/mod-world-buff-bots](https://github.com/Rockhopper1776/mod-world-buff-bots) | `baae5656aa6a` | Timed Vanilla events with individual earned-era and native recipient checks |
| Era Events | [buildthehomelab/wow-mod-era-events](https://github.com/buildthehomelab/wow-mod-era-events) | `cf02786aceb5` | Outdoor encounters at exact earned tiers without cross-era phasing or passive rewards |
| LFG Progression | [buildthehomelab/wow-mod-lfg-progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) | `2615e82902cf` | Always included access guards for optional Dungeon Finder use |
| MultiBot Bridge | [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | `ebfa01a129dd` | Server support for the MultiBot controls |
| MultiBot Chatless | [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) | `80148dff3f3a` | Client bot-control addon |
| Questie-335 (source only) | [Aldori15/Questie, branch `335`](https://github.com/Aldori15/Questie/tree/335) | `d695e9048e6d` | Prepared bot quest progress integration; installer downloads upstream files separately |
| Zygor Guides Viewer Remaster (source only) | [ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK](https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK) | `9087c457e20f` | Prepared Individual Progression integration of the `ZygorGuidesViewerRM/` addon folder |
| DragonUI (source only) | [NeticSoul/DragonUI](https://github.com/NeticSoul/DragonUI) | `82a6c52c93ad` | Talent window entry points and spellbook catalogue checked against the EraTalents integration; not redistributed |
| Era Talents | [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) | `0dac15c4a71d` | Historical server trees and client addon |
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
blanketing instead of attacking. The MultiBot role patch uses the canonical
class strategy names for commands and status display: Warrior `prot`, Priest
`disc`, and Paladin `holy`, `ret` and `prot`.

The client packager uses IP's locked base archive, merges generated spell and
skill rows and German text, and preserves other entries byte for byte.
`SOURCE_MANIFEST.json` records sources, patches, artifact hashes and the
server/client generation. See [client setup](era-talents.md#install-the-matching-client-files).

The MultiBot Chatless addon ZIP contains the prepared addon at
`MultiBot/MultiBot.toc`; the server package contains no client addons. Its
`SOURCE_MANIFEST.json` records the upstream revision and local patch hashes.
See [client integration](adaptations.md#client-integration) and
[client addons](addons.md) for its behavior.

The `sourceAddons` manifest section pins Questie separately from redistributed
client addons. Preparation applies its ordered patch into
`.module-cache/prepared-source-addons/Questie-335`. The separate
`Questie-335-latest.zip` contains an installer and integration metadata, not
the upstream addon. The installer downloads the pinned archive directly from
upstream, verifies it and applies the patch locally; see
[installation](questie-playerbots.md#installation). The MultiBot
Bridge reads the bots' native quest state and supplies the existing Questie
communication path. No additional quest bridge module is required.

Zygor Guides Viewer Remaster is pinned the same way. Its entry names the
repository's `ZygorGuidesViewerRM/` folder, which preparation exports into
`.module-cache/prepared-source-addons/ZygorGuidesViewerRM` with the
[Individual Progression patch](zygor-progression.md) applied. The addon's TOC
is checked without regard to case, as the client loads it. The separate
`Zygor-IP-latest.zip` contains an installer, the pinned file list and the patch
data, not the upstream addon. The installer downloads the pinned archive from
upstream, checks every addon file against the pinned Git tree and applies the
patch locally; see [installation](zygor-progression.md#installation).

DragonUI is pinned only so the fixtures run its talent window entry points
and spellbook catalogue with the EraTalents client files; no package contains it.

Dependencies keep their own license terms and per-file notices; see
[third-party notices](../THIRD_PARTY_NOTICES.md) and each package's `licenses/`
directory.

## Updating dependencies

Changes to pins require checking patch applicability, core/module APIs, SQL
migration behavior, server/client generation agreement and earned-play guards.
The build workflow checks progression fixtures, launcher behavior and package
integrity before producing the Windows server and matched client packages.
These checks do not certify every encounter tactic or live realm performance;
see the [configuration reference](configuration.md#supported-scope).

Pins follow the core fork's `Playerbot` branch, Playerbots `master` and the
`main` branch of MultiBot Chatless and MultiBot Bridge, not their GitHub
default feature branch; other components follow their default branch. MultiBot
Chatless and MultiBot Bridge are checked as a compatible pair. New bridge
endpoints, such as pet creation, glyph application and maintenance, must
preserve natural progression.

The Playerbots pin `e88cc409` reads `Playerbots.*` configuration names.
Profiles and launcher settings use that prefix. Normal startup migrates legacy
`AiPlayerbot.*` values and their managed baselines before merging profile
updates; existing `Playerbots.*` values take precedence. See
[configuration updates](configuration.md) for migration and backup behavior.
`cmake/tests/TestProfileKeys.py` checks that the prepared sources read every
shipped key and rejects renamed readers and removed keys.
