# Earned bot levels and PvP brackets

Random bots start at level 1 with normal starter items. Inviting them to a party,
dungeon, raid or battleground does not raise their level or generate equipment,
gold or supplies. They keep their earned inventory and can acquire upgrades
through ordinary loot, quests, purchases and trades. Natural progression blocks
factory upgrades, refresh grants, legacy level resets and bot XP multipliers.
Individual Progression still enforces each character's expansion gates.

The default reserves roughly 35% of random bots for these earned caps:

| Cap | Share of the bot population |
| --- | --- |
| 19 | 5% |
| 29 | 5% |
| 39 | 5% |
| 49 | 5% |
| 59 | 5% |
| 69 | 5% |
| 79 | 5% |
| Continue individual progression | 65% |

Every assigned bot must earn its cap through normal XP. At its cap, it can still
quest, farm, earn gold and honor, obtain equipment and join eligible activities;
further XP and levels are blocked. This does not use the Wrath XP-off flag or
place these bots in a separate XP-disabled battleground queue.

The level-69 and level-79 groups first have to earn TBC and Wrath access. Their
assignment does not let them cross the level-60/70 progression stops. Appending
these two groups keeps the five lower groups' existing GUID assignments.

Assignment uses a stable character GUID bucket, so the same configuration keeps
the same caps across logouts and restarts. These are approximate shares across
the population, not exact online counts, faction quotas or instant catch-up.
Existing bots already above their assigned cap keep their level and continue
normal progression. No character is downgraded or rerolled.

## Change the distribution

Stop the servers and edit `configs/modules/playerbots.conf`:

```ini
AiPlayerbot.NaturalProgression = 1
AiPlayerbot.EarnedLevelBrackets = "19:5,29:5,39:5,49:5,59:5,69:5,79:5"
AiPlayerbot.LevelBrackets.Enabled = 0
AiPlayerbot.ResetBotLevel.Enabled = 0
```

Each entry is `level:percentage`, with unique levels from 1 to 80 and positive
whole percentages totaling at most 100. The remainder continues normally. For
only level-19 residents, use `"19:10"` to reserve roughly 10%; for a smaller
spread use `"19:2,29:2,39:2,49:2,59:2"`. Use `""` to release every cap. Raising a
cap or removing it allows normal earned XP again; it grants no catch-up XP.

Restart after editing, or use the normal administrator `.reload config` command.
Reload publishes the policy atomically for map threads. Invalid syntax logs an
error and disables earned caps. Changing entry order or percentages changes
some assignments; keep the order stable when you want to retain residents.

For an older installation, install the **complete updated server ZIP**, stop
the servers and run `startup.exe --apply-profiles` once. It backs up configs and
applies the recommended defaults, including this 35% distribution. Make custom
distribution edits afterward; applying profiles again restores bundled defaults.
The launcher alone cannot add these server hooks. Characters and databases are
preserved. No additional bracket module is required: Playerbots already includes
the older bracket/reset feature, whose level rerolls are blocked in natural mode.

## Waiting for battlegrounds

Bots fill real players' Vanilla battleground queues with their actual level,
faction and equipment. They must already qualify for your bracket; a level-1
bot cannot become level 19 just because you queue. There must be enough eligible
queued characters on both factions. Normal minimums from the pinned core remain:
Warsong Gulch 5 per faction, Arathi Basin 8 and Alterac Valley 20. This update
does not reduce those minimums or enable battleground testing mode.

Recruitment and leveling take time. Bots may also be offline, busy, grouped or
unable to reach a task. A population target of 2,500 does not guarantee an
available match in every bracket. Humans and their account alts receive no
automatic earned bracket assignment.

The later residents are available for ordinary eligible grouping, questing and
trading. This profile still enables only the audited Vanilla battlegrounds; it
does not enable TBC/Wrath battlegrounds or arenas.

Progression uses the Wrath client/core with individual expansion content gates.
Talent identities and some encounter AI shortcuts still differ from historical eras;
see [the audit](vanilla-config-audit.md) for the broader limits.
