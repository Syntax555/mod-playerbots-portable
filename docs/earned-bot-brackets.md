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

Bots fill real players' named queues with their actual level, earned era, faction
and equipment. A level-1 bot cannot become level 19 just because you queue, and
an assigned level-69/79 cap does not unlock TBC/Wrath. Queue eligibility needs
both the map's normal level requirements and the character's earned expansion.

| Battleground | IP level brackets within the level-80 realm | Required earned tier | Minimum per faction |
| --- | --- | --- | ---: |
| Warsong Gulch | 10–19, 20–29, 30–39, 40–49, 50–59, 60, 61–69, 70, 71–79, 80 | 0+ | 5 |
| Arathi Basin | 20–29, 30–39, 40–49, 50–59, 60, 61–69, 70, 71–79, 80 | 0+ | 8 |
| Alterac Valley | 51–60, 61–70, 71–79, 80 | 0+ | 20 |
| Eye of the Storm | 61–69, 70, 71–79, 80 | 8+ | 8 |
| Isle of Conquest | 71–79, 80 | 13+ | 20 |

The pinned IP/core level data determines the actual bracket; these settings do
not fabricate missing brackets or lower map requirements. Matchmaking also
separates Vanilla (tiers 0–7), TBC (8–12) and Wrath (13+) within each bracket.
A Vanilla level-60 character and a TBC level-60 character enter separate pools;
so do TBC and Wrath characters at level 70. Premades and group queues must have
one earned era, and every member must independently qualify. Existing matches
retain their era for invitations and refills. Accepting an invitation rechecks
the actual selected map and match era, so an expansion change while queued
cannot move a character into the departing era's match.

Preserved older characters above their earned era's level ceiling (60 in Vanilla,
70 in TBC) must earn the appropriate milestones before queueing. The update
keeps their levels and possessions; it does not downgrade them to fit a match.

The portable defaults are:

```ini
AiPlayerbot.EarnedEraBattlegrounds = 1
AiPlayerbot.VanillaBattlegroundsOnly = 0
AiPlayerbot.RandomBotJoinBG = 1
AiPlayerbot.RandomBotAutoJoinBG = 0
```

Bots fill a real player's eligible pool rather than seed autonomous all-bot
matches. Normal faction/team minimums remain in place; battleground testing mode
stays disabled. Recruitment and leveling take time. Bots may be offline, busy,
grouped or unable to reach a task. A population target of 2,500 does not guarantee
an available match in every era and bracket. Humans and account alts receive no
automatic earned-cap assignment.

Match rules follow the pool's earned era:

| Rule | Vanilla | TBC | Wrath |
| --- | --- | --- | --- |
| Arathi Basin victory points | 2,000 | 2,000 | 1,600 |
| Eye of the Storm victory points | Unavailable | 2,000 | 1,600 |
| Alterac Valley starting reinforcements | No countdown | 600 | 600 |
| Warsong Gulch time limit | None | None | Native 25 minutes |
| Warsong Focused/Brutal Assault penalties | Disabled | Native penalties | Native penalties |

The Wrath time limit is the pinned core's 25-minute rule. Vanilla omits the
later Focused/Brutal Assault flag-carry penalties; TBC/Wrath retain native
penalties, whose exact original TBC values are not retrofitted. These are selected
era rules, not a recreation of every historical patch version.

These rules are fixed before players enter; another era's queued players cannot
change them during a match. Marks of Honor continue through Vanilla/TBC according
to IP's existing earned-era reward rules. The natural progression patch supplies
no free equipment, levels, consumables or forced resurrection for PvP. Bots use
normal invitations, transport and spirit-guide resurrection waves.

Humans unlock Strand of the Ancients and random battleground queues with earned
Wrath, and arena skirmishes with earned TBC, while retaining normal level/team
requirements. Native rated arenas require level 80, so rated participation needs
earned Wrath; TBC characters capped at 70 can use skirmishes only. TBC arena
selection uses Nagrand, Blade's Edge and Ruins of Lordaeron; Wrath also adds
Dalaran Sewers and Ring of Valor. Bots do not fill those queues. The pinned AI
has no Strand tactics, and its arena team gathering uses teleport shortcuts, so
bot arena teams remain disabled. These human activities need ordinary
participants.

Install the complete updated server ZIP and run `startup.exe --apply-profiles`
with the servers stopped to replace an older Vanilla-only queue configuration.
This backs up changed configs and preserves characters. Simply replacing the
launcher cannot add the server matchmaking hooks.

Progression still uses the Wrath client/core. Historical human and bot talents
follow earned eras, but not every world rule or encounter tactic is historical.
Source and fixture checks do not establish perfect live battleground tactics;
see [the audit](vanilla-config-audit.md) for the broader limits.
