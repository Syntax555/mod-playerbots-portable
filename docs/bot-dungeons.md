# Bot dungeons

Autonomous parties consist of five nearby random bots: a tank, a healer and
three damage dealers. They use their own earned level, equipment and progression,
walk to the entrance and attempt the instance through ordinary combat and loot.
A human party leader is optional. Controlled companions and existing player
groups are not recruited into these parties.

## Supported instances

| Instance | Faction | Bot levels |
| --- | --- | --- |
| Ragefire Chasm | Horde | 15–18 |
| The Stockade | Alliance | 24–28 |

All members must have Vanilla progression and form a suitable nearby group.
The tank must be near the outdoor entrance, and navigation data must provide a
real route. The coordinator does not summon distant bots or generate equipment,
money, keys, attunements or missing group members. A large bot population does
not guarantee that a suitable party will be available near either entrance.

Other instances and raids retain the Playerbots module's encounter support for
player-led groups. Autonomous routing is limited to the instances listed above;
it does not guarantee completion of every encounter or quest.

## Travel and encounters

The party walks over the native navigation mesh. Each bot must reach the
entrance and pass the ordinary instance-entry handler; the run starts after all
five arrive in the same instance. Entering and leaving uses the physical dungeon
portal. The ordinary Dungeon Finder is not used to teleport the party.

Natural progression rejects unsupported maps, movement shortcuts, artificial
combat recovery and item grants. Missing routes, failed recruitment, wipes or
timeouts stop the attempt. Corpses, loot eligibility and paid character upkeep
remain subject to the core's rules. Encounter tactics and real navigation can
still fail; the module does not turn such failures into completed runs.

## Configuration

Edit `configs/modules/mod_dungeon_clear.conf` with the server stopped:

```ini
DungeonClear.Enable = 1
DungeonClear.AutonomousParties.Enable = 1
DungeonClear.AutonomousParties.MaxConcurrent = 2
```

The simultaneous-party limit accepts 1–8. Set the autonomous-party switch to
`0` to stop automatic recruitment. The strict travel and gameplay guards require
`AiPlayerbot.NaturalProgression = 1` in `configs/modules/playerbots.conf`.

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
