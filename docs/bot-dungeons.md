# Bot dungeons and raids

Dungeon Clear coordinates routes and objectives; Playerbots and its integrated
Raid Clear provide combat tactics. Under natural progression, bots walk real
routes, use ordinary interactions and fight and loot with their own earned
levels, equipment, keys and progression. Teleports, grants, artificial combat
recovery and unaudited event shortcuts are refused.

## Autonomous parties

Five nearby random bots of one faction form a tank, healer and three damage
dealers. Controlled altbots, SelfBot characters and existing player groups are
not recruited. All members need the dungeon's own earned era, level band and
native entry eligibility; a leader or another character cannot unlock it.
Vanilla, TBC and Wrath level caps are 60, 70 and 80.

The tank must be near the outdoor entrance and navigation must provide a real
route. Bots walk to the physical portal, and the run starts only when all five
enter the same instance normally. The coordinator supplies no distant members,
equipment, keys, attunements, gold or summons. A large population alone does not
guarantee a suitable nearby party. Autonomous parties enter normal dungeons,
not heroics or raids.

### Dungeons

World data supplies entrances, exits and faction restrictions. Level bands use
Finder recommendations extended by `LevelSpread`, within native entry ranges
and the earned-era cap. A dungeon's era comes from its record, including TBC or
Wrath entrances in Kalimdor. Capital portals admit that capital's faction.

Configured ids are candidates. Required objectives and conditional controllers
that own pulling or movement must pass the event audit, even if upstream marks
them optional. Keys, special locks, unaudited item acquisition and unsupported
controllers can refuse a map. The startup log reports each configured route's
acceptance or refusal for the installed world data.

### Vanilla routes

| Dungeon | Finder id | Bot levels | Autonomous parties |
| --- | --- | --- | --- |
| Ragefire Chasm | 4 | 15–19 | Horde only |
| Wailing Caverns | 1 | 17–23 | Enabled with checked ramp paths and the native Disciple escort |
| The Deadmines | 6 | 17–23 | Enabled with the ordinary gunpowder and cannon actions |
| Shadowfang Keep | 8 | 18–24 | Enabled |
| Blackfathom Deeps | 10 | 21–27 | Not enabled: the route crosses disconnected navigation mesh |
| The Stockade | 12 | 22–28 | Alliance only |
| Razorfen Kraul | 16 | 24–30 | Enabled |
| Gnomeregan | 14 | 25–31 | Enabled |
| Scarlet Monastery: Graveyard, Library, Armory, Cathedral | 18, 165, 163, 164 | 29–35, 32–38, 34–40, 37–43 | Enabled |
| Razorfen Downs | 20 | 34–40 | Enabled |
| Uldaman | 22 | 37–43 | Not enabled: Ironaya's keystone requires the Staff of Prehistoria |
| Zul'Farrak | 24 | 43–49 | Not enabled: the Troll Cage requires the Executioner's Key |
| Maraudon: Purple, Orange, Pristine Waters | 272, 26, 273 | 41–47, 43–49, 45–51 | Enabled |
| Sunken Temple | 28 | 47–53 | Enabled |
| Blackrock Depths: Prison, Upper City | 30, 276 | 49–55, 53–59 | Not enabled: the Shadowforge Lock requires a key |
| Lower Blackrock Spire | 32 | 57–60 | Enabled |
| Dire Maul: East, West, North | 34, 36, 38 | 55–60, 58–60, 60 | Enabled |
| Scholomance | 2 | 60 | Enabled |
| Stratholme: Main Gate, Service Entrance | 40, 274 | 60 | Not enabled: required ziggurat and movement controllers are unaudited |


Blackfathom Deeps has disconnected mesh sections. Its authored party jumps,
swimming chains, pool exits and fall recovery have no audited ordinary route.
Stratholme's ziggurats and trap-alley controllers also remain unaudited. Both
maps refuse autonomous recruitment. Player-led groups can enter normally, but
bots refuse those controllers and may need ordinary player assistance.

The following handlers use ordinary actions; their presence does not establish
a complete verified clear:

| Instance | Supported action | Material limit |
| --- | --- | --- |
| Wailing Caverns | Checked ramp routes and native Disciple of Naralex escort after the four Fanglords | Every member needs a complete safe path. Completion needs Mutanus kill credit and the native departure marker; missing/reset NPCs or the 15-minute attempt limit block the objective. |
| The Deadmines | Open the native gunpowder chest, loot owned powder and use it on the cannon | Native item, lock and range checks apply. Missing powder, restricted loot, bags above the 80% safeguard or missing paths can stall; another member's powder is not borrowed. |
| Uldaman | Use the Keepers and Archaedas altars through the ordinary object action | The native five-second channel, group ownership, interruptions and encounter reset apply. Ironaya still needs the group's own Staff of Prehistoria; autonomous acquisition is unaudited. |
| Zul'Farrak | Walk into Zum'rah's area and submit the normal area trigger | Paused/cancelled clears cannot activate it. The Troll Cage still needs the Executioner's Key, and Gahz'rilla's special-lock gong is unaudited. |
| Blackrock Depths | Gather everyone inside Ring of Law and submit the ordinary area trigger | Human members enter themselves. Completion waits for native encounter state, including Grimstone's final walk. Wipe cooldown and missing-member/path guards remain. |

Blackrock Depths' Shadowforge Lock still needs its own key. Rocknot's ale-run
hooks remain refused under natural progression, including their fallback
quest-credit calls. A player can buy the ale and complete the normal turn-ins;
bots do not manufacture missing mugs or count an unpaid turn-in. Karazhan's
conditional library-pit rescue also remains refused.

Automated fixtures cover selected native data contracts, interactions, routes,
interruptions and retries. Complete runs, group spacing, combat and recovery
still need in-game validation. In Wailing Caverns, a long pause can miss the
short departure-marker window and leave the objective blocked.

### TBC and Wrath routes

The profile lists all 16 normal TBC and 16 normal Wrath Finder entries. Heroic,
raid, random-queue and holiday entries are excluded. The event audit admits
these candidates; actual entrances, locks, world data and navigation can further
restrict them:

| Era | Candidate routes | Refused event routes |
| --- | --- | --- |
| TBC | Hellfire Ramparts, Blood Furnace, Mana-Tombs, Auchenai Crypts, Sethekk Halls, Shadow Labyrinth, Botanica, Magisters' Terrace | Shattered Halls, Slave Pens, Underbog, Steamvault, Escape from Durnholde, Black Morass, Mechanar, Arcatraz |
| Wrath | Utgarde Keep, Ahn'kahet, Nexus, Forge of Souls | Utgarde Pinnacle, Azjol-Nerub, Oculus, Halls of Lightning, Halls of Stone, Culling of Stratholme, Drak'Tharon Keep, Gundrak, Violet Hold, Trial of the Champion, Pit of Saron, Halls of Reflection |


Refused maps need unaudited event, escort, vehicle, item or movement handling.
For example, Steamvault's access panel requires a special opening lock;
Drak'Tharon Keep needs a Novos controller; Trial of the Champion needs its arena
controller. They remain available to player-led groups, with earned-play guards
active. Magisters' Terrace requires tier 12 and Forge of Souls tier 16 under
Individual Progression. Every member also keeps native attunements, lockouts
and instance limits.

## Player-led clears

With a real player in the group, playing normally or as SelfBot, a tank bot can
lead a clear after the party enters through the normal portal checks. Use
`.dc on` or `dc on` in party chat to start and `.dc off` to stop. `.dc pause`
pauses/resumes, `.dc status` reports progress and `.dc bosses` lists objectives.
The tank must be under bot control; controlled characters keep their own
progression and equipment.

The optional [DungeonClear addon](addons.md#optional-upstream-addons) opens its
panel with `/dc`; install it separately. If a start appears to do nothing,
`.dc on` exposes server refusals the addon may omit.

When a member dies during a clear, a living Priest, Paladin, Shaman or Druid
in the party raises them with their own resurrection spell after the fight;
bots stay down until then, and real players accept or decline the offer
themselves. If nobody left can resurrect, the dead release and walk back from
the graveyard while the tank waits for them. A wipe, or the tank's death with
nobody to raise it, ends the clear. A SelfBot's ghost is walked back by its
player.

A required unsupported event stalls for ordinary player interaction; an optional
one may be skipped. `.dc skip` advances the objective list without opening
locked objects or awarding native encounter credit.

## Raids

Raid Clear supplies Onyxia's Lair, Molten Core, Blackwing Lair, Zul'Gurub and
both Ahn'Qiraj raids with kill order, tank roles, positioning and encounter
actions. It works alongside Playerbots' registered strategies, enabled by
`Playerbots.ApplyInstanceStrategies = 1`:

| Era | Registered Playerbots raid tactics |
| --- | --- |
| Vanilla | Onyxia's Lair, Molten Core, Blackwing Lair, Ruins of Ahn'Qiraj |
| TBC | Karazhan, Gruul's Lair, Magtheridon's Lair, Serpentshrine Cavern, Tempest Keep, Hyjal Summit, Black Temple, Zul'Aman |
| Wrath | Onyxia's Lair, Naxxramas, Obsidian Sanctum, Eye of Eternity, Vault of Archavon, Ulduar, Icecrown Citadel, Ruby Sanctum |


A registration does not establish a complete verified raid clear. Restored
Vanilla Naxxramas is unverified; Sunwell and Trial of the Crusader have no
dedicated Playerbots registration in this pin. Autonomous parties do not raid,
and raid difficulty does not scale with the number of players or bots.

Native attunements and each character's progression remain required. Only an
equipped Onyxia Scale Cloak protects against Shadow Flame; only rogues knowing
Disarm Trap disarm Suppression Devices. Hunters earn Tranquilizing Shot, and
Molten Core runes need Aqual Quintessence; bots do not douse them. Natural
progression does not cancel a bot's crowd control artificially when a formerly
mind-controlled target returns to the raid.

Onyxia's map 249 tactics cover Deep Breath spell positions, Fireball spacing,
tank positioning and threat in the restored level-60 encounter. Whelp targeting
includes native and restored Vanilla whelps and skips evading targets. A full
Onyxia clear remains unverified; each character still needs its native entry
requirements, including the Drakefire Amulet where required. See the
[gameplay validation checklist](todo.md#gameplay-validation).

## Travel and encounters

Parties share a route calculated over the native navigation mesh. Each bot's
short movement sections are checked from its current position; water sections
use its swim speed. After interruptions a bot rejoins a reachable route point.
Missing mesh, unsafe sections or a missing member stop progress.

If an entrance refuses a member, the attempt stops and that bot is excluded from
that dungeon for two hours or until its level/progression changes. Failed
recruitment, wipes, timeouts and objectives stalled for five minutes stop an
autonomous attempt. Ordinary corpse, loot and paid-upkeep rules remain in force.
Encounter or navigation failures are not converted into completed runs.

Natural progression blocks provisioned `.dc test` starts/plans and `.dc lab run`
or `.dc lab batch`, including background party provisioning. Lab status and stop
remain available.

## Configuration

Edit `configs/modules/mod_dungeon_clear.conf` with the server stopped.

| Setting | Shipped default | Purpose |
| --- | --- | --- |
| `DungeonClear.Enable` | `1` | Module master switch; restart required |
| `DungeonClear.AutonomousParties.Enable` | `1` | Recruit nearby random-bot parties |
| `DungeonClear.AutonomousParties.MaxConcurrent` | `2` | Concurrent parties, range 1–8 |
| `DungeonClear.AutonomousParties.LevelSpread` | `3` | Extend recommended level bands, range 0–10 |
| `DungeonClear.AutonomousParties.Dungeons` | Normal Vanilla, TBC and Wrath candidate ids | Remove an id to exclude a route; the event audit still applies |

The [native configuration template](https://github.com/Syntax555/mod-dungeon-clear/blob/master/conf/mod_dungeon_clear.conf.dist)
lists all settings. Native autonomy defaults to off with ids `4,12`; the
portable profile enables the broader candidate list. Natural guards require
`Playerbots.NaturalProgression = 1` in `configs/modules/playerbots.conf` and
Individual Progression's strict default earned chain; custom or disabled
progression does not substitute levels or account progress.

The portable profile disables `DungeonClear.DungeonQueueFill.Enable`,
`BgQueueFill.Enable`, `StrandedRecovery`, `UnreachableCombatPurgeSecs` and
`SpectateEnable`, and enables the party resurrection `PostCombatRez`.
`LootMinQuality = 0` keeps ordinary corpse loot. Updates preserve custom route
lists, autonomy switches and limits; unchanged managed defaults follow the
current profile.

Raid Clear settings live in `configs/modules/playerbots.conf`:

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


Random bots run while a real session is connected. Login begins after 30
seconds; they log out 60 seconds after the last real session ends. A player's
SelfBot session still counts. Adjust population to the host using the
[population settings](configuration.md#bots-and-population); a population of
zero prevents autonomous parties.

## Optional Dungeon Finder

The Finder is disabled with `DungeonFinder.OptionsMask = 0` in
`configs/worldserver.conf`; automatic bot queues are disabled with
`Playerbots.RandomBotJoinLfg = 0` in `configs/modules/playerbots.conf`.
Autonomous Dungeon Clear parties use physical travel independently of it.

LFG Progression is always compiled and enabled. If you opt into the Finder,
keep `LfgProgression.Enable = 1` in `configs/modules/mod_lfg_progression.conf`.
Each participant, including invited companions and random bots, retains its own
earned era and native level, class, quest, item, achievement, attunement and
instance locks. Each join refreshes all online members' locks. A later-era
random selection is remapped to the group's lowest earned era. Missing Death
Knight starting-chain quests are never granted.

Use `.lfgprogress` to inspect online group members' effective eras and expansion
requirements. TBC begins at tier 8 and Wrath at tier 13 in the shipped chain;
the realm ceiling still applies. Queue messages explain era refusals and
remapping, while the client retains its generic required-quest tooltip.
LFG Progression does not navigate or run encounters; complete queue and chat
behavior still needs in-game validation.

Keep `IndividualProgression.DisableRDF = 0` in
`configs/modules/individualProgression.conf`: `1` forces specific queues (mask
`4`) instead of disabling the Finder. Updates preserve deliberate Finder and
LFG customizations, including installations without a saved profile baseline.
See [configuration](configuration.md) and [source versions](module-versions.md).
