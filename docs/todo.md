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
  overrides), Uldaman (earned acquisition of the Staff of Prehistoria for
  Ironaya's keystone), Zul'Farrak (waking
  Witch Doctor Zum'rah as a player does) and Blackrock Depths (earned access
  through the Shadowforge Lock with the group's own key).
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
- [ ] Raid Clear coverage for Naxxramas as upstream adds it; verify the raid
  before relying on it.
- [ ] Optional original raid difficulty: disable AutoBalance for 20- and
  40-player raids (`AutoBalance.Enable.20M`, `AutoBalance.Enable.40M`) once
  full bot raids are available, keeping party scaling for dungeons.

## Gameplay validation

- [ ] Verify complete runs in-game for each enabled Vanilla, TBC and Wrath
  dungeon: walking to the entrance, combat, loot rolls, quest objectives, wipes
  and normal recovery.
  Remove a failing dungeon from the default list until it is fixed. Confirm bot
  logout after the last real player session ends.
- [ ] Verify the Deadmines cannon in-game: the tank walks to and loots the
  gunpowder chest, handles its native ambushes, returns to the cannon and
  consumes the powder through ordinary item use. Cover full bags, missing or
  inaccessible powder, another character carrying it, interrupted casts,
  druid forms, an already open door and resuming the same instance. Confirm
  an autonomous party retains every member's personal entry and era checks.
- [ ] Verify both Uldaman altars in-game: physical approach and line of sight,
  the native five-second channel, interruptions and retries, an already active
  keeper chain or Archaedas fight, reset after a wipe and walking back from the
  entrance, resuming the same instance, a completed encounter, ritual-owner
  group changes or logout, and a fresh instance. Confirm normal combat and
  door opening, with no direct awakening casts or premature objective credit.
  Check Ironaya's seal with the group's own Staff of Prehistoria; autonomous
  recruitment must remain refused until its acquisition has an audited path.
- [ ] Verify complete Ring of Law and Blackrock Depths clears in-game: every
  member physically enters the arena, the native trigger starts Grimstone,
  both waves and the random boss are fought normally, and the objective waits
  for Grimstone's final waypoint and native encounter credit. Cover interrupted
  approaches, combat and looting while gathering, missing mesh, a trailing or
  disconnected member, a human starting early, an already running event,
  a wipe with ordinary resurrection and return travel, the two-minute reset
  cooldown, stop/resume, a completed event and a fresh instance. Confirm the
  separate Shadowforge key requirement still refuses autonomous recruitment.
- [ ] Verify long entrance and return paths in-game, including bends,
  interrupted movement and changed obstacles. Measure server tick time while
  multiple groups are travelling.
- [ ] Verify player-led Molten Core, Blackwing Lair, Zul'Gurub and Ahn'Qiraj raids
  with Raid Clear, including the Suppression Room without the raid cheat.
- [ ] Verify a complete player-led Onyxia clear with Raid Clear and Playerbots:
  each member's personal progression, Drakefire Amulet and portal refusal;
  ground, air and landing phases; all Deep Breath directions, Fireball spacing,
  head/tail positioning, Fear and threat recovery; restored Vanilla whelp
  targeting, evading mobs, wipe and ordinary recovery. Check earned-era
  EraTalents spells with normal resources, cooldowns, range and line of sight,
  plus strategy recovery after an AI reset and the Onyxia enable switch.
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
