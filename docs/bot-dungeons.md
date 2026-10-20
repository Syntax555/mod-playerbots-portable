# Bot dungeons and raids

Bots clear instances with Dungeon Clear, Raid Clear and Playerbots' own
encounter tactics. Under natural progression they act only as ordinary players
can: they walk real routes, open objects without a lock or with their own key,
talk to NPCs, fight and loot. They earn their own keys and items; teleports,
free resurrections and encounter shortcuts are refused.

## Autonomous parties

Five nearby random bots form a party: a tank, a healer and three damage
dealers of one faction. They use their own earned level, equipment and
progression, walk to the entrance and attempt the dungeon through ordinary
combat and loot. A human party leader is optional. Controlled companions,
SelfBot characters and existing player groups are not recruited.

All members must have the dungeon's earned era and a level within its band.
Vanilla, TBC and Wrath parties use level caps of 60, 70 and 80. Each bot's own
rewarded progression determines its era; the tank's level or another character
on the account does not unlock it. The tank must be near the outdoor entrance,
and navigation data must provide a real route. The coordinator does not summon
distant bots or generate equipment, money, keys, attunements or missing group
members. A large bot population does not guarantee that a suitable party forms
near an entrance.

### Dungeons

Entrance and exit portals, level bands and faction come from the world data.
A band is the Dungeon Finder's recommended level range, extended by
`LevelSpread` within the dungeon's entry range and earned-era level cap.
The dungeon record determines the era even when a TBC or Wrath entrance is in
Kalimdor. Portals inside a capital admit only that capital's faction.

### Vanilla routes

| Dungeon | Finder id | Bot levels | Autonomous parties |
| --- | --- | --- | --- |
| Ragefire Chasm | 4 | 15–19 | Horde only |
| Wailing Caverns | 1 | 17–23 | Enabled with checked ramp paths and the native Disciple escort |
| The Deadmines | 6 | 17–23 | Enabled with the ordinary gunpowder and cannon actions |
| Shadowfang Keep | 8 | 18–24 | Enabled |
| Blackfathom Deeps | 10 | 21–27 | Enabled |
| The Stockade | 12 | 22–28 | Alliance only |
| Razorfen Kraul | 16 | 24–30 | Enabled |
| Gnomeregan | 14 | 25–31 | Enabled |
| Scarlet Monastery: Graveyard, Library, Armory, Cathedral | 18, 165, 163, 164 | 29–35, 32–38, 34–40, 37–43 | Enabled |
| Razorfen Downs | 20 | 34–40 | Enabled |
| Uldaman | 22 | 37–43 | Not enabled: Ironaya's keystone requires the Staff of Prehistoria |
| Zul'Farrak | 24 | 43–49 | Not enabled: Witch Doctor Zum'rah is woken by a script |
| Maraudon: Purple, Orange, Pristine Waters | 272, 26, 273 | 41–47, 43–49, 45–51 | Enabled |
| Sunken Temple | 28 | 47–53 | Enabled |
| Blackrock Depths: Prison, Upper City | 30, 276 | 49–55, 53–59 | Not enabled: the Shadowforge Lock requires a key |
| Lower Blackrock Spire | 32 | 57–60 | Enabled |
| Dire Maul: East, West, North | 34, 36, 38 | 55–60, 58–60, 60 | Enabled |
| Scholomance | 2 | 60 | Enabled |
| Stratholme: Main Gate, Service Entrance | 40, 274 | 60 | Enabled |

A dungeon is enabled when its required Dungeon Clear objectives and conditional
controllers for pulling or movement use audited ordinary actions. Unsupported
controllers cannot be treated as dispensable simply because upstream marks
them optional. Events requiring scripted shortcuts, unaudited item acquisition
or locked objects without an audited ordinary interaction prevent automatic
recruitment for that map.

For Wailing Caverns, the party backtracks to the ramp by Anacondra's platform
and walks the native patrol route to Serpentis and back from Verdan. Each leg
requires a complete navigation-mesh path to the intended floor, with every
spline segment checked. Bots follow the same checkpoints, and each leg waits
for every member to arrive; humans walk there themselves. Missing mesh, partial
routes and unsafe gaps stop the objective; bots do not cross the drops by
jumping or relocation.

After the four Fanglords are defeated, the party gathers at the Disciple of
Naralex and starts his normal gossip escort. The native SmartAI controls its
pace, ambushes, cleansing channel, ritual waves, Mutanus and Naralex's awakening.
Bots follow over checked paths and protect the Disciple through ordinary combat.
Completion requires Mutanus's kill credit and the native post-dialogue departure
marker; a spawned boss or missing NPC is not success. An unsafe follower path
pauses the clear. Missing, dead or reset NPCs block or require an ordinary retry,
and the escort has a finite fifteen-minute attempt budget. The tank's escort
action takes priority over starting food or drink, so long fights can exhaust
its resources.

Fixtures cover the native data contracts, routes, prerequisites and interruption
guards. Complete Wailing Caverns runs still need in-game validation, especially
the joins to the ramp, group spacing, combat and recovery between waves. A long
pause can miss the short departure-marker window before the NPCs despawn; the
objective then remains blocked instead of inferring completion. Automatic
recruitment still depends on the installed world-data audit, ordinary entry
checks and usable navigation data.

For the Deadmines, the tank opens the Defias Gunpowder chest with its native
opening spell, takes the powder through Playerbots' normal loot handling and
walks back to use the carried item on the Defias Cannon. The core checks the
item, lock, cast and interaction range and consumes the powder. Only the Iron
Clad Door's cannon-open state completes the objective. No quest is required
for this chest in the pinned world data. Its native ambushes still occur.

This item action alone is admitted by the event audit. Missing or unavailable
powder, bags above Playerbots' 80% usage safeguard, custom loot restrictions, a
blocked chest or missing navigation can still stall the run. Powder in another
character's bags is not borrowed.
A player carrying it can fire the cannon normally. Complete autonomous Deadmines
runs, the chest detour and combat interruptions still need in-game validation.

In player-led Uldaman clears, bots walk to and use the Altar of the Keepers and
the Altar of Archaedas through Playerbots' ordinary object action. The pinned
core requires one participant to channel for five seconds; it checks the ritual
owner's group and removes interrupted channels. Bots wait for the native fight
to finish, avoid another ritual while keepers are awake or Archaedas is active,
and retry through ordinary use after an interruption or encounter reset. Missing
objects, blocked paths or the core's refusal of a missing ritual owner or an
unrelated group can stall the objective.

Automated fixtures cover the ritual, interaction guards and retries; complete
Uldaman runs and recovery still need in-game validation. Autonomous recruitment
remains refused because acquiring the Staff of Prehistoria for Ironaya's
keystone has no audited acquisition driver. A player-led group must bring its
own staff and open the seal through the normal interaction.

In player-led Blackrock Depths clears, the Ring of Law objective gathers the
group inside the arena's actual trigger volume. Bots walk there over checked
mesh paths; human members enter themselves. The tank submits the ordinary
area-trigger action only after everyone arrives. The core starts Grimstone,
spawns the waves and boss, controls the gates and awards encounter credit.
The objective waits for the core's exact completed state, including Grimstone's
final walk after the boss dies. An empty arena between waves is not completion.

An already running event continues through normal combat. After a native reset,
the group gathers again and the core enforces its two-minute post-wipe cooldown.
A cancelled or paused bot clear does not submit a queued arena start.
Missing paths, dead or absent members can stall a new start. Fixtures cover the
spatial trigger, group guards, retries and completion checks; complete Ring of
Law and Blackrock Depths runs still need in-game validation. Autonomous parties
remain refused because the separate Shadowforge Lock objective requires a key.

### TBC and Wrath routes

The default configuration also lists all 16 normal TBC and 16 normal Wrath
Dungeon Finder entries. Heroic, raid, random-queue and holiday entries are
excluded. The event audit admits candidates; actual world data, entrances,
object locks and navigation can further restrict them.

| Era | Candidate routes | Refused event routes |
| --- | --- | --- |
| TBC | Hellfire Ramparts, Blood Furnace, Mana-Tombs, Auchenai Crypts, Sethekk Halls, Shadow Labyrinth, Botanica, Magisters' Terrace | Shattered Halls, Slave Pens, Underbog, Steamvault, Escape from Durnholde, Black Morass, Mechanar, Arcatraz |
| Wrath | Utgarde Keep, Ahn'kahet, Nexus, Forge of Souls | Utgarde Pinnacle, Azjol-Nerub, Oculus, Halls of Lightning, Halls of Stone, Culling of Stratholme, Drak'Tharon Keep, Gundrak, Violet Hold, Trial of the Champion, Pit of Saron, Halls of Reflection |

Refused routes require event, escort, vehicle, item or movement handling that
the earned integration cannot perform through ordinary actions. For example,
Trial of the Champion needs its arena controller, and Drak'Tharon Keep needs
an unaudited Novos controller. They remain available to player-led groups.
Steamvault's required access-panel objective needs an opening lock type that
the ordinary event click does not implement. Special opening, closing or
blasting spells do not count as a plain unlocked interaction in the event audit.

Entry rules still apply to candidate routes. Individual Progression admits
Magisters' Terrace from tier 12 and The Forge of Souls from tier 16; the core
checks attunements, lockouts and instance limits. Before
recruiting, the coordinator asks the portal's own checks for every member, so
bots that cannot enter are not invited.

The worldserver log lists every configured dungeon at startup as enabled or
not enabled with its reason. That log is authoritative for the installed world
data. Complete autonomous runs have not been verified in-game; automated checks
cover the coordinator, era boundaries, event audit and selected handlers.

## Player-led clears

With a real player in the group, playing normally or as SelfBot, the tank bot
can lead a clear in any dungeon or raid the group entered through the normal
portal checks. Start it with `dc on` in party chat or `.dc on`; `dc off` ends
it. Altbots and SelfBot characters keep their own equipment and progression.

The optional [DungeonClear addon](addons.md#optional-upstream-addons) opens its
control panel with `/dc`, showing the boss list, run status and controls. Install
it separately from its upstream project. If a start request appears to do
nothing, `.dc on` in chat exposes server refusals that the addon may omit.

Scripted events run only through ordinary actions. An optional event the bots
cannot perform is skipped. A required one stalls the clear: perform the action
yourself and the clear continues, or skip the objective with `dc skip`.

## Raids

Raid Clear adds boss and trash mechanics for Onyxia's Lair, Molten Core, Blackwing Lair,
Zul'Gurub and both Ahn'Qiraj raids: kill order, main and off-tank roles, spacing
and positioning against the bosses' abilities. They apply on these maps whether
you lead the raid or a player-led clear walks it from boss to boss, alongside
Playerbots' own raid strategies. Autonomous parties do not enter raids.

Under natural progression only an equipped Onyxia Scale Cloak protects against
Shadow Flame, and Suppression Devices are disarmed only by rogues casting
Disarm Trap. Raid entry keeps native attunements and Individual Progression
requirements. Molten Core's runes must be doused with Aqual Quintessence; bots
do not douse them.
Hunters must earn Tranquilizing Shot. Natural progression also keeps a bot's
own crowd control in place when its formerly mind-controlled target returns
to the raid; it does not cancel those auras artificially.
AutoBalance scales raid difficulty to the number of players and bots present.

Onyxia's Lair has a registered Raid Clear strategy for map 249 alongside
Playerbots' `onyxia` strategy. The implementation covers Deep Breath movement
from the server's spell positions, Fireball spacing, tank positioning and
threat during the restored level-60 encounter. Its whelp action selects both
native whelps (`11262`) and Individual Progression's Vanilla whelps (`301001`),
retains a living, non-evading current whelp and skips evading targets.

These are code and fixture checks; a complete Onyxia clear has not been
verified in game. Each character still needs its own progression and native
entry requirements, including the Drakefire Amulet where required. EraTalents
keeps each bot's own historical spells and talents; ordinary attack and spell
checks still apply. The remaining encounter tests are listed in the
[gameplay validation checklist](todo.md#gameplay-validation).

## Travel and encounters

Entrance and return travel use Dungeon Clear's existing route planner over the
native navigation mesh. The party shares one calculated route per journey and
bots follow it in short sections, each checked from the bot's current position
before movement. After a fight, looting or another interruption a bot rejoins
the nearest point of the route; a new route is calculated only when no point is
within reach or the travel destination changes. Sections crossing water use the
bot's swim speed. Missing navigation and unsafe sections stop the attempt.

Each bot must reach the entrance and pass the ordinary instance-entry handler;
the run starts after all five arrive in the same instance. If the portal
refuses a member, the attempt stops and that bot is not recruited for the
dungeon again for two hours or until its level or progression changes. Entering
and leaving uses the physical dungeon portal. The ordinary Dungeon Finder is not used to
teleport the party.

Natural progression rejects movement shortcuts, artificial combat recovery and
item grants. Missing routes, failed recruitment, wipes, timeouts and objectives
that stall for five minutes stop an autonomous attempt. Corpses, loot
eligibility and paid character upkeep remain subject to the core's rules.
Encounter tactics and real navigation can still fail; the module does not turn
such failures into completed runs.

Natural progression disables `.dc lab run` and `.dc lab batch`, including
their background test-party provisioning. Lab status and stop remain available.

## Configuration

Edit `configs/modules/mod_dungeon_clear.conf` with the server stopped:

```ini
DungeonClear.Enable = 1
DungeonClear.AutonomousParties.Enable = 1
DungeonClear.AutonomousParties.MaxConcurrent = 2
DungeonClear.AutonomousParties.Dungeons = "4,1,6,8,10,12,16,14,18,165,163,164,20,22,24,272,26,273,28,30,276,34,32,36,2,38,40,274,136,137,138,140,146,147,148,149,150,151,170,171,172,173,174,198,202,203,204,206,207,208,209,214,216,218,220,225,245,251,253,255"
DungeonClear.AutonomousParties.LevelSpread = 3
```

The simultaneous-party limit accepts 1–8. `Dungeons` lists Dungeon Finder ids;
remove an id to keep autonomous parties out of that dungeon. `LevelSpread`
accepts 0–10. Set the autonomous-party switch to `0` to stop automatic
recruitment. The strict travel and gameplay guards require
`Playerbots.NaturalProgression = 1` in `configs/modules/playerbots.conf`.
Automatic parties also require Individual Progression's strict default earned
chain. A realm with a disabled or custom progression chain does not use level
or account progress as a substitute.

Raid Clear's tactics are set in `configs/modules/mod_raid_clear.conf`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `RaidClear.Enable` | `1` | Master switch, read at startup |
| `RaidClear.Bots.TeachTranquilizingShot` | `0` | Automatic spell teaching is disabled; natural progression refuses it even with a custom `1` |
| `RaidClear.KillOrder` | `1` | The main tank marks the add to kill first; damage dealers attack it |
| `RaidClear.Tanks.AssignMainTank` | `1` | Give the Main Tank flag to the first tank when nobody has it |
| `RaidClear.Tanks.Split` | `1` | Other tanks act as off-tanks |
| `RaidClear.Tanks.Separation` | `12` | Minimum yards between tanked trash mobs; `0` disables it |
| `RaidClear.Tanks.SeparateOnBosses` | `0` | Also separate tanked mobs during boss fights |
| `RaidClear.DeathLog` | `1` | Log each raid death and its causes to `logs/Server.log` |
| `RaidClear.MoltenCore.Enable`, `RaidClear.BlackwingLair.Enable`, `RaidClear.ZulGurub.Enable` | `1` | Tactics for each raid |
| `RaidClear.OnyxiasLair.Enable` | `1` | Onyxia tactics for the native and restored level-60 encounters on map 249 |
| `RaidClear.RuinsOfAhnQiraj.Enable`, `RaidClear.TempleOfAhnQiraj.Enable` | `1` | Ahn'Qiraj 20- and 40-player encounter tactics |

`Playerbots.ApplyInstanceStrategies = 1` in `configs/modules/playerbots.conf`
keeps Playerbots' own encounter strategies active alongside Raid Clear.

The file's comments say Suppression Devices need the "raid" bot cheat or a
rogue. Under natural progression bot cheats have no effect: only a bot that
knows Disarm Trap turns a device off, and only an equipped Onyxia Scale Cloak
protects against Shadow Flame.

Updates extend an unchanged managed dungeon list and preserve custom lists,
autonomy switches and party limits. For an existing custom list, add the desired
normal Dungeon Finder ids explicitly; an entry must still pass the event audit.

Random bots run while at least one real player session is connected through
`Playerbots.DisabledWithoutRealPlayer = 1`. Login begins after a 30-second delay;
bots log out after the last session has ended for 60 seconds. SelfBot enabled on
a human player's character still counts as a real session. Independent parties
can run while that player is elsewhere in the world. Adjust
`Playerbots.MinRandomBots` and `Playerbots.MaxRandomBots` for the host's
capacity. A population limit of `0` prevents random-bot parties; updates preserve
custom population settings.

## Optional Dungeon Finder

LFG Progression checks each participant's own earned expansion and retains
native quest, item, achievement and class access requirements. It does not form
autonomous parties, navigate or run encounters. Automatic Dungeon Finder joining
remains disabled through `Playerbots.RandomBotJoinLfg = 0`, keeping automatic
groups on the physical travel path.

Source revisions and integration patches are recorded in
[build provenance](module-versions.md). See [configuration](configuration.md)
for population, scaling and other module defaults.
