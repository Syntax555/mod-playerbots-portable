# Roadmap and validation

Open integration work and gameplay validation. Planned work is not a claim of
release support; [bot dungeons and raids](bot-dungeons.md),
[class quests](class-quests.md) and [server adaptations](adaptations.md)
describe the current behavior. Prefer existing AzerothCore and module
functions, with small integration changes where required by earned progression
and ordinary player actions.

## Dungeon integration

- [ ] Earned replacements for the refused Dungeon Clear events so the remaining
  Vanilla dungeons can be enabled: Wailing Caverns (Serpentis and lower-cavern
  drops over real paths, the Disciple of Naralex escort without speed
  overrides), the Deadmines (Defias Cannon with gunpowder the party carries),
  Uldaman (the altars through the player interaction), Zul'Farrak (waking
  Witch Doctor Zum'rah as a player does) and Blackrock Depths (the Ring of Law
  through its arena trigger).
- [ ] Expand the audited TBC and Wrath routes by providing ordinary player
  actions for currently refused event controllers, escorts, vehicle sequences
  and locked objectives. Verify complete runs before advertising completion.
- [ ] Evaluate heroic autonomous parties separately, including earned access,
  keys, gear suitability and heroic-only encounter mechanics.

## Raid integration

- [ ] Autonomous raid recruitment and travel: 10-, 20- and 40-player groups
  with tank and healer quotas, recruited nearby and walking to the entrance.
  Optimal Bot Raid's role quotas are a reference; its teleports, level
  relaxation and factory refresh are not compatible with earned play.
- [ ] Bots earn raid attunements and keys through their own quest progress
  (Drakefire Amulet, Blackhand's Command, Naxxramas) and respect instance
  lockouts.
- [ ] Molten Core rune dousing with Aqual Quintessence earned by a bot.
- [ ] Raid Clear coverage for Onyxia, the Ahn'Qiraj raids and Naxxramas as
  upstream adds them; verify each raid before relying on it.
- [ ] Optional original raid difficulty: disable AutoBalance for 20- and
  40-player raids (`AutoBalance.Enable.20M`, `AutoBalance.Enable.40M`) once
  full bot raids are available, keeping party scaling for dungeons.

## Gameplay validation

- [ ] Verify complete runs in-game for each enabled Vanilla, TBC and Wrath
  dungeon: walking to the entrance, combat, loot rolls, quest objectives, wipes
  and normal recovery.
  Remove a failing dungeon from the default list until it is fixed. Confirm bot
  logout after the last real player session ends.
- [ ] Verify long entrance and return paths in-game, including bends,
  interrupted movement and changed obstacles. Measure server tick time while
  multiple groups are travelling.
- [ ] Verify player-led Molten Core, Blackwing Lair and Zul'Gurub raids with
  Raid Clear, including the Suppression Room without the raid cheat.
- [ ] Audit historical class quests beyond the restored priest families across
  Vanilla, TBC and Wrath, including teacher availability, objectives, rewards
  and paid training. Apply targeted fixes for confirmed discrepancies.
- [ ] Record verified content and remaining limits in the public guides,
  including matching EraTalents and MultiBot inspection behavior.
