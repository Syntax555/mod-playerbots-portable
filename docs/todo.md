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
- [ ] Verify in-game the behavior covered so far only by fixtures: discovered
  flight routes, Drain Soul shards for every warlock spec, SelfBot talent
  points, weighted bot specs, Spirit of Zandalar at the Zul'Gurub stage, Halion
  credit in the Twilight Realm, dungeon recruitment at refused portals and
  vendor bag purchases.
- [ ] Verify era experience in game: quest values per era, battleground
  objective XP, heirloom and holiday bonuses, and rest and quest money at the
  60/70 era caps.

## Dependency updates

- [ ] Submit the prepared Individual Progression filter fix upstream when
  repository permissions allow; see the
  [upstream proposals](https://github.com/Syntax555/mod-playerbots-portable/blob/main/docs/upstream/README.md).
- [ ] Track the generic core proposals, then pin accepted fixes and remove
  their corresponding local hunks.

## Core and module patches

- [ ] Keep the rated-arena team-era filter while retained level-70 teams can
  enter the same native bracket with different earned eras after a TBC-to-Wrath
  realm transition. Remove it only if the native admission rules make this
  impossible without restricting existing characters or teams.
- [ ] Decide era experience rules with weak sources: Vanilla repeatable quests
  paying XP on every turn-in; the 1.12/2.4.3 hunter pet XP requirement; dungeon
  and raid elite multipliers (Outland ×4.5 versus TBC DB ×2.5/×2.0, Vanilla
  bosses ×4 versus ×5); gray level 47 at level 60 for group splits, which needs
  a core patch.
- [ ] Heirloom item stats and Experience Eliminator availability before Wrath.
- [ ] Core experience deviations shared by every era: raid groups outside raid
  maps receive the party bonus, and online rest accrues faster in rest areas.
- [ ] Thrallmar's and Honor Hold's Favor raise kill XP twice in the core: once
  through their aura effect in `KillRewarder` and once in `Player::GiveXP`. Era
  experience removes the duplicate for TBC-era characters only.
- [ ] Recruit-a-Friend started after the 2.4.3 release; decide whether TBC and
  Wrath characters should regain it.

## Launcher and updates

- [ ] Sign `UPDATE_MANIFEST.json` so a token that can upload release assets
  cannot push code to installations.
- [ ] Evaluate starting `mysqld` with `--no-monitor` and tracking the server
  process directly, and applying updates in-process instead of through the
  detached helper.

## Release and tests

- [ ] Measure a compiler cache for the Windows compile step.
- [ ] Optional: replace the two submodules with the lock-driven fetch used for
  the other modules.
