# Historical class quests

Class quests use each character's own earned progression. Selected historical
priest quests retain their original teacher relations, race and level conditions
and reward a matching historical spell. Players and bots follow the same access
rules.

## Priest training

| Family | Historical race |
| --- | --- |
| Desperate Prayer | Human and dwarf |
| Fear Ward | Dwarf in Vanilla; ordinary all-race training in TBC |
| Starshards | Night elf |
| Elune's Grace | Night elf |
| Touch of Weakness | Undead; also blood elf in TBC |
| Hex of Weakness | Troll |
| Shadowguard | Troll |
| Feedback | Human |
| Devouring Plague | Undead |

Desperate Prayer begins at level 10 for human and dwarf priests. Eligible
teachers offer the original quest variants, and the final teacher grants rank
1. Later ranks require ordinary paid training. The Vanilla spell uses its
historical rank levels and cooldown rather than the Wrath talent's values.

Historical quest rewards and removed spell ranks use separate spell records.
Vanilla and TBC mechanics follow the corresponding source data; native Wrath
records remain in place for Wrath progression. The core also checks eligibility
when a quest is accepted or rewarded, and when its spell is learned or cast.
Another party member's progression does not unlock these rewards.

The client patch retains the server's native Wrath mana costs for Desperate
Prayer and Devouring Plague. A dataset contract identifies the twelve affected
records and permits only `ManaCost` and `ManaCostPct` restoration from the
checksum-verified Wrath source. The client package records each change in
`SOURCE_MANIFEST.json`.

TBC also includes historical racial spells learned directly through paid
training, without a quest prerequisite:

| Family | Race | First level |
| --- | --- | --- |
| Chastise | Dwarf and draenei | 20 |
| Symbol of Hope | Draenei | 10 |
| Consume Magic | Blood elf | 20 |
| Touch of Weakness | Blood elf | 10 |

Consume Magic requires consuming an eligible priest aura. TBC blood elf training
does not require completing an undead quest. These trainer purchases retain
ordinary range, race, progression, level and money requirements.

Logging in can restore a missing rank-1 root when the character has already
earned the matching quest reward. It does not complete missing quests, grant
higher ranks or bypass trainer costs.

## Client installation

Install the release's matching EraTalents addon and `Data/patch-V.mpq` with WoW
fully closed. The MPQ contains the restored spell records and German and English
text, and must match the server's generation. See [EraTalents](era-talents.md)
for installation and generation checks.

Questie and guide addons maintain their own quest databases. Their markers can
omit restored quests even when the server offers them. The NPC quest list and
server-side eligibility determine availability; see [client addons](addons.md).

## Source and scope

Quest relations, ranks and mechanics use pinned CMaNGOS Classic and TBC sources.
[Build provenance](module-versions.md), [versions.lock.json](../versions.lock.json)
and packaged license notices identify the exact source revisions and adaptations.
SQL updates run through the ordinary database updater.

This integration restores the listed priest families. Other classes retain the
core and Individual Progression quest support. It does not provide three complete
historical quest databases or certify every class quest and scripted objective.
