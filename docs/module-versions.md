# Module version review

The existing core, module and Chatless branch heads were checked on 5 October
2026. Historical talents and their native client build dependency were added
with immutable pins on 7 October 2026. Full revisions live in
`versions.lock.json`; ordered local compatibility and progression patches are
recorded alongside each affected component.

| Component | Repository / branch | Locked revision | Result |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | `mod-playerbots/azerothcore-wotlk`, `Playerbot` | `f19a18799a35` | Retained; local historical spell compatibility, paid respec accounting and earned-era riding-price hooks. |
| Playerbots | `mod-playerbots/mod-playerbots`, `master` | `037c01418b5d` | Retained; natural progression, earned auctions and historical bot talent/spell-resolution integration. |
| AutoBalance | `azerothcore/mod-autobalance`, default branch | `73d4ad3c379f` | Already current; retain actual-party scaling and no bonus tokens. |
| Individual Progression | `ZhengPeiRu21/mod-individual-progression`, default branch | `60336b349cce` | Retained; strict contiguous boss/quest milestones, nearby earned credit, new death knight creation block and earned riding prices. |
| AH Bot Plus | `NathanHandley/mod-ah-bot-plus`, default branch | `f685832994c8` | Already current; synthetic supply and automatic buying remain disabled. |
| Dungeon Clear | `jrad7/mod-dungeon-clear`, default branch | `60f3d98b8314` | Already current; retain compatibility patch and disabled shortcut routes. |
| Quest Loot Party | `pangolp/mod-quest-loot-party`, default branch | `6f073c1bef1b` | Already current; narrow naturally dropped quest-item sharing. |
| MultiBot Bridge | `Wishmaster117/mod-multibot-bridge`, `main` | `1da05982e478` | Retained with natural-progression restrictions and historical specialization support. |
| Token Turn-in | `Zerathane/mod-token-turnin`, default branch | `73e447c49975` | Added at current head; strict mode permits checks, blocks shortcut redemption. |
| MultiBot Chatless addon | `Wishmaster117/MultiBot-Chatless`, `main` | `80148dff3f3a` | Replaces `Macx-Lio/MultiBot`; paired with the bridge above. |
| Era Talents server module and addon | `lathcf/azerothcore-mod-era-talents` | `0dac15c4a71d` | Pinned and adapted for earned IP eras, incremental bot allocation, paid training/respecs and preserved glyph ownership. |
| StormLib client build dependency | `ladislav-zezula/StormLib` | `86f9b99ffe4d` | Pinned native tools merge and verify the historical client MPQ against IP's locked base archive. |

The maintained Playerbots core/module pair and original scoped module sources
remain appropriate for this realm. A newer fork is not inherently better for
Vanilla: generated auction stock, forced quest drops, broad personal equipment
loot and automatic token exchanges would change earned-play rules. This review
does not claim to benchmark every fork or establish complete raid/quest AI.

The Chatless project still uses the client folder/TOC name `MultiBot`. Each
portable release builds a separate `MultiBot-Chatless-<version>.zip` containing
that folder, its assets, upstream license and source revision, so players can
download and install it without the server ZIP.

Era Talents uses Vanilla 1.12.1 and TBC Classic 2.5.4 talent data. Its TBC talents
are not an exact original 2.4.3 dataset. The portable adaptation does not apply
the upstream manual-advance IP patch: earned boss credit and transition quests
remain authoritative for bots and humans. Routine bot respecs and free trainer
rank grants are removed, and broad character-spell cleanup SQL is neutralized.
The local patch also provides cached character talent/era state with ordered
persistence rather than synchronous database queries on routine map-thread polls.

Six core historical-effect patches, a native respec-accounting patch and a shared
earned riding-price hook are applied to a generated core copy. Module patches
are applied in manifest order to generated module exports. The original core and
Playerbots submodules remain at their pinned commits. Source preparation and
packaging stamps include each local patch's hash; an upstream revision alone
does not identify the final adapted server or addon.

Each matching build provides `EraTalents-client-<version>.zip` with the adapted
addon and a merged `Data/patch-V.mpq`. Packaging starts from the pinned IP client
archive, verifies the generated spell/skill rows and preserves its other client
patch entries byte for byte. The client ZIP records a generation marker, exact
source identities, local patch hashes and artifact hashes. The addon-only
`EraTalents-<version>.zip` does not contain the required MPQ. See
[client installation and migration](era-talents.md).

The bridge revision has no explicit upstream license declaration; its packaged
`licenses/mod-multibot-bridge/NOTICE.txt` records that fact and its provenance
without inventing a license. Other dependencies retain their upstream licenses
or existing source license notices.
Era Talents and StormLib retain their MIT licenses; patches modifying the
AzerothCore source remain under that source's AGPL license.

Validation and gameplay limitations are recorded in the addenda of
`vanilla-config-audit.md` and [earned-auctions.md](earned-auctions.md). The earned
auction patch adds trading to the same pinned Playerbots revision; AH Bot Plus
remains disabled. Historical integration validation includes production-policy
fixtures, actual pinned-core header/object compilation and independent client
packaging checks. Full Windows compilation and packaging are performed by CI;
source checks do not establish live raid AI, class balance or market behavior.
Future updates should re-check patch applicability, core/module API compatibility,
server/client generation agreement and shortcut behavior before changing these pins.
