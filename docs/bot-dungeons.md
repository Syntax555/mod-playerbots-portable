# Bot dungeons and raids

Bots clear instances with Dungeon Clear, Raid Clear and Playerbots' own
encounter tactics. Under natural progression they act only as ordinary players
can: they walk real routes, open objects without a lock or with their own key,
talk to NPCs, fight and loot. They never receive keys, quest items, teleports,
resurrections or encounter shortcuts.

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
and navigation data must provide a real route. The coordinator does not summon distant bots or generate
equipment, money, keys, attunements or missing group members. A large bot
population does not guarantee that a suitable party forms near an entrance.

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
| Wailing Caverns | 1 | 17–23 | Not enabled: off-mesh drops and the Disciple escort |
| The Deadmines | 6 | 17–23 | Not enabled: the Defias Cannon uses a scripted item |
| Shadowfang Keep | 8 | 18–24 | Enabled |
| Blackfathom Deeps | 10 | 21–27 | Enabled |
| The Stockade | 12 | 22–28 | Alliance only |
| Razorfen Kraul | 16 | 24–30 | Enabled |
| Gnomeregan | 14 | 25–31 | Enabled |
| Scarlet Monastery: Graveyard, Library, Armory, Cathedral | 18, 165, 163, 164 | 29–35, 32–38, 34–40, 37–43 | Enabled |
| Razorfen Downs | 20 | 34–40 | Enabled |
| Uldaman | 22 | 37–43 | Not enabled: the altars are scripted spell casts |
| Zul'Farrak | 24 | 43–49 | Not enabled: Witch Doctor Zum'rah is woken by a script |
| Maraudon: Purple, Orange, Pristine Waters | 272, 26, 273 | 41–47, 43–49, 45–51 | Enabled |
| Sunken Temple | 28 | 47–53 | Enabled |
| Blackrock Depths: Prison, Upper City | 30, 276 | 49–55, 53–59 | Not enabled: the Ring of Law is a scripted event |
| Lower Blackrock Spire | 32 | 57–60 | Enabled |
| Dire Maul: East, West, North | 34, 36, 38 | 55–60, 58–60, 60 | Enabled |
| Scholomance | 2 | 60 | Enabled |
| Stratholme: Main Gate, Service Entrance | 40, 274 | 60 | Enabled |

A dungeon is enabled when its required Dungeon Clear objectives and conditional
controllers for pulling or movement use audited ordinary actions. Unsupported
controllers cannot be treated as dispensable simply because upstream marks
them optional. Events requiring scripted shortcuts, quest items or locked
objects without a normal click prevent automatic recruitment for that map.

### TBC and Wrath routes

The default configuration also lists all 16 normal TBC and 16 normal Wrath
Dungeon Finder entries. Heroic, raid, random-queue and holiday entries are
excluded. The event audit admits candidates; actual world data, entrances,
object locks and navigation can further restrict them.

| Era | Candidate routes | Refused event routes |
| --- | --- | --- |
| TBC | Hellfire Ramparts, Blood Furnace, Steamvault, Mana-Tombs, Auchenai Crypts, Sethekk Halls, Shadow Labyrinth, Botanica, Magisters' Terrace | Shattered Halls, Slave Pens, Underbog, Escape from Durnholde, Black Morass, Mechanar, Arcatraz |
| Wrath | Utgarde Keep, Ahn'kahet, Nexus, Forge of Souls | Utgarde Pinnacle, Azjol-Nerub, Oculus, Halls of Lightning, Halls of Stone, Culling of Stratholme, Drak'Tharon Keep, Gundrak, Violet Hold, Trial of the Champion, Pit of Saron, Halls of Reflection |

Refused routes require event, escort, vehicle, item or movement handling that
the earned integration cannot perform through ordinary actions. For example,
Trial of the Champion needs its arena controller, and Drak'Tharon Keep needs
an unaudited Novos controller. They remain available to player-led groups.

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

Raid Clear adds boss and trash mechanics for Molten Core, Blackwing Lair and
Zul'Gurub: kill order, main and off-tank roles, spacing and positioning against
the bosses' abilities. They apply on these maps whether you lead the raid or a
player-led clear walks it from boss to boss, alongside Playerbots' own raid
strategies. Autonomous parties do not enter raids.

Under natural progression only an equipped Onyxia Scale Cloak protects against
Shadow Flame, and Suppression Devices are disarmed only by rogues casting
Disarm Trap. Raid entry keeps native attunements and Individual Progression
requirements. Molten Core's runes must be doused with Aqual Quintessence; bots
do not douse them.
AutoBalance scales raid difficulty to the number of players and bots present.

## Travel and encounters

The party walks over the native navigation mesh. Each bot must reach the
entrance and pass the ordinary instance-entry handler; the run starts after all
five arrive in the same instance. Entering and leaving uses the physical dungeon
portal. The ordinary Dungeon Finder is not used to teleport the party.

Natural progression rejects movement shortcuts, artificial combat recovery and
item grants. Missing routes, failed recruitment, wipes, timeouts and objectives
that stall for five minutes stop an autonomous attempt. Corpses, loot
eligibility and paid character upkeep remain subject to the core's rules.
Encounter tactics and real navigation can still fail; the module does not turn
such failures into completed runs.

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
`AiPlayerbot.NaturalProgression = 1` in `configs/modules/playerbots.conf`.
Automatic parties also require Individual Progression's strict default earned
chain. A realm with a disabled or custom progression chain does not use level
or account progress as a substitute.
Raid Clear's switches are in `configs/modules/mod_raid_clear.conf`.

Updates extend an unchanged managed dungeon list and preserve custom lists,
autonomy switches and party limits. For an existing custom list, add the desired
normal Dungeon Finder ids explicitly; an entry must still pass the event audit.

Random bots run while at least one real player session is connected through
`AiPlayerbot.DisabledWithoutRealPlayer = 1`. Login begins after a 30-second delay;
bots log out after the last session has ended for 60 seconds. SelfBot enabled on
a human player's character still counts as a real session. Independent parties
can run while that player is elsewhere in the world. Adjust
`AiPlayerbot.MinRandomBots` and `AiPlayerbot.MaxRandomBots` for the host's
capacity. A population limit of `0` prevents random-bot parties; updates preserve
custom population settings.

## Optional Dungeon Finder

LFG Progression checks each participant's own earned expansion and retains
native quest, item, achievement and class access requirements. It does not form
autonomous parties, navigate or run encounters. Automatic Dungeon Finder joining
remains disabled through `AiPlayerbot.RandomBotJoinLfg = 0`, keeping automatic
groups on the physical travel path.

Source revisions and integration patches are recorded in
[build provenance](module-versions.md). See [configuration](vanilla-config-audit.md)
for population, scaling and other module defaults.
