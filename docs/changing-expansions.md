# Changing the realm expansion

Individual Progression supports Vanilla, TBC and WotLK on the same WoW 3.3.5a
client and server databases. Opening an expansion raises the realm's ceiling.
It does not advance every character to that expansion or award levels/items.

Use the phase-aware launcher added after v1.0.11. For an existing v1.0.11 realm,
the standalone launcher upgrade can replace `startup.exe` while retaining the
installed server executables and databases. Its phase commands are available
immediately. The progression quest recovery fix described below also needs the
new server binaries included in the next complete portable release.

1. Back up the realm's databases and configurations. Config backups alone cannot
   undo gameplay earned after an expansion opens.
2. Stop `startup.exe`, `worldserver.exe` and `authserver.exe`.
3. In PowerShell in the server installation folder, choose the phase:

   ```powershell
   .\startup.exe --set-expansion tbc
   ```

   Later, to open Wrath:

   ```powershell
   .\startup.exe --set-expansion wotlk
   ```

4. Run `startup.exe` normally to restart the realm.

`startup.exe --show-expansion` displays the selected phase. Fresh installations
start in Vanilla. Phase selection requires the three active realm/module
configs; run the launcher once to create them if the realm is not initialized.

The command refuses to write while a realm port is listening. It validates all
updates and creates timestamped `.backup.*` copies before replacing configs.
A failed replacement rolls back earlier writes. Repeating the same phase makes
no further changes. Returning from TBC/WotLK to an earlier phase is blocked;
restore a matching database/config backup if you need to undo realm progression.

## Settings changed together

These values can also be applied manually to the existing active configs with
the old launcher. Manual changes alone do not give the old `--apply-profiles`
command awareness of the expansion, so use the new launcher for future updates.

| Active config / setting | Vanilla | TBC | WotLK |
| --- | --- | --- | --- |
| `worldserver.conf`: `MaxPlayerLevel` | 60 | 70 | 80 |
| `worldserver.conf`: `Expansion` | 2 | 2 | 2 |
| `worldserver.conf`: `CharacterCreating.Disabled.RaceMask` | 1536 | 0 | 0 |
| `worldserver.conf`: `CharacterCreating.Disabled.ClassMask` | 32 | 32 | 0 |
| `worldserver.conf`: `MinDualSpecLevel` | 80 | 80 | 40 |
| `modules/individualProgression.conf`: `IndividualProgression.ProgressionLimit` | 7 | 12 | 0 (unlimited) |
| `modules/individualProgression.conf`: `IndividualProgression.BotAccountsMaxLevel` | 60 | 70 | 80 |
| `modules/playerbots.conf`: `AiPlayerbot.RandomBotMaxLevel` | 60 | 70 | 80 |
| `modules/playerbots.conf`: `AiPlayerbot.botActiveAloneSmartScaleWhenMaxLevel` | 60 | 70 | 80 |
| `modules/playerbots.conf`: `AiPlayerbot.RandomBotMaps` | `0,1` | `0,1,530` | `0,1,530,571` |

Module configs are under `configs/modules/`, and `worldserver.conf` is under
`configs/`. `Expansion = 2` is required for the Wrath client/core and the restored
Vanilla Naxxramas map even during the Vanilla phase.

The helper keeps Individual Progression enabled, its starting tier at zero,
the bot/excluded account filters empty, and `AiPlayerbot.NaturalProgression = 1`.
Credentials, file paths, population targets and unrelated custom settings remain.
No database command, SQL import, character reroll or reset runs during selection.

The chosen phase is recorded in `configs/realm-phase.txt`. Later profile updates
and missing-config creation use that choice. Do not change the phase by editing
only this file: the command updates all active configs together. Older manually
upgraded realms with matching caps are recognized without that file. If old caps
conflict, explicitly select the latest expansion already enabled to align them;
profile migration refuses to guess and revert a later realm to Vanilla.

## Earned progression and remaining limits

Characters still need tier **8** for TBC access/XP beyond 60 and tier **13** for
Wrath access/XP beyond 70. Tier 12 opens Sunwell; it keeps Wrath locked until the
realm opens that expansion. Tier 18 completes Wrath. Unlocking the realm alone
does not satisfy quests, raid kills, attunements or reputation requirements.

TBC races require account progression 8; player death knights require progression
13 and retain their ordinary level-55 class start. Existing bots are not rerolled,
and random death knights stay disabled to retain level-1 bot creation. Talent
depth restriction is already level-aware and remains enabled; this does not
replace the Wrath client's talent data with historical expansion trees.

The module checks legitimately earned raid achievements on login. The updated
server patch also recognizes **Into the Breach** already rewarded while TBC was
locked, provided the character earned Vanilla tier 7. Once the realm opens TBC,
that completion can advance the character to tier 8. It still respects the realm
limit and does not award levels, money, equipment or unearned raid progress.

This command retains conservative bot PvP settings: it does not automatically
enable later battlegrounds, random battlegrounds or arenas. The existing Vanilla
bot PvP restriction excludes bots above level 60; expanded bot PvP needs its own
review. Dungeon Finder remains disabled. Some later encounters still need an AI
audit, and the autonomous bots cannot guarantee every raid or class/profession
quest. See `vanilla-config-audit.md` for the existing gameplay limits.
