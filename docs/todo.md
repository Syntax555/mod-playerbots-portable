# Development TODO

Open integration work and gameplay validation. The scope below describes the
source implementation; planned work is not a claim of release support.

## Current scope

| Area | Implementation and limits |
| --- | --- |
| Autonomous dungeons | Five nearby random bots can form a party and walk to Ragefire Chasm or the Stockade. Combat and navigation use Dungeon Clear and Playerbots. |
| Dungeon Clear access | With natural progression enabled, the integration permits only those two normal instances, including manually started runs. Other dungeons, heroic instances and raids are blocked for Dungeon Clear. |
| Raid parties | Automatic recruitment and travel for raid groups are not implemented. Player-led groups retain ordinary Playerbots encounter support. |
| Historical class quests | Selected priest families are restored. Other classes retain the core and Individual Progression implementations. |
| Validation | Selected native handlers and package contracts have automated checks. Complete live dungeon runs and all historical class quests have not been verified. |

## Dungeon and raid integration

- [ ] Separate autonomous route availability from Dungeon Clear access so its
  existing supported content can be used with earned progression and ordinary
  gameplay rules.
- [ ] Extend party selection and physical travel to eligible upstream-supported
  dungeons across Vanilla, TBC and Wrath. Reuse Dungeon Clear's encounter engine;
  retain each bot's own equipment, progress and entry requirements.
- [ ] Add raid recruitment and travel with the appropriate group sizes,
  attunements and instance lockouts. Verify which upstream raid encounters work
  under the same gameplay rules before advertising support.

## Gameplay validation

- [ ] Verify complete dungeon and raid runs in-game: walking to the entrance,
  combat, loot rolls, quest objectives, wipes and normal recovery. Confirm bot
  logout after the last real player session ends.
- [ ] Audit historical class quests beyond the restored priest families across
  Vanilla, TBC and Wrath, including teacher availability, objectives, rewards
  and paid training. Apply targeted fixes for confirmed discrepancies.
- [ ] Record verified content and remaining limits in the public guides,
  including matching EraTalents and MultiBot inspection behavior.

See [bot dungeons](bot-dungeons.md), [class quests](class-quests.md) and
[server adaptations](adaptations.md) for current behavior.
