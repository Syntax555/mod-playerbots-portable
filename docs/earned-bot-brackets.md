# Earned bot levels and PvP brackets

Random bots start at level 1 with normal starter items. They earn XP, equipment,
gold, supplies and expansion access through play. Joining a party or queue does
not raise their level or generate resources.

## Resident level caps

The default reserves about 35% of random bots for earned level caps:

| Cap | Share of the population |
| --- | ---: |
| 19 | 5% |
| 29 | 5% |
| 39 | 5% |
| 49 | 5% |
| 59 | 5% |
| 69 | 5% |
| 79 | 5% |
| Continue individual progression | 65% |

Assigned bots must earn their cap through normal XP. At the cap they can still
quest, farm, earn gold and honor, improve equipment and join eligible activities.
Further XP is blocked without the Wrath XP-off flag or a separate XP-disabled
battleground queue. Level-69/79 residents must earn TBC/Wrath before crossing
level 60/70.

Assignment uses a stable character GUID bucket and persists across restarts.
These are approximate population shares, not exact online counts or faction
quotas. Existing bots above their assigned cap keep their levels and continue
progression. Human characters and account alts receive no automatic caps.

## Change the distribution

Edit `configs/modules/playerbots.conf` with the servers stopped:

```ini
AiPlayerbot.NaturalProgression = 1
AiPlayerbot.EarnedLevelBrackets = "19:5,29:5,39:5,49:5,59:5,69:5,79:5"
AiPlayerbot.LevelBrackets.Enabled = 0
AiPlayerbot.ResetBotLevel.Enabled = 0
```

Each entry is `level:percentage`: unique levels from 1 to 80 and positive whole
percentages totaling at most 100. The remainder progresses normally. For example,
`"19:10"` reserves about 10% at level 19; `""` releases all caps. Raising or
removing a cap allows earned XP again without granting catch-up XP.

Restart or use the administrator `.reload config` command. Invalid syntax logs
an error and disables earned caps. Changing order or percentages can reassign
some bots; retain the order when preserving residents.

`startup.exe --apply-profiles` backs up configs and restores the bundled
distribution. Apply custom edits afterward. The complete server package is
required for these hooks; replacing the launcher alone is insufficient.

## Waiting for battlegrounds

Bots fill real players' named queues with their actual level, earned era,
faction and equipment. Both ordinary map requirements and earned expansion
access apply.

| Battleground | Level brackets | Required tier | Minimum per faction |
| --- | --- | --- | ---: |
| Warsong Gulch | 10–19, 20–29, 30–39, 40–49, 50–59, 60, 61–69, 70, 71–79, 80 | 0+ | 5 |
| Arathi Basin | 20–29, 30–39, 40–49, 50–59, 60, 61–69, 70, 71–79, 80 | 0+ | 8 |
| Alterac Valley | 51–60, 61–70, 71–79, 80 | 0+ | 20 |
| Eye of the Storm | 61–69, 70, 71–79, 80 | 8+ | 8 |
| Isle of Conquest | 71–79, 80 | 13+ | 20 |

The pinned IP/core data supplies these brackets. Matchmaking separates Vanilla
(tiers 0–7), TBC (8–12) and Wrath (13+) within each bracket, including overlapping
level-60/70 characters. Queued groups must share one earned era and every member
must qualify. Invitations and refills retain the instance's era; invitation
acceptance checks the actual map and era again.

Preserved characters above their earned ceiling, level 60 in Vanilla or 70 in
TBC, must earn the needed expansion before queueing. Their levels are retained.

The defaults in `configs/modules/playerbots.conf` are:

```ini
AiPlayerbot.EarnedEraBattlegrounds = 1
AiPlayerbot.VanillaBattlegroundsOnly = 0
AiPlayerbot.RandomBotJoinBG = 1
AiPlayerbot.RandomBotAutoJoinBG = 0
```

Bots fill a real player's eligible queue; autonomous all-bot matches and
battleground testing mode are disabled. Native faction and team minimums apply.
Recruitment and leveling take time, and bots can be offline or busy. A population
target of 2,500 does not guarantee a match in every era and bracket.

## Match rules

| Rule | Vanilla | TBC | Wrath |
| --- | --- | --- | --- |
| Arathi Basin victory points | 2,000 | 2,000 | 1,600 |
| Eye of the Storm victory points | Unavailable | 2,000 | 1,600 |
| Alterac Valley starting reinforcements | No countdown | 600 | 600 |
| Warsong Gulch time limit | None | None | Native 25 minutes |
| Warsong Focused/Brutal Assault penalties | Disabled | Native penalties | Native penalties |

Rules are fixed before players enter and remain unchanged through refills.
Marks of Honor follow IP's Vanilla/TBC reward policy. Bots use normal invitation
transport and spirit-guide resurrection waves, without free PvP resources.

These are selected era rules. Original TBC assault-penalty values are not
retrofitted. Eye's server victory threshold changes, but the Wrath client's
static scoreboard maximum is not a historical TBC display.

## Human queues and AI limits

Humans unlock Strand of the Ancients and random battlegrounds with earned Wrath,
and arena skirmishes with earned TBC. Native rated arenas require level 80 and
earned Wrath; TBC characters can use skirmishes only. TBC arenas select Nagrand,
Blade's Edge and Ruins of Lordaeron. Wrath also adds Dalaran Sewers and Ring of
Valor. Ordinary team and rating requirements remain in force.

Bots do not fill Strand, random battlegrounds or arenas. The pinned AI lacks
Strand tactics, and its arena gathering uses teleport shortcuts, so those bot
paths are disabled. These human queues need ordinary participants. Other
battleground tactics and pathfinding also depend on upstream AI; see the
[configuration reference](vanilla-config-audit.md#supported-scope).
