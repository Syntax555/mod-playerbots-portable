# Dependencies and build provenance

[versions.lock.json](../versions.lock.json) records immutable source revisions
and ordered local patches. The release packages include this manifest and
component source/license notices. An upstream commit alone does not identify
the adapted build; local patch hashes are also part of its identity.

| Component | Upstream repository | Locked revision | Role |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | [mod-playerbots/azerothcore-wotlk](https://github.com/mod-playerbots/azerothcore-wotlk) | `f19a18799a35` | Core server, historical spell/accounting hooks and earned-era PvP rules |
| Playerbots | [mod-playerbots/mod-playerbots](https://github.com/mod-playerbots/mod-playerbots) | `037c01418b5d` | Natural progression, earned auctions and era-aware bots |
| AutoBalance | [azerothcore/mod-autobalance](https://github.com/azerothcore/mod-autobalance) | `73d4ad3c379f` | Instance scaling by actual party size |
| Individual Progression | [ZhengPeiRu21/mod-individual-progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | `60336b349cce` | Earned content milestones and expansion access |
| AH Bot Plus | [NathanHandley/mod-ah-bot-plus](https://github.com/NathanHandley/mod-ah-bot-plus) | `f685832994c8` | Optional synthetic market; disabled by default |
| Dungeon Clear | [jrad7/mod-dungeon-clear](https://github.com/jrad7/mod-dungeon-clear) | `60f3d98b8314` | Optional scripted runs; disabled by default |
| Quest Loot Party | [pangolp/mod-quest-loot-party](https://github.com/pangolp/mod-quest-loot-party) | `6f073c1bef1b` | Scoped party sharing of naturally dropped quest items |
| MultiBot Bridge | [Wishmaster117/mod-multibot-bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | `1da05982e478` | Server support for the MultiBot controls |
| Token Turn-in | [Zerathane/mod-token-turnin](https://github.com/Zerathane/mod-token-turnin) | `73e447c49975` | Token inspection; shortcut redemption blocked in natural mode |
| MultiBot Chatless | [Wishmaster117/MultiBot-Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) | `80148dff3f3a` | Client bot-control addon |
| Era Talents | [lathcf/azerothcore-mod-era-talents](https://github.com/lathcf/azerothcore-mod-era-talents) | `0dac15c4a71d` | Historical server trees and client addon |
| StormLib | [ladislav-zezula/StormLib](https://github.com/ladislav-zezula/StormLib) | `86f9b99ffe4d` | Native MPQ generation and verification |

## Source preparation

Core and Playerbots submodules remain at their locked commits. CMake prepares a
separate core copy and module/addon exports, then applies patches in manifest
order. Preparation and packaging checks include patch hashes and verify addon
files against the prepared source.

The client packager uses IP's locked base archive, merges generated spell and
skill rows, and preserves other entries byte for byte. `SOURCE_MANIFEST.json`
records sources, patches, artifact hashes and the server/client generation.
Install `EraTalents-client-latest.zip` with the matching server; the server's
addon folder does not include the MPQ. See [client setup](era-talents.md).

MultiBot Chatless installs as `Interface/AddOns/MultiBot/`, with `MultiBot.toc`.
The separate addon ZIP and server package contain the same prepared addon.

## Licenses

Dependencies retain their own license terms and per-file notices. The locked
AzerothCore and Playerbots repositories carry GPL-2.0 root license texts, with
GPL-2.0-or-later notices in common source headers. Individual Progression carries
an MIT root license and AGPL-3.0-or-later notices in many source files. Era
Talents carries an MIT license; portable integration files can carry their own
GPL notices. These components should not be described under one blanket license.

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
