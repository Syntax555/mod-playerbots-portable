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
| Warrior | Startup quest flag changes already exist in Individual Progression. No Affray or stance bot sequence is supplied. | Defensive stance and The Affray still need their own event handling and live validation. |
| Paladin | Tome of Nobility and class-mount quest relations are already restored. | Resurrection, Valor and mount chains remain on the class audit. Quest-taught Sense Undead uses personal-era gates. |
| Hunter | The project supplies no taming-lesson bot actions. | Six racial lesson chains and first-pet acquisition have dedicated actions. Historical pet ability acquisition remains separate. |
| Rogue | Matching startup letter and scroll flags already exist. | Poison, lockpicking, keys and event handling remain to be audited. |
| Priest | Trainer edits do not replace the existing historical racial quest and spell integration. | Restored racial rewards and paid ranks have personal-era gates; complete bot runs still need validation. |
| Shaman | Earth quest flag changes and Water quest text already exist. | Horde and Draenei totem actions handle owned quest items, wells, spirits and ritual objects. Optional equipment chains and complete live runs remain open. |
| Mage | Matching startup quest flags and trainer handling already exist. | Magecraft, Fragmented Magic and other class sequences remain to be audited. |
| Warlock | Imp and Felsteed quest relations, orb prerequisites and inspected quest starters already exist. | The 43-step basic-demon action supplies bot handling absent from the reference project. Mounts, later demons and optional chains remain separate. |
| Druid | Existing native quest scripts and trainer restoration supply quest content. | Bear, Aquatic Form and cure-event bot sequences still need implementation and validation. |

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
