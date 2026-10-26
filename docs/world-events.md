# Era world events

[Era Events](https://github.com/buildthehomelab/wow-mod-era-events) adds timed
outdoor encounters at four earned Individual Progression tiers. Each character
must be at the event's exact tier after applying the realm ceiling and in its
zone to see and fight its creatures. Humans, SelfBot characters and bots use
their own progress; a group leader does not unlock an event for other members.
Lowering the ceiling caps this event tier without erasing saved milestones.
No additional client files are needed.

| Event | Earned tier | Location and encounter |
| --- | --- | --- |
| Gates of Ahn'Qiraj | 4, rewarded gong quest | Qiraji waves at the Scarab Wall in Silithus, ending with Lieutenant General Nokhor |
| Scourge Invasion | 6, after C'Thun | Alternates between Stormwind/Undercity attacks and necropolis encounters in invasion zones |
| Legion Incursion | 7, after Vanilla Kel'Thuzad | Demon waves near Gadgetzan, Everlook, Cenarion Hold, Nethergarde Keep or Light's Hope Chapel |
| Zombie Infestation | 12, after Illidan with Sunwell access | Plagued crates, zombies, infection and Argent Healers in Stormwind or Orgrimmar |

Use `.era next` to see the event for your current tier and its timer. Characters
at other tiers have no matching event. The schedule starts over after a server
restart; running encounters do not persist.

## Timing and earned-play rules

Each event has an independent random 120–240 minute schedule, a 10-minute warning
and a 30-minute duration, except Ahn'Qiraj's 45 minutes. A scheduled event needs
one real non-GM player at its exact tier online. Bots can participate but do not
satisfy that minimum. If too few players are online, it retries every five
minutes. Players still travel to the announced location normally.

With the shipped strict earned progression, events respect the realm ceiling
and require the default progression chain. An inactive or custom chain runs no
events. Realm-wide Ahn'Qiraj phasing is refused, including GM requests: ringing
the gong starts an encounter for the earned tier without opening it to other
characters. Ordinary quest and boss requirements remain in place.

The profile disables automatic victory payouts. Strict mode also blocks these
gold, reputation and mailed-item grants if reward settings are customized,
because standing in the event's zone does not establish contribution. Normal
creature loot still uses native kill, eligibility and looting rules.

## Configuration

Edit `configs/modules/mod_era_events.conf` with the servers stopped.

| Setting | Shipped default | Purpose |
| --- | --- | --- |
| `EraEvents.Enable` | `1` | Master switch |
| `EraEvents.MinRealPlayers` | `1` | Real non-GM players at the exact tier required for scheduled starts |
| `EraEvents.RetryMinutes` | `5` | Retry delay while the player minimum is unmet |
| `EraEvents.<Event>.Enable` | `1` | Schedule the selected event |
| `EraEvents.<Event>.IntervalMin` / `IntervalMax` | `120` / `240` | Minutes between event opportunities |
| `EraEvents.<Event>.WarningMinutes` | `10` | Warning before a scheduled start |
| `EraEvents.<Event>.DurationMinutes` | `30`, Ahn'Qiraj `45` | Maximum encounter duration |
| `EraEvents.AQWar.RealmWideMinutes` | `0` | Realm-wide mode is also blocked by strict progression |
| `EraEvents.<Event>.RewardGold` / `RewardReputation` | `0` / `0` | Automatic victory payouts, blocked by strict progression |
| `EraEvents.<Event>.RewardItem` / `RewardItemCount` | `0` / `0` | Automatic item payouts, blocked by strict progression |

`<Event>` is `AQWar`, `ScourgeInvasion`, `LegionIncursion` or
`ZombieInfestation`. GM administration supports `.era list`,
`.era start <aq|si|legion|zombie>` and `.era stop <aq|si|legion|zombie>`.
Starting an event manually skips its timer and player minimum, while keeping
its earned-tier and realm-ceiling requirements.

The separate [World Buff Bots](world-buffs.md) module offers optional Vanilla
buff timers, disabled by default in favor of native quest events. Era Events'
Scourge encounter is separate from the core's global
Scourge Invasion (game event 17), which Individual Progression disables.

The launcher adds the module configuration and preserves custom values during
updates. See [configuration updates](configuration.md) and
[source versions](module-versions.md). Source fixtures verify the earned-play
guards; full encounters and bot tactics have not been verified in game.
