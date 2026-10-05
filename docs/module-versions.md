# Module version review

Checked on 5 October 2026 using upstream Git branch heads. Full immutable
revisions live in `versions.lock.json`; local compatibility and progression
patches are recorded alongside each affected module.

| Component | Repository / branch | Locked revision | Result |
| --- | --- | --- | --- |
| AzerothCore Playerbots core | `mod-playerbots/azerothcore-wotlk`, `Playerbot` | `f19a18799a35` | Already current. |
| Playerbots | `mod-playerbots/mod-playerbots`, `master` | `037c01418b5d` | Already current; retain natural-progression patch. |
| AutoBalance | `azerothcore/mod-autobalance`, default branch | `73d4ad3c379f` | Already current; retain actual-party scaling and no bonus tokens. |
| Individual Progression | `ZhengPeiRu21/mod-individual-progression`, default branch | `60336b349cce` | Already current; retain Vanilla gates for bots and humans. |
| AH Bot Plus | `NathanHandley/mod-ah-bot-plus`, default branch | `f685832994c8` | Already current; synthetic supply and automatic buying remain disabled. |
| Dungeon Clear | `jrad7/mod-dungeon-clear`, default branch | `60f3d98b8314` | Already current; retain compatibility patch and disabled shortcut routes. |
| Quest Loot Party | `pangolp/mod-quest-loot-party`, default branch | `6f073c1bef1b` | Already current; narrow naturally dropped quest-item sharing. |
| MultiBot Bridge | `Wishmaster117/mod-multibot-bridge`, `main` | `1da05982e478` | Added at current head with natural-progression restrictions. |
| Token Turn-in | `Zerathane/mod-token-turnin`, default branch | `73e447c49975` | Added at current head; strict mode permits checks, blocks shortcut redemption. |
| MultiBot Chatless addon | `Wishmaster117/MultiBot-Chatless`, `main` | `80148dff3f3a` | Replaces `Macx-Lio/MultiBot`; paired with the bridge above. |

The maintained Playerbots core/module pair and original scoped module sources
remain appropriate for this realm. A newer fork is not inherently better for
Vanilla: generated auction stock, forced quest drops, broad personal equipment
loot and automatic token exchanges would change earned-play rules. This review
does not claim to benchmark every fork or establish complete raid/quest AI.

The Chatless project still uses the client folder/TOC name `MultiBot`. Each
portable release builds a separate `MultiBot-Chatless-<version>.zip` containing
that folder, its assets, upstream license and source revision, so players can
download and install it without the server ZIP.

The bridge revision has no explicit upstream license declaration; its packaged
`licenses/mod-multibot-bridge/NOTICE.txt` records that fact and its provenance
without inventing a license. Other dependencies retain their upstream licenses
or existing source license notices.

Validation and gameplay limitations are recorded in the Chatless/token addendum
of `vanilla-config-audit.md`. Future updates should re-check patch applicability,
core/module API compatibility and shortcut behavior before changing these pins.
