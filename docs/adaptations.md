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
| Data location | Configurations, databases, logs and server data live in the server folder. `PLAYERBOTS_WORKDIR`, or `%LOCALAPPDATA%\Playerbots` for a read-only server folder, moves them elsewhere; automatic updates then do not run. |
| Portable paths | Generated SQL source paths are relative. A missing absolute `SourceDirectory` is pointed at the complete bundled SQL tree, with configuration backups. |
| Supervision | MySQL, authserver and worldserver restart two seconds after they exit or crash, including after the console `server shutdown` command. |
| Shutdown | Ctrl+C requests shutdown of the launcher's own game servers before its database; timeout handling targets only owned processes. |
| Client packages | EraTalents and MultiBot are separate downloads. Each player installs matching client files manually with WoW closed. |

See [updates, moving the server and recovery](updating.md) for operating steps.

## Playerbots and group play

Bots follow Playerbots' natural progression, `AiPlayerbot.NaturalProgression = 1`
in the default profile.

| Area | Behavior and limits |
| --- | --- |
| Earned progression | Bots start with ordinary character-creation items and earn levels, money, equipment and content milestones. Factory grants, routine resets and progression synchronization are disabled. |
| Upkeep | Autonomous bots without a player master walk to nearby vendors, repairers and trainers. They sell surplus, repair, pay for trainer lessons and buy food, drink, ammunition and reagents for spells they know, all with their own gold. An NPC they cannot reach or use is skipped on the next search; no supplies are generated. |
| Auction trading | Autonomous bots trade owned surplus and spend their own gold through ordinary auctioneer and mailbox interactions. Generated AH stock is disabled. |
| Bot commands | Natural progression refuses the `maintenance`, `autogear`, `summon`, `tame`, `mail` and `sendmail` commands and ignores bot cheats; the default profile also disables `addclass`. Other commands follow the [Playerbots wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). |
| Flight points | Nearby controlled bots learn the visited point when their player or SelfBot master speaks to its flight master. Both characters must satisfy ordinary interaction checks. Bots fly only routes whose points they have discovered. |
| Exploration objectives | A follower can retain the master's quest-area trigger until it enters that area. The native handler validates its own active quest, position and other gates. This provides credit for physical arrival, without completing other objectives. |
| Group loot | Both roll entry points use the configured policy, reject duplicate votes and respect group masks and native Need Before Greed restrictions. Defaults permit Need for appropriate equipment upgrades and Greed for other useful loot. Item evaluation remains the upstream AI's responsibility. |
| Manual training | MultiBot purchases use the bot's current wallet and core trainer pricing, including reputation discounts. NPC access and the paid transaction remain native; autonomous spending keeps its AI budget. Optional preset discovery accepts absent entries without missing-key warnings. |
| Battlegrounds | Supported queues and matches follow each participant's earned era and level. Ordinary minimum team sizes apply; no automatic equipment or level catch-up is supplied. |
| World buffs | Simulated Vanilla events check each recipient's own rewarded milestones and native eligibility. TBC buffs retain ordinary quest, world-state and personal progression conditions. |
| Autonomous dungeons | Suitable nearby random bots form real five-member parties for audited normal dungeons in their own earned Vanilla, TBC or Wrath era and walk to the physical portal. Each member's progress selects the era; level caps are 60, 70 and 80. Entrance and return travel share one Dungeon Clear route per party with checks before each movement section and swim speed in water. Members must pass the portal's native entry checks before they are invited. Routes come from world data, and required events and encounter controllers must use ordinary actions. |
| Player-led clears | A real player's group can run Dungeon Clear in any dungeon or raid it entered. Events run only through ordinary actions; movement, item, key and scripted-event shortcuts are refused. Pull Lab runs and batches are disabled under natural progression. |
| Raid tactics | Raid Clear adds Molten Core, Blackwing Lair and Zul'Gurub mechanics. Only an equipped Onyxia Scale Cloak protects, and Suppression Devices are disarmed through the rogue's own spell. Natural progression refuses free Tranquilizing Shot teaching and synthetic cancellation of the bot's own crowd control. |

Settings and scope are documented in [configuration](configuration.md),
[bot brackets and PvP](earned-bot-brackets.md) and
[auction trading](earned-auctions.md). The exploration and loot integrations are
implemented in [area-trigger handling](../patches/mod-playerbots-quest-area-triggers.patch)
and [roll policy](../patches/mod-playerbots-loot-roll-policy.patch).

See [bot dungeons](bot-dungeons.md) for recruitment, supported instances and
travel requirements. LFG Progression supplies earned-era access guards for the
optional Dungeon Finder; it does not navigate or run encounters.

See [world buffs](world-buffs.md) for event timers, recipient conditions and the
[world-event integration](../patches/mod-world-buff-bots-earned-era.patch).

## World data

| Adaptation | Scope |
| --- | --- |
| Era creature modifiers | A module SQL update restores Individual Progression's damage and armor modifiers for the 532 creatures affected by the core's `2026_09_27_06.sql`. It replaces only fields still matching the core update's values, preserving other fields and subsequent custom values. |
| Frostmane Hold, quest 287 | The SQL update removes prerequisite 420 only when that is the existing value. Ordinary level/faction checks remain; follow-up quest 291 still requires 287. Existing unrelated custom prerequisites are preserved. |
| Historical priest quests | Original teacher relations and personal race, level and era gates select historical rank-1 rewards. Later ranks use paid training; native Wrath records are retained. See [class quests](class-quests.md). |
| EraTalents spell groups | A targeted SQL update removes invalid rank or incompatible aura entries from the custom spell groups. Native rank and aura stacking checks remain in force. |
| Formation movement | Formation velocity falls back to the creature's native walking speed when the computed movement velocity is effectively zero. Ordinary movement calculations remain in use. |

Source: [era creature modifiers](../patches/mod-individual-progression-creature-era-modifiers.patch),
[quest availability](../patches/mod-individual-progression-frostmane-hold.patch),
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
retained. Its talent button uses native inspection with EraTalents: historical
trees and ranks belong to the inspected bot, and Wrath retains Blizzard's view.
Historical inspection is read-only. Optional quest, gear and guide addons are linked in
[client addons](addons.md) and installed from their upstream projects.

## Validation and supported scope

The release workflow checks patched native gameplay handlers, launcher
subprocesses and update recovery, client generation and package contents before
publishing the Windows build. These checks cover the integrations above; they
do not certify every quest route, encounter tactic, third-party addon combination
or historical combat formula. See [supported scope](configuration.md#supported-scope)
for the practical limits.
