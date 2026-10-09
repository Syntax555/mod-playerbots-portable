# Server adaptations

This distribution combines pinned upstream projects with local integration
patches and an earned-play configuration. This guide describes its supported
behavior. [Dependencies and build provenance](module-versions.md) and
[versions.lock.json](../versions.lock.json) identify exact revisions and ordered
patches; packaged source manifests also record their hashes.

## Launcher and distribution

| Area | Behavior |
| --- | --- |
| Server updates | Normal startup checks Latest, downloads changed managed files, verifies their hashes and installs them with rollback and recovery. The console reports progress and activity. |
| User data | Databases, characters, downloaded server data and custom settings are preserved. Managed configuration defaults follow the saved baseline. |
| Portable paths | Generated SQL source paths are relative. Missing legacy paths produced by the launcher can be repaired from the complete bundled SQL tree, with configuration backups. |
| Shutdown | Ctrl+C requests shutdown of the launcher's own game servers before its database; timeout handling targets only owned processes. |
| Client packages | EraTalents and MultiBot are separate downloads. Each player installs matching client files manually with WoW closed. |

See [updates, moving the server and recovery](updating.md) for operating steps.

## Playerbots and group play

| Area | Behavior and limits |
| --- | --- |
| Earned progression | Bots start with ordinary character-creation items and earn levels, money, equipment and content milestones. Factory grants, routine resets and progression synchronization are disabled. |
| Auction trading | Autonomous bots trade owned surplus and spend their own gold through ordinary auctioneer and mailbox interactions. Generated AH stock is disabled. |
| Flight points | Nearby controlled bots learn the visited point when their player or SelfBot master speaks to its flight master. Both characters must satisfy ordinary interaction checks. |
| Exploration objectives | A follower can retain the master's quest-area trigger until it enters that area. The native handler validates its own active quest, position and other gates. This provides credit for physical arrival, without completing other objectives. |
| Group loot | Both roll entry points use the configured policy, reject duplicate votes and respect group masks and native Need Before Greed restrictions. Defaults permit Need for appropriate equipment upgrades and Greed for other useful loot. Item evaluation remains the upstream AI's responsibility. |
| Manual training | MultiBot purchases use the bot's current wallet and core trainer pricing, including reputation discounts. NPC access and the paid transaction remain native; autonomous spending keeps its AI budget. |
| Battlegrounds | Supported queues and matches follow each participant's earned era and level. Ordinary minimum team sizes apply; no automatic equipment or level catch-up is supplied. |

Settings and scope are documented in [configuration](vanilla-config-audit.md),
[bot brackets and PvP](earned-bot-brackets.md) and
[auction trading](earned-auctions.md). The exploration and loot integrations are
implemented in [area-trigger handling](../patches/mod-playerbots-quest-area-triggers.patch)
and [roll policy](../patches/mod-playerbots-loot-roll-policy.patch).

## World data

| Adaptation | Scope |
| --- | --- |
| Frostmane Hold, quest 287 | The SQL update removes prerequisite 420 only when that is the existing value. Ordinary level/faction checks remain; follow-up quest 291 still requires 287. Existing unrelated custom prerequisites are preserved. |
| EraTalents spell groups | A targeted SQL update removes invalid rank or incompatible aura entries from the custom spell groups. Native rank and aura stacking checks remain in force. |
| Formation movement | Formation velocity falls back to the creature's native walking speed when the computed movement velocity is effectively zero. Ordinary movement calculations remain in use. |

Source: [quest availability](../patches/mod-individual-progression-frostmane-hold.patch),
[spell-group contracts](../patches/mod-era-talents-spell-groups.patch) and
[formation movement](../patches/azerothcore-formation-minimum-velocity.patch).
SQL updates run through the ordinary database updater.

Progression uses shared AzerothCore quest data with selected corrections. It
does not supply three complete historical quest databases. Quest addons with
static data can show different availability; each character's server-side
progression determines access.

## Client integration

The matching EraTalents addon and merged MPQ provide historical trees and German
and English text. German locale merging preserves numeric gameplay fields and
other locale slots. Historical TBC trees use Classic 2.5.4 data; the client and
core remain Wrath 3.3.5a. See [EraTalents](era-talents.md) for installation and
supported historical rules.

The prepared MultiBot addon displays gold, silver and copper and initializes its
options with the supported fallback interface. Existing saved settings are
retained. Optional quest, gear and guide addons are linked in
[client addons](addons.md) and installed from their upstream projects.

## Validation and supported scope

The release workflow checks patched native gameplay handlers, launcher
subprocesses and update recovery, client generation and package contents before
publishing the Windows build. These checks cover the integrations above; they
do not certify every quest route, encounter tactic, third-party addon combination
or historical combat formula. See [supported scope](vanilla-config-audit.md#supported-scope)
for the practical limits.
