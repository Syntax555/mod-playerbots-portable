# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) records immutable source revisions
and ordered local patches. The release packages include this manifest and
component source/license notices. An upstream commit alone does not identify
the adapted build; local patch hashes are also part of its identity.
See [server adaptations](adaptations.md) for the behavior of the local changes.

| Component | Upstream repository | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) | `f19a18799a35` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots | [mod-playerbots/mod-playerbots](https://github.com/mod-playerbots/mod-playerbots) | `037c01418b5d` | Natural progression, earned auctions and era-aware bots |
| AutoBalance | [azerothcore/mod-autobalance](https://github.com/azerothcore/mod-autobalance) | `1d707cb61a09` | Instance scaling by actual party size |
| Individual Progression | [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | `60336b349cce` | Earned content milestones and expansion access |
| AH Bot Plus | [NathanHandley/mod-ah-bot-plus](https://github.com/NathanHandley/mod-ah-bot-plus) | `f685832994c8` | Optional synthetic market; disabled by default |
| Dungeon Clear | [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) | `60f3d98b8314` | Autonomous earned-era parties and player-led clears without event shortcuts |
| Raid Clear | [buildthehomelab/wow-mod-raid-clear](https://github.com/buildthehomelab/wow-mod-raid-clear) | `6bf9d66876b5` | Boss and trash mechanics for Molten Core, Blackwing Lair and Zul'Gurub |
| Quest Loot Party | [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) | `c3955915c76d` | Scoped party sharing of naturally dropped quest items |
| World Buff Bots | [Rockhopper1776/mod-world-buff-bots](https://github.com/Rockhopper1776/mod-world-buff-bots) | `baae5656aa6a` | Timed Vanilla events with individual earned-era and native recipient checks |
| LFG Progression | [buildthehomelab/wow-mod-lfg-progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) | `5d64585dd2ac` | Optional Dungeon Finder access by every participant's earned era |
| MultiBot Bridge | [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | `1da05982e478` | Server support for the MultiBot controls |
| Token Turn-in | [Zerathane/mod-token-turnin](https://github.com/Zerathane/mod-token-turnin) | `73e447c49975` | Token inspection; shortcut redemption blocked in natural mode |
| MultiBot Chatless | [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) | `80148dff3f3a` | Client bot-control addon |
| Era Talents | [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) | `0dac15c4a71d` | Historical server trees and client addon |
| StormLib | [ladislav-zezula/StormLib](https://github.com/ladislav-zezula/StormLib) | `86f9b99ffe4d` | Native MPQ generation and verification |
| CMaNGOS Classic DB | [cmangos/classic-db](https://github.com/cmangos/classic-db) | `ec4f596146be` | Historical class quest and trainer records |
| CMaNGOS TBC DB | [cmangos/tbc-db](https://github.com/cmangos/tbc-db) | `ebe51a83b0fd` | Historical TBC class quest and trainer records |
| CMaNGOS Classic core | [cmangos/mangos-classic](https://github.com/cmangos/mangos-classic) | `8ec338a1704e` | Historical spell mechanics and coefficients |
| CMaNGOS TBC core | [cmangos/mangos-tbc](https://github.com/cmangos/mangos-tbc) | `a8ad244bcbce` | Historical TBC spell mechanics and coefficients |

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
skill rows, and preserves other entries byte for byte. `SOURCE_MANIFEST.json`
records sources, patches, artifact hashes and the server/client generation.
Install `EraTalents-client-latest.zip` with the matching server. Both the addon
and MPQ are required and are installed manually with WoW closed; the server
updater does not modify client files. See [client setup](era-talents.md).

MultiBot Chatless installs as `Interface/AddOns/MultiBot/`, with `MultiBot.toc`.
The separate addon ZIP contains the prepared addon; the server package contains
no client addons. Local addon patches display gold, silver and copper and guard
options-panel initialization with its existing fallback interface. Its
`SOURCE_MANIFEST.json` records the upstream revision and those patch hashes.
With matching EraTalents loaded, the talent button uses native inspection and
the selected bot's server-authorized historical tree. Both addons must match
the release; the historical view permits inspection rather than talent writes.

In natural mode, Bridge trainer requests use the bot's current money for explicit
purchases and the core's trainer pricing and paid purchase path.

## Licenses

Dependencies retain their own license terms and per-file notices. The locked
AzerothCore and Playerbots repositories carry GPL-2.0 root license texts, with
GPL-2.0-or-later notices in common source headers. Individual Progression carries
an MIT root license and AGPL-3.0-or-later notices in many source files. Era
Talents carries an MIT license; portable integration files can carry their own
GPL notices. These components should not be described under one blanket license.

The historical class data uses pinned CMaNGOS sources. Database projects carry
GPL-3.0 texts; core projects carry GPL-2.0 texts with GPL-2.0-or-later source
notices. The server and combined client pack retain their provenance notice and
both license texts. Original game data retains its own terms.

The locked MultiBot Bridge revision has no explicit upstream license declaration.
Its packaged notice records provenance and this absence without granting a
license. See [third-party notices](../THIRD_PARTY_NOTICES.md) and each package's
`licenses/` directory for the applicable declarations.

## Updating dependencies

Changes to pins require checking patch applicability, core/module APIs, SQL
migration behavior, server/client generation agreement and earned-play guards.
The build workflow checks progression fixtures, launcher behavior and package
integrity before producing the Windows server and matched client packages.
These checks do not certify every encounter tactic or live realm performance;
see the [configuration reference](vanilla-config-audit.md#supported-scope).

Playerbots revisions from `ed54b459` rename every `AiPlayerbot.*` key to
`Playerbots.*` without reading the old names, so such a pin also needs renamed
profile and launcher keys and a launcher migration that carries users'
existing `AiPlayerbot.*` values. `cmake/tests/TestProfileKeys.py` fails while a
shipped profile key is no longer read by the prepared sources.
