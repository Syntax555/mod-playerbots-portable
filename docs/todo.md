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
  credit in the Twilight Realm and dungeon recruitment at refused portals.

## Dependency updates

- [ ] mod-playerbots `cf1a2a20`, the last commit before the configuration
  rename: refresh the natural-progression, earned-auctions and era-talents
  patches, reduce the upstream-fixes patch to what the pin lacks and adapt
  MultiBot's role toggles to the renamed strategies. A pin past `ed54b459`
  also needs a launcher migration of every `AiPlayerbot.*` key;
  `TestProfileKeys` fails until the profiles match.
- [ ] Dungeon Clear `da0bdfbc`: run the new Lab tick inside the natural gate
  and refuse `.dc lab run|batch` under natural progression.
- [ ] Raid Clear `a3c29f6a`: ship `RaidClear.Bots.TeachTranquilizingShot = 0`
  and keep the Zul'Gurub mind-control release from removing the bot's own
  crowd control.
- [ ] Try `CL_MPCount=2` on the Windows runner and drop the core
  `settings.cmake` compile-parallelism patch if MSBuild caps `cl.exe` the same
  way.
- [ ] Offer generic fixes upstream (formation velocity guard, the
  `resetTalentsCost` underflow, the empty random-battleground guard and the
  Individual Progression filter fixes) to shrink the patch set.

## Core and module patches

- [ ] Replace the historical class-quest core hook with
  `CONDITION_SOURCE_TYPE_QUEST_AVAILABLE` rows.
- [ ] Reduce the rated-arena core patch to the map filter once the team-era
  filter is shown never to reject in the shipped setups.
- [ ] Credit the Naxxramas marker together with the Ahn'Qiraj marker in strict
  mode instead of rewriting upstream condition rows, with a characters backfill.
- [ ] One earned-era helper in Individual Progression, clamped to the realm
  ceiling, instead of the local stage-to-era mappings in the other patches.
- [ ] Move the Into the Breach fix into the milestones patch and the riding
  script into its own patch (a coordinated two-patch refresh).
- [ ] Decide whether World Buff Bots keeps its announcer name pools, which only
  serve `{player}` in customized announcements.

## Launcher and updates

- [ ] Treat cleanup failures after a finished update as warnings unless the
  journal is still applying, so a lingering lock on a backup file does not stop
  the realm from starting.
- [ ] A MySQL Windows service under a system account cannot be opened by a
  normal user, so the update guard refuses every update. Read the image path
  without opening the process.
- [ ] When `OpenProcess` is denied, check the image name from the process
  snapshot instead of treating the process as gone.
- [ ] The update journal is rewritten, manifest included, once per installed
  file. Change the format only with a recovery path for older launchers.
- [ ] Close the short window in which `startup.exe` is missing between moving
  the old launcher to the backup and installing the new one.
- [ ] Sign `UPDATE_MANIFEST.json` so a token that can upload release assets
  cannot push code to installations.
- [ ] Evaluate starting `mysqld` with `--no-monitor` and tracking the server
  process directly, and applying updates in-process instead of through the
  detached helper.

## Release and tests

- [ ] Re-running an older successful main build can replace a pending
  publication of a newer build until the next push.
- [ ] Measure a compiler cache for the Windows compile step.
- [ ] Build `mpqread` once in the client job and pass it to the fixtures that
  read the client patch.
- [ ] Share the sanitizer build flags, the `--source`/`--core`/`--module`
  arguments and the WDBC helpers through `FixtureSupport`, and move the child
  fixtures of `TestEarnedProgression` into `run_fixtures.py` groups.
- [ ] Optional: replace the two submodules with the lock-driven fetch used for
  the other modules.
