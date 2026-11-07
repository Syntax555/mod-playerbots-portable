# Class quest coverage and source comparison

The server separates native quest content from the bot actions needed to play
it. A restored questgiver or reward does not establish that a bot can use its
items, finish its event or reach its destination. Each character still needs
its own race, class, level and earned-era eligibility.

## Comparison with Wrath of the Vanilla v2

[Hextv/wrath-of-the-vanilla-v2](https://github.com/Hextv/wrath-of-the-vanilla-v2/tree/04c09ee2a8cb0d3aa651f4bc17d5feaa984c633e)
restores selected Classic data on a Wrath server. Its class-quest checklist
marks Shaman, Warlock and Druid complete; the other six Classic classes remain
unchecked. Its C++ scripts cover encounters, and supply no Playerbots class
quest runner.

| Class | Relevant comparison | Bot coverage and remaining work |
| --- | --- | --- |
| Warrior | Startup quest flag changes already exist in Individual Progression. No Affray or stance bot sequence is supplied. | The shared class quest action covers all six Defensive Stance chains and The Affray, including the Ulag, Bartleby, ravager cage and grate events, and 29 other solo class quests. Complete live runs remain open. |
| Paladin | Tome of Nobility and class-mount quest relations are already restored. | The shared action covers the four Redemption chains, both Sense Undead chains, both warhorses and 5 other solo class quests. Quest-taught Sense Undead uses personal-era gates. The level-60 Charger chains and complete live runs remain open. |
| Hunter | The project supplies no taming-lesson bot actions. | Six racial lesson chains and first-pet acquisition have dedicated actions; the shared action covers 25 other solo class quests. Historical pet ability acquisition remains separate. |
| Rogue | Matching startup letter and scroll flags already exist. | The shared action covers 30 solo class quests, including Klaven's Tower. Pickpocketing, the Horde poison chain's scripted salute and disguise events and Ravenholdt remain player content. |
| Priest | Trainer edits do not replace the existing historical racial quest and spell integration. | Restored racial rewards and paid ranks have personal-era gates. The shared action takes bots through the nine restored families and 21 other solo class quests, including the robe quests' healing sequences; complete live runs remain open. |
| Shaman | Earth quest flag changes and Water quest text already exist. | Horde and Draenei totem actions handle owned quest items, wells, spirits and ritual objects; the shared action covers 5 other solo class quests. Group and raid equipment chains and complete live runs remain open. |
| Mage | Matching startup quest flags and trainer handling already exist. | The shared action covers 29 solo class quests, including the flask fills at their spell focus and Magecraft. The containment coffers, Uldaman and Fragmented Magic remain player content. |
| Warlock | Imp and Felsteed quest relations, orb prerequisites and inspected quest starters already exist. | The 53-step demon action supplies bot handling absent from the reference project, including the Felsteed, the blood elf Voidstone and the solo Infernal chain; the shared action covers 9 other solo class quests. The Dreadsteed and Doomguard need dungeons or a group and remain player content. |
| Druid | Existing native quest scripts and trainer restoration supply quest content. | The 32-variant Bear, Aquatic Form and Cure Poison action uses native spirit dialogues, items, loot and material purchases; the shared action covers 4 other solo class quests. Complete live runs, the Toxic Test equipment chain and Swift Flight remain open. |

The inspected Shaman changes include Earth quests 1516–1518 and 1520–1521,
and Water quests 96, 100, 220 and 1530. Warlock comparisons include Imp quests
1470, 1485, 1598 and 1599, Felsteed variants 3631 and 4487–4490, and orb
predecessors 4962–4964 and 4975. Matching restoration is already present in
Individual Progression's zone and riding SQL.

The reference removes the later Relic of the Earthen Ring quests 14100/14111.
This server keeps them behind each character's Wrath progression instead.
Its global Classic level cap, expansion restrictions and legacy trainer schema
also differ from this server's personal progression and current trainer data.

Use the comparison to identify specific missing content. The runtime sources
remain the forks pinned in [the dependency manifest](../versions.lock.json);
the reference modules and global SQL are not installed.

## Verification scope

Production-source fixtures exercise supported bot steps and refusals. Complete
quest runs, combat, navigation, event resets and recovery still need live-server
validation. Dungeon and raid equipment quests also need an appropriate earned
group and encounter support. Death knight starting quests belong to Wrath and
are outside the reference project's nine-class comparison.

See the [class quest guide](class-quests.md) for supported behavior and the
[class audit](todo.md#dungeons-raids-and-outdoor-content) for open work.
