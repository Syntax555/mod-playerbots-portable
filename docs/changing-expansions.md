# Individual progression through expansions

Fresh v1.0.13 installations use **individual** mode on the WoW 3.3.5a client.
The realm supports level 80 and all expansions, while each character begins in
Vanilla and earns its own progression. There is no manual realm switch needed
when a character finishes Vanilla or TBC.

| Earned milestone | Character access | Account creation unlock |
| --- | --- | --- |
| Starting tier 0 | Vanilla; XP stops at 60 until TBC is earned | Vanilla races/classes |
| Tier 8: all Vanilla tiers, then Into the Breach | TBC; XP stops at 70 until Wrath is earned | Blood elves and draenei |
| Tier 13: TBC completed, including Kil'jaeden | Wrath; normal XP up to 80 | Human-controlled death knights |
| Tier 18 | Wrath progression completed | No extra bot grants |

Race/class unlocks use rewarded progression markers from characters on **that
account**. Your account's progress does not unlock races on random-bot accounts.
The patched bot factory checks the same account hook as ordinary character
creation before choosing a race. Bot login checks it again before loading the
character, so an existing unearned expansion race remains offline. Characters
are not deleted, rerolled or reset.

New random bots always use the ordinary level-1 starter kit, zero starting gold
and normal XP. An unlocked blood elf or draenei still starts at level 1, tier 0,
and earns its own quests, equipment and expansion access. An account unlock does
not give all its characters the highest character's progression.

**Death knight bots stay disabled.** Their normal class start is level 55; a
level-1 death knight would require a different starting experience and class
design. Human-controlled death knights retain their normal start only after the
account earns tier 13. Wrath introduces no additional playable races.

The population's nine-class account pools are not automatically replaced with
expansion races after unlocks. Eligible new characters can use unlocked races
when creation is requested and an account has space. No character recycling is
used to change the race mix.

## Updating an existing realm

Use the **complete v1.0.13 server ZIP**. Replacing only the launcher cannot fix
the old bot factory's missing account checks.

1. Back up the databases and configurations, then stop the launcher and servers.
2. Install the updated ZIP using the existing installation's upgrade procedure.
3. In PowerShell in the installation folder, run:

   ```powershell
   .\startup.exe --set-expansion individual
   .\startup.exe --apply-profiles
   ```

4. Restart `startup.exe` normally.

The first command aligns linked progression settings and enforces earned starts
and unlock thresholds. The second applies all recommended farming, talent,
travel and balancing settings. Both back up changed configurations. Neither
command changes characters, inventories, gold, spellbooks or databases.

Existing Vanilla/TBC ceilings stay selected until explicitly changed. A normal
upgrade or `--apply-profiles` does not open an established realm automatically.

## Optional realm ceilings

`--show-expansion` displays the selected mode. Use `--set-expansion vanilla` or
`--set-expansion tbc` only if you also want a shared realm ceiling. These keep
individual requirements and restrict the realm to level 60/tier 7 or level
70/tier 12. `--set-expansion wotlk` retains the older level-80 phase option;
`individual` is the recommended mode with a conservative level-80 dual-spec
minimum. The older `wotlk` mode permits dual spec from level 40.

Phase changes require initialized active configs and a stopped realm. The
launcher validates every update, makes timestamped `.backup.*` copies, and rolls
back earlier writes if replacement fails. It refuses lower level ceilings after
an expansion has opened; reverting needs matching database/config backups.

The mode is recorded in `configs/realm-phase.txt` and survives profile updates
and missing-config creation. Do not edit that marker alone. The core's
`Expansion = 2` is always required, including for restored Vanilla Naxxramas.

## Balancing and gameplay limits

AutoBalance counts the actual non-GM party, including bots. Full groups retain
ordinary creature stats; smaller groups use the existing instance scaling curve
and reduced XP/money. Creature levels are preserved, no bonus tokens are awarded,
and Vanilla/TBC damage and healing modifiers remain 1.0 for bots and humans.
Item, quest, spell-rank, travel and XP progression gates remain per character.

Talent allocation spends earned points without free resets; fallback allocation
also respects the configured Vanilla/TBC tree-depth limits. The talent identities
are still Wrath data. Ground riding remains paid at levels 40/60; flying requires
the ordinary trainer's prerequisites. Dungeon Finder stays disabled, and later
bot battlegrounds/arenas remain disabled pending their own audit.

The server can recover Into the Breach already rewarded while a Vanilla ceiling
was active, only after the character has earned tier 7 and the ceiling permits
tier 8. It does not award ordinary quests, levels or gear. Some upstream encounter
AI still has special movement/combat shortcuts, and autonomous completion of
every raid or class/profession quest is not guaranteed. See
[the configuration audit](vanilla-config-audit.md) for those remaining limits.
