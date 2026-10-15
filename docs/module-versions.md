# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) records immutable source revisions
and ordered local patches. The release packages include this manifest and
component source/license notices. An upstream commit alone does not identify
the adapted build; local patch hashes are also part of its identity.
See [server adaptations](adaptations.md) for the behavior of the local changes.

| Component | Upstream repository | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) | `2a2211cd8f3d` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots | [mod-playerbots/mod-playerbots](https://github.com/mod-playerbots/mod-playerbots) | `037c01418b5d` | Natural progression, earned auctions and era-aware bots |
| AutoBalance | [azerothcore/mod-autobalance](https://github.com/azerothcore/mod-autobalance) | `1d707cb61a09` | Instance scaling by actual party size |
| Individual Progression | [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | `60336b349cce` | Earned content milestones and expansion access |
| Dungeon Clear | [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) | `60f3d98b8314` | Autonomous earned-era parties and player-led clears without event shortcuts |
| Raid Clear | [buildthehomelab/wow-mod-raid-clear](https://github.com/buildthehomelab/wow-mod-raid-clear) | `6bf9d66876b5` | Boss and trash mechanics for Molten Core, Blackwing Lair and Zul'Gurub |
| Quest Loot Party | [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) | `c3955915c76d` | Scoped party sharing of naturally dropped quest items |
| World Buff Bots | [Rockhopper1776/mod-world-buff-bots](https://github.com/Rockhopper1776/mod-world-buff-bots) | `baae5656aa6a` | Timed Vanilla events with individual earned-era and native recipient checks |
| LFG Progression | [buildthehomelab/wow-mod-lfg-progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) | `5d64585dd2ac` | Optional Dungeon Finder access by every participant's earned era |
| MultiBot Bridge | [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | `1da05982e478` | Server support for the MultiBot controls |
| MultiBot Chatless | [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) | `80148dff3f3a` | Client bot-control addon |
| Era Talents | [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) | `0dac15c4a71d` | Historical server trees and client addon |
| StormLib | [ladislav-zezula/StormLib](https://github.com/ladislav-zezula/StormLib) | `6bb1882bd00d` | Native MPQ generation and verification |
| CMaNGOS Classic DB | [cmangos/classic-db](https://github.com/cmangos/classic-db) | `ec4f596146be` | Historical class quest and trainer records |
| CMaNGOS TBC DB | [cmangos/tbc-db](https://github.com/cmangos/tbc-db) | `ebe51a83b0fd` | Historical TBC class quest and trainer records |
| CMaNGOS Classic core | [cmangos/mangos-classic](https://github.com/cmangos/mangos-classic) | `8ec338a1704e` | Historical spell mechanics and coefficients |
| CMaNGOS TBC core | [cmangos/mangos-tbc](https://github.com/cmangos/mangos-tbc) | `a8ad244bcbce` | Historical TBC spell mechanics and coefficients |
| German client text | [Haeniken/TrinityCore-3.3.5-data-multilang](https://github.com/Haeniken/TrinityCore-3.3.5-data-multilang) | `b21c94991a28` | German DBC text merged into the client MPQ |

## Bundled runtime

The server ZIP bundles these Windows x64 runtime dependencies. The
[release workflow](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/workflows/release.yml)
pins each download with its SHA-256 hash.

| Runtime | Version | Location in the server ZIP |
| --- | --- | --- |
| MySQL Community Server | 8.0.40 | `mysql/` |
| OpenSSL | 3.5.7, FireDaemon build | `libcrypto-3-x64.dll`, `libssl-3-x64.dll` and the `legacy.dll` provider at the root |
| Boost | 1.84.0 | Linked statically into the servers |
| Microsoft Visual C++ runtime | From the build's Visual Studio 2022 | DLLs at the root and in `mysql/bin/` |

## Server data download

The packages do not contain the server's DBC, map, vmap and mmap files. On first
start the launcher downloads `Data.zip` (about 1.2 GB) from the
[wowgaming/client-data v20.0 release](https://github.com/wowgaming/client-data/releases/tag/v20.0)
and extracts it into `data/`. `--data-url` selects another copy of that archive;
see [launcher options](updating.md#launcher-options).

## Source preparation

Core and Playerbots submodules remain at their locked commits. CMake prepares a
separate core copy and module/addon exports, then applies patches in manifest
order. Preparation and packaging checks include patch hashes and verify addon
files against the prepared source.

`mod-playerbots-upstream-fixes.patch` carries upstream Playerbots commits
`5dc162f3` (no item reads after a destroy or stack merge can free the item),
`45112ef7` (queued chat commands resolve their sender when they run),
`c583bc22` (addon messages do not command bots) and `c9398d16` (RPG quest-giver
search skips despawned quest givers). The patch is dropped once the locked
Playerbots revision contains these commits.

The client packager uses IP's locked base archive, merges generated spell and
skill rows and German text, and preserves other entries byte for byte.
`SOURCE_MANIFEST.json` records sources, patches, artifact hashes and the
server/client generation. See [client setup](era-talents.md#install-the-matching-client-files).

The MultiBot Chatless addon ZIP contains the prepared addon at
`MultiBot/MultiBot.toc`; the server package contains no client addons. Its
`SOURCE_MANIFEST.json` records the upstream revision and local patch hashes.
See [client integration](adaptations.md#client-integration) and
[client addons](addons.md) for its behavior.

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
Chatless and MultiBot Bridge move only together, and a newer pair needs a
review of new bridge endpoints, such as pet taming, against natural progression.

Playerbots revisions from `ed54b459` rename every `AiPlayerbot.*` key to
`Playerbots.*` without reading the old names, so such a pin also needs renamed
profile and launcher keys and a launcher migration that carries users'
existing `AiPlayerbot.*` values. `cmake/tests/TestProfileKeys.py` fails while a
shipped profile key is no longer read by the prepared sources.
