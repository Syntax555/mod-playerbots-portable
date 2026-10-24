# Quest diagnostics

Use the bundled core's `.quest status` before reporting a missing historical
quest. It reads quest state and acceptance checks without completing quests,
changing prerequisites or awarding progression. No additional module is needed.

## Run the check

```text
.help quest status
.lookup quest Desperate Prayer
.quest status 5635 Althea
```

Replace `Althea` with the affected character's name. Syntax is
`.quest status <quest-id> [character-name]`; a quest link also works. Without a
name it checks the selected player, falling back to yourself. In the worldserver
console omit the dot and supply the name: `quest status 5635 Althea`.

The shipped command database requires GM level **2** for `quest status` and
allows the console. The core registers permission `RBAC_PERM_COMMAND_QUEST`
(602), but the database's `command.security` overrides that value; local
command overrides can change access. Use an administration account to inspect
the affected ordinary player or bot. Do not change that character's privileges.

Keep the target **online** for acceptance reasons. Offline named characters
return only stored quest status. Status words remain English, including with a
German client:

| Status | Meaning |
| --- | --- |
| `Not Taken` | No current quest state; repeatable quests can show this after an earlier reward. |
| `Incomplete` / `Complete` | In the log, unfinished / objectives complete and awaiting reward. |
| `Failed` / `Rewarded` | Failed / turned in and rewarded. Seasonal reward state follows the current season. |

## Interpret acceptance reasons

For an online target failing `CanTakeQuest`, the command prints
`Quest <id> cannot be taken. Reasons:` followed by failed checks. Messages are
localized; the table uses their English text.

| Output | What to check |
| --- | --- |
| `Quest has already been taken or completed.` | Read the status first; an active or rewarded quest normally cannot be accepted again. |
| `Previous quest in chain not completed.` | Inspect the actual prerequisite and query its ID too. Positive prerequisites normally need `Rewarded`, not just `Complete`; negative prerequisites can require an active quest. The message does not name the prerequisite. |
| `Class requirement not met.` / `Race requirement not met.` | The character's own class/race against the quest masks. Extra SQL conditions can restrict them further. |
| `Player level too low (required: <level>).` / `Player level too high (max: <level>).` | The printed minimum or maximum acceptance level. |
| `Skill requirement not met.` | Required profession/skill and **base** skill points; bonuses do not satisfy this check. The message gives neither skill ID nor points. |
| `Reputation requirement not met.` | Faction and minimum/maximum reputation gates, including the second reputation objective acceptance gate. Maximum bounds are exclusive; more reputation is not always sufficient. Values are not printed. |
| `Condition requirements not met:` | Copy every `Condition not met: type ... value1: ... value2: ... value3: ...` line. Type 8 tests a rewarded quest; type 16 tests a race mask. Negation and alternative groups are not printed. |

Other reasons cover disabled quests, an existing timed quest, exclusive-group,
next-chain, previous-chain and breadcrumb conflicts, daily/weekly/monthly/seasonal
availability, and a full quest log. Exclusive groups can represent alternative
quests, rather than a problem with the player's party.

For missing IDs or values, an administrator can run these **SELECT-only** queries
in the configured world database, replacing `5641` with the affected quest ID:

```sql
SELECT q.ID, q.MinLevel, q.AllowableRaces, q.RequiredFactionId2,
       q.RequiredFactionValue2, a.*
FROM quest_template AS q
LEFT JOIN quest_template_addon AS a ON a.ID = q.ID
WHERE q.ID = 5641;

SELECT SourceEntry, ElseGroup, ConditionTypeOrReference,
       ConditionValue1, ConditionValue2, ConditionValue3, NegativeCondition
FROM conditions
WHERE SourceTypeOrReferenceId = 19 AND SourceGroup = 0 AND SourceEntry = 5641;
```

The addon row includes `AllowableClasses`, `MaxLevel`, `PrevQuestID`, `NextQuestID`,
`ExclusiveGroup`, `RequiredSkillID`, `RequiredSkillPoints` and the
`RequiredMinRep*`/`RequiredMaxRep*` fields. Also inspect incoming `NextQuestID`
relations when tracing a chain. Interpret conditions with their negation and
`ElseGroup` alternatives; a failed row alone is not the whole condition expression.

## Class quests and Individual Progression

Run each command against the same affected character:

| Example | Useful interpretation |
| --- | --- |
| `.quest status 5635 Althea` | Desperate Prayer: human/dwarf priest, minimum level 10. Variants 5634–5639 are alternatives; query the other variant when exclusivity blocks acceptance. |
| `.quest status 5641 Althea` | A Lack of Fear (Fear Ward): priest, minimum level 20. Its native race mask includes draenei, but the restored Vanilla quest adds a dwarf-only condition: type 16, value1 4. A draenei can fail this condition without a native race-requirement message. |
| `.quest status 287 Althea` then `.quest status 291 Althea` | Frostmane Hold (287) does not require 420 in the shipped data; The Reports (291) still requires rewarded 287. |
| `.quest status 10259 Althea` then `.ip get Althea` | Into the Breach must be **rewarded**, with the preceding earned milestone chain satisfied, for the TBC transition. `Complete` alone does not open TBC. |
| `.quest status 66007 Althea` / `.quest status 66008 Althea` / `.quest status 66013 Althea` | Inspect saved tier-7, TBC and Wrath reward markers respectively; these marker quests are not repeatable. |

`.ip get [character-name]` reads the highest saved personal progression marker;
it requires an online target and also accepts selection/self without a name.
The shipped IP command database allows ordinary players (`security = 0`). It
does not validate the whole milestone chain or clamp its answer to the realm
ceiling. Consult the [progression guide](changing-expansions.md) for those limits.

Historical Fear Ward quests are retired by any rewarded personal marker
66008–66018; the other restored priest quests by 66013–66018. These SQL conditions
are visible through `.quest status`, including saved markers above a lowered
realm ceiling. A leader's tier, account unlock or high character level does not
establish the affected character's earned access.

For example, `type 8 value1: 66008 value2: 1 value3: 0` on a historical
Fear Ward rejection comes from a **negated** rewarded-marker condition: the
character already has that marker, rather than needing it to unlock the quest.

The command checks acceptance, not quest-giver spawns, NPC relations, gossip,
travel, objective scripts, trainer purchases or historical spell eligibility.
An active quest can still be turned in under native rules while its historical
spell reward remains gated; see [class quests](class-quests.md). IP access checks
outside native quest conditions are not explained by this command.

An absence of rejection reasons does not guarantee acceptance: the command does
not call `CanAddQuest` for source-item inventory checks, and reports a full log
only inside the `CanTakeQuest` rejection block. A full log alone can therefore go
unreported.

For a report, include the server revision, character race/class/level, quest ID,
NPC entry/location, complete status/condition output, `.ip get` output and realm
mode. Use these read-only checks; quest add/complete/reward/remove and IP setters
are not diagnostic steps.

## Verified sources

The [locked sources](module-versions.md) supply the
[command handler](https://github.com/mod-playerbots/azerothcore-wotlk/blob/3f2969ddb0da42b48b4fca050c02b19163ba1e20/src/server/scripts/Commands/cs_quest.cpp),
[acceptance checks](https://github.com/mod-playerbots/azerothcore-wotlk/blob/3f2969ddb0da42b48b4fca050c02b19163ba1e20/src/server/game/Entities/Player/PlayerQuest.cpp),
[command permissions/help](https://github.com/mod-playerbots/azerothcore-wotlk/blob/3f2969ddb0da42b48b4fca050c02b19163ba1e20/data/sql/base/db_world/command.sql)
and [reason strings](https://github.com/mod-playerbots/azerothcore-wotlk/blob/3f2969ddb0da42b48b4fca050c02b19163ba1e20/data/sql/updates/db_world/2026_02_15_02.sql).
IP provides the [read-only progression handler](https://github.com/ZhengPeiRu21/mod-individual-progression/blob/4933d455d2f611eed50c74c68c78832df4ed37a3/src/cs_individualProgression.cpp)
and its [command defaults](https://github.com/ZhengPeiRu21/mod-individual-progression/blob/4933d455d2f611eed50c74c68c78832df4ed37a3/data/sql/world/base/cs_individualProgression.sql).
Local [historical quest](../patches/mod-individual-progression-historical-class-quests.patch),
[Frostmane Hold](../patches/mod-individual-progression-frostmane-hold.patch) and
[earned milestone](../patches/mod-individual-progression-earned-milestones.patch)
adaptations define the examples and progression limits.
