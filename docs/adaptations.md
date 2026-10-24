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

Bots follow Playerbots' natural progression, `Playerbots.NaturalProgression = 1`
in the default profile.

| Area | Behavior and limits |
| --- | --- |
| Earned progression | Bots start with ordinary character-creation items and earn levels, money, equipment and content milestones. Factory grants, routine resets and progression synchronization are disabled. |
| Upkeep | Autonomous bots without a player master walk to nearby vendors, repairers and trainers. They sell surplus, repair, pay for trainer lessons and buy food, drink, ammunition and reagents for the class spells they know, all with their own gold. Random bots also buy the largest affordable general-purpose vendor bag for an empty bag slot or, with a free backpack slot, to replace a smaller general bag; quivers, ammo pouches and profession bags stay equipped. Auction-house bag purchases follow the same slot rules. An NPC they cannot reach or use is skipped on the next search; no supplies are generated. |
| Auction trading | Autonomous bots trade owned surplus and spend their own gold through ordinary auctioneer and mailbox interactions. Generated AH stock is disabled. |
| Bot commands | Natural progression refuses the `maintenance`, `autogear`, `summon`, `tame`, `mail` and `sendmail` commands and ignores bot cheats; the default profile also disables `addclass`. Other commands follow the [Playerbots wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). |
| Flight points | Nearby controlled bots learn the visited point when their player or SelfBot master speaks to its flight master. Both characters must satisfy ordinary interaction checks. Bots fly only routes whose points they have discovered. |
| Exploration objectives | A follower can retain the master's quest-area trigger until it enters that area. The native handler validates its own active quest, position and other gates. This provides credit for physical arrival, without completing other objectives. |
| Group loot | Both roll entry points use the configured policy, reject duplicate votes and respect group masks and native Need Before Greed restrictions. Defaults permit Need for appropriate equipment upgrades and Greed for other useful loot. Item evaluation remains the upstream AI's responsibility. |
| MultiBot upkeep | Natural progression refuses remote equipment generation, glyph application, pet creation and renaming, remote pet calls and dismissals, and free maintenance. |
| Manual training | MultiBot purchases use the bot's current wallet and core trainer pricing, including reputation discounts. NPC access and the paid transaction remain native; autonomous spending keeps its AI budget. Optional preset discovery accepts absent entries without missing-key warnings. |
| Battlegrounds | Supported queues and matches follow each participant's earned era and level. Ordinary minimum team sizes apply; no automatic equipment or level catch-up is supplied. |
| World buffs | Simulated Vanilla events check each recipient's own rewarded milestones and native eligibility. TBC buffs retain ordinary quest, world-state and personal progression conditions. |
| Era world events | Outdoor encounters use each character's exact earned tier and the realm ceiling. Strict default progression blocks cross-era realm-wide phasing and passive victory payouts; ordinary creature kill loot remains native. |
| Autonomous dungeons | Suitable nearby random bots form real five-member parties for audited normal dungeons in their own earned Vanilla, TBC or Wrath era and walk to the physical portal. Each member's progress selects the era; level caps are 60, 70 and 80. Entrance and return travel share one Dungeon Clear route per party with checks before each movement section and swim speed in water. Members must pass the portal's native entry checks before they are invited. Routes come from world data, and required events and encounter controllers must use ordinary actions. |
| Player-led clears | A real player's group can run Dungeon Clear in any dungeon or raid it entered. Events run only through ordinary actions; movement, item, key and scripted-event shortcuts are refused. The Deadmines cannon uses powder looted from its chest through native opening, loot and item-use actions. Pull Lab runs and batches are disabled under natural progression. |
| Raid tactics | Raid Clear adds Onyxia's Lair, Molten Core, Blackwing Lair, Zul'Gurub and Ahn'Qiraj mechanics. Its Onyxia whelp action handles both native and restored Vanilla whelps. Only an equipped Onyxia Scale Cloak protects, and Suppression Devices are disarmed through the rogue's own spell. Natural progression refuses free Tranquilizing Shot teaching and synthetic cancellation of the bot's own crowd control. |
| Raid composition component | An internal recruitment function checks real Playerbots roles, hard tank/healer quotas, five-member subgroups and every bot's own era, access and lockout. Learned historical abilities inform buff preferences. No scheduler or route invokes it; autonomous raid runs remain unavailable. See [scope and quotas](raid-composition.md). |

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

See [era world events](world-events.md) for outdoor encounters, tier requirements
and schedules. Events require the default Individual Progression chain.

## World data

| Adaptation | Scope |
| --- | --- |
| Era creature modifiers | A module SQL update restores Individual Progression's damage and armor modifiers for the 532 creatures affected by the core's `2026_09_27_06.sql`. It replaces only fields still matching the core update's values, preserving other fields and subsequent custom values. |
| World database setup | A new world database applies Individual Progression's cleanup after the core renames `creature.id1` to `id` and before the module's zone data. The file keeps its contents, so existing realms record the new name without applying it again. |
| Netherstorm core updates | Core updates newer than Individual Progression's Netherstorm data reach existing realms after it. A module SQL update restores the module's escort script for Drijya (quest 10310) and Summoner Kanthin's formation and weapon sheath state, and removes five duplicate Sunfury Magister spawns, only where the rows still match the core updates. New realms already have the module's rows. |
| Frostmane Hold, quest 287 | The SQL update removes prerequisite 420 only when that is the existing value. Ordinary level/faction checks remain; follow-up quest 291 still requires 287. Existing unrelated custom prerequisites are preserved. |
| Historical priest quests | Original teacher relations and personal race, level and era gates select historical rank-1 rewards. Later ranks use paid training; native Wrath records are retained. See [class quests](class-quests.md). |
| Client cache | A world SQL migration assigns a stable `version.cache_id` for bundled quest and item data. The core uses it with `ClientCacheVersion = 0`; unchanged restarts retain it. Explicit overrides and higher database versions are preserved. See [cache updates and verification](updating.md#server-data-and-the-client-cache). |
| EraTalents spell groups | A targeted SQL update removes invalid rank or incompatible aura entries from the custom spell groups. Native rank and aura stacking checks remain in force. |
| Era experience | Quest values, battleground objective XP, XP bonus effects, and rest and quest money at the era cap follow each character's earned era; 2.4.3 quest values and 1.12 quest levels come from the pinned TBC and Classic DBs. See [experience by era](changing-expansions.md#experience-by-era). |
| Shared experience rules | Raid groups receive no party XP bonus on any map. Online rest in inns and cities uses the same base accrual rate as offline rest there, with the respective configured multipliers. |
| Formation movement | Formation velocity falls back to the creature's native walking speed when the computed movement velocity is effectively zero. Ordinary movement calculations remain in use. |

Source: [era creature modifiers](../patches/mod-individual-progression-creature-era-modifiers.patch),
[era experience](../patches/mod-individual-progression-era-experience.patch) with its
[Recruit-a-Friend grant limit](../patches/azerothcore-recruit-a-friend-grant-limit.patch),
[shared experience rules](../patches/azerothcore-experience-rules.patch),
[quest availability](../patches/mod-individual-progression-frostmane-hold.patch),
[world database setup](../patches/mod-individual-progression-cleanup-order.patch),
[Netherstorm core updates](../patches/mod-individual-progression-netherstorm-updates.patch),
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
retained. In its inventory's Buy mode, merchant clicks buy for the selected bot
with that bot's own gold. Its talent button uses native inspection with
EraTalents: historical trees and ranks belong to the inspected bot, and Wrath
retains Blizzard's view.
Controlled group altbots can spend their earned Vanilla/TBC points there;
other characters remain read-only. Optional quest, gear and guide addons and
their installation sources are listed in [client addons](addons.md).

The [Questie Playerbots integration](questie-playerbots.md) sends authorized
group bots' native quest counters through the MultiBot Bridge. Questie uses
its existing group tooltips and optional party map objectives. A small pinned
addon patch handles special objectives, WATCH renewal and stale-data cleanup.
Run the separate Questie-335 installer from the matching Latest release. It
downloads the pinned upstream addon and applies the patch locally; the prebuilt
server includes its MultiBot Bridge support.

[Zygor Individual Progression](zygor-progression.md) adapts Zygor Guides
Viewer Remaster the same way. The MultiBot Bridge reports the character's own
tier, quest availability and instance access read-only; guides, the Gear
Finder, best-in-slot lists and the Talent Advisor follow them, and an unknown
state unlocks nothing. Run the separate Zygor IP installer from the matching
Latest release.

## Validation and supported scope

The release workflow checks patched native gameplay handlers, launcher
subprocesses and update recovery, client generation and package contents before
publishing the Windows build. These checks cover the integrations above; they
do not certify every quest route, encounter tactic, third-party addon combination
or historical combat formula. See [supported scope](configuration.md#supported-scope)
for the practical limits.
