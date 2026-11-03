# Server adaptations

This distribution combines maintained core, module and addon forks with an
earned-play profile. The [source guide](module-versions.md) and
[versions.lock.json](../versions.lock.json) record the exact revisions, original
projects and integration commits. This page summarizes the resulting behavior;
linked guides contain settings, controls and content limits.

## Launcher and distribution

| Area | Behavior |
| --- | --- |
| Updates | Normal startup verifies and replaces changed managed server files, with file rollback and interrupted-update recovery. SQL migrations run at server startup. |
| User data | Existing characters, databases, downloaded data and custom configuration values are preserved. Managed defaults change only where the previous managed value remains active. File rollback does not reverse SQL migrations. |
| Data location | Configurations, databases, logs and server data normally live beside `startup.exe`. An external `PLAYERBOTS_WORKDIR` or the fallback `%LOCALAPPDATA%\Playerbots` data folder disables automatic server updates. |
| Supervision | MySQL, authserver and worldserver restart after they exit, including after `server shutdown`. Ctrl+C stops the realm's own game servers before MySQL. |
| Portability | Generated SQL paths are relative where possible. A missing legacy absolute `SourceDirectory` ending in `/src` is repaired only when the bundled SQL tree is complete, with configuration backups. |
| Client files | The server updater never modifies WoW. Each player installs the matching EraTalents addon and MPQ, and optional addons from their forks, with WoW closed. |

See [running, backups, updates and recovery](updating.md).

## Playerbots and group play

The shipped profile enables `Playerbots.NaturalProgression = 1`. Automatic
talent allocation leaves SelfBot characters and controlled altbots under their
owner's control. Autonomous dungeon recruitment selects random bots and
excludes ordinary players, SelfBot characters and controlled altbots.

| Area | Behavior and limits |
| --- | --- |
| Earned progression | Bots start with ordinary character-creation items and earn levels, gold, equipment, quests and era milestones. Factory grants, routine resets and leader-progress synchronization are disabled. |
| Free-bot RPG goals | New RPG selects independent activities and travel destinations. Ambient `grind` pulls yield while a free bot travels, gathers or handles other RPG goals, but remain available while wandering or at a quest objective. Combat reactions and ordinary loot remain independent. |
| Upkeep | Autonomous bots walk to usable vendors, repairers and trainers, and pay for lessons, repairs, supplies and general-purpose bags with their own gold. Unreachable NPCs are skipped; no supplies are generated. |
| Trading | Bots sell owned surplus and spend their own gold through ordinary auctioneer and mailbox interactions. See [earned auctions](earned-auctions.md). |
| Commands | Natural progression refuses `maintenance`, `autogear`, `summon`, `tame`, `mail` and `sendmail` and ignores bot cheats. The default profile also disables `addclass`; remaining commands follow the [Playerbots wiki](https://github.com/mod-playerbots/mod-playerbots/wiki/Playerbot-Commands). |
| Travel and exploration | Bots walk real routes and fly only discovered routes. Companions can learn a visited flight point, or bind at the inn where their player or SelfBot master binds, when both can interact with that flight master or innkeeper. Random bots discover a zone's flight point by speaking to its flight master. Bots change continents and islands by boarding ships, zeppelins, elevators and the Deeprun Tram, with their player when following, using portals and the Dark Portal in person, or casting their own teleports and hearthstone, within their faction's territory and their own earned era; see [continent travel](configuration.md#continent-travel). Quest-area credit requires the bot's own active quest and physical arrival. |
| Death recovery | Released bots use ordinary corpse runs, instance portals and core resurrection checks. Repeated deaths, long ghost runs and reduced AI activity do not disable recovery. Ghosts walk navigation-mesh routes, in legs over long distances, and use the spirit healer when no walk reaches the body. In a clear, bots stay down only while a party member can resurrect them with their own spell. SelfBot ghosts are walked back by their player. |
| Equipment and loot | Bots can equip suitable owned bag items. Group rolls respect native eligibility and Need Before Greed restrictions; the default is Need for appropriate upgrades and Greed for other useful items. See [combat profiles](combat-profiles.md). |
| MultiBot actions | Paid purchases, training and bank actions require ordinary access. Remote gear, glyph, pet and maintenance grants are refused. Combat-profile choices refresh strategies and owned equipment outside combat; they do not spend controlled characters' talent points. |
| Dungeons and raids | Nearby random bots can form five-member parties for audited normal dungeons in their own earned era and walk to the entrance. Player-led clears and integrated Raid Clear tactics use ordinary actions, with earned-play guards on selected encounter shortcuts. Autonomous raids remain unavailable. See [dungeon and raid scope](bot-dungeons.md). |
| Battlegrounds | Supported queues and matches use each participant's earned era and level, with ordinary minimum teams and no equipment or level catch-up. See [bot brackets and PvP](earned-bot-brackets.md). |
| Buffs and events | Native quest and area events supply buffs; optional timed Vanilla buffs are disabled by default. Outdoor era encounters require each recipient's exact earned tier. Strict progression blocks automatic victory payouts. See [world buffs](world-buffs.md) and [era events](world-events.md). |
| Party quest loot | Quest Loot Party shares naturally rolled normal-quality quest items with eligible corpse looters. Ordinary drop rolls, equipment loot, quest prerequisites and personal progression remain in force. |

LFG Progression guards the [optional Dungeon Finder](bot-dungeons.md#optional-dungeon-finder).
It does not supply routes or encounter tactics. Difficulty does not scale down
for smaller parties. The [configuration guide](configuration.md) describes the
active files and default policies.

## World data

| Adaptation | Scope |
| --- | --- |
| Era creature modifiers | Targeted SQL restores damage and armor modifiers affected by a conflicting core update and historical health/damage base tables. Outdoor bosses and guards that retained stock Wrath levels receive historical values. Shared creature statistics do not switch per character; later custom field values are preserved. |
| World setup, Wetlands and Netherstorm | SQL ordering keeps Individual Progression's cleanup compatible with the core schema. Guarded updates restore Drijya's escort, Summoner Kanthin's formation and sheath state, the Wetlands Dark Iron scripts and a Netherstorm Mageslayer's spawn height, and remove duplicate Sunfury Magister spawns on established realms. |
| Frostmane Hold, quest 287 | Removes prerequisite 420 only where that value remains; ordinary level/faction checks and quest 291's prerequisite remain. |
| Era world content | Spawns, quests and vendor items follow the earned tier of their expansion or patch, from Vanilla's 1.6 to Wrath's 3.3.5. Creatures that drop or are needed by earlier quests stay. Troll Necklace Bounty's repeatable turn-in, Mastering the Elements, Mortal Champions, the Darnassus commendation signets, and Vanilla's Warsong Gulch and Arathi Basin reputation turn-ins regain their givers; the first three and the turn-ins end with TBC. Guard Didier and Seer Nakha return to their posts. See [world content by era and patch](changing-expansions.md#world-content-by-era-and-patch). |
| Historical class quests | Personal race, level and earned-era gates select restored priest rank-1 rewards; later ranks use paid training. Native Wrath records remain. See [class quests](class-quests.md). |
| Client cache | A stable database cache version refreshes client query data after relevant SQL migrations. Explicit overrides and higher administrator-managed versions remain. See [cache behavior](updating.md#server-data-and-the-client-cache). |
| EraTalents spell groups | Targeted corrections remove invalid rank or incompatible aura entries while retaining native rank and aura stacking checks. |
| Era experience | Quest values, battleground objective XP, XP bonuses, rest and quest money at the era cap follow each character's earned era. See [experience by era](changing-expansions.md#experience-by-era). |
| Shared experience | Raid groups receive no party XP bonus on any map. Rest in inns/cities uses the same base rate online and offline, with the corresponding configured multipliers. Thrallmar's and Honor Hold's Favor apply their XP bonus once. |
| Formation movement | Near-zero computed velocity falls back to the creature's native walking speed. |
| Spell cancellation | Cancelling a game object's spell removes dynamic objects without a unit caster; a world trigger's objects are removed from its original caster. |
| Inventory saving | An item saved outside the inventory save leaves its owner's update queue, so the next save stores or deletes it once. |
| Aura states | Aura state changes walk a snapshot of owned auras, so effects that add or remove auras cannot overrun the walk. |
| Hidden creatures | A creature or gameobject that its scripts or visibility conditions hide from a player is absent for that player and the player's pets, and it does not perceive them either: it neither shows, aggroes nor targets them. |
| Bot aura updates | Players without an open connection, mostly bots, update their owned auras every 100 ms with the accumulated time. Durations and periodic totals are unchanged; connected players update every tick. |

SQL updates run through the ordinary database updater. Back up an established
realm before applying them. Progression uses shared AzerothCore quest data with
selected corrections; it does not provide three complete historical quest
databases. The server decides each character's eligibility, even when an
addon's static quest data differs. Use [read-only quest diagnostics](quest-diagnostics.md)
to investigate access without granting quest or progression credit.

## Client integration

| Integration | Behavior |
| --- | --- |
| [EraTalents](era-talents.md) | Matching addon and MPQ provide Vanilla 1.12.1 and TBC Classic 2.5.4 trees, selected restored spells, and German/English text. The core and client remain Wrath 3.3.5a. |
| [DragonUI](era-talents.md#dragonui) | Historical trees render for the player and inspected bots. Spellbook and level-up notices follow the character's trainer list; glyph access follows earned Wrath. |
| [MultiBot](addons.md) | Inspected historical trees belong to the selected bot. Controlled group altbots can spend their earned Vanilla/TBC points; other inspected characters stay read-only. The Bridge supplies the bot's own spells, inventory, money and control state. |
| [Questie](questie-playerbots.md) | Authorized group bots' native quest counters feed Questie's group tooltips and optional party objectives. Each character sees only the quests and questgivers of its own era. It does not complete quests or unlock content. |
| [Zygor](zygor-progression.md) | Read-only server tier, quest and instance access inform guides, Gear Finder and Talent Advisor. Unknown progression does not unlock content. |

Install optional addons from their [forks' Latest releases](addons.md#addon-forks).
The complete EraTalents client pack comes from the server release; an addon-only
ZIP does not replace its matching MPQ.

## Validation and supported scope

Source fixtures, launcher tests and package checks cover selected production
handlers and release behavior. A successful complete build establishes compile
integration; it does not establish full in-game coverage. Complete dungeon and
raid runs, all class quests, the 2,500-bot target and some addon interactions
still need live validation. Some upstream AI encounter actions retain movement
or combat shortcuts. Historical talents and selected rules do not replace every
Wrath combat formula or world-data system. See [supported scope](configuration.md#supported-scope)
and the [validation roadmap](todo.md#gameplay-validation).
