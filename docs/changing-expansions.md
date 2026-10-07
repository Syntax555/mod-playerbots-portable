# Individual progression through expansions

Fresh installations use **individual** mode on the WoW 3.3.5a client. The realm
supports level 80 and all expansions, while each ordinary character starts at
level 1, tier 0, and earns its own progression. Humans and bots use the same
milestones. An account unlock permits race creation; it never advances an alt.

| Earned milestone | Character access | Account creation unlock |
| --- | --- | --- |
| Starting tier 0 | Vanilla; XP stops at 60 until TBC is earned | Vanilla races/classes |
| Tier 8: Vanilla prerequisites, then Into the Breach | TBC; XP stops at 70 until Wrath is earned | Blood elves and draenei |
| Tier 13: TBC prerequisites, including Kil'jaeden | Wrath; normal XP up to 80 | No additional level-1 class |
| Tier 18 | Wrath progression completed | No levels, gear or money granted |

The default enables `IndividualProgression.StrictEarnedProgression = 1` with the
module's normal milestone chain. Eligible boss credit is recorded durably,
including when earned out of order, but advancement requires every preceding
milestone. Rewarded transition quests are checked separately. A later kill or an
early Into the Breach completion cannot fill missing Vanilla tiers.

## Required milestone chain

The table names the completion marker for each tier, rather than every encounter
available at that tier. IP's ordinary quest, item, map and attunement requirements
also apply. Completing every optional quest or raid is not an extra requirement
introduced by this patch.

| Tier earned | Required completion | Next content opened |
| --- | --- | --- |
| 1 | Ragnaros | Blackwing Lair progression |
| 2 | Restored Vanilla Onyxia | Next Vanilla milestone |
| 3 | Nefarian | Zul'Gurub and AQ preparation |
| 4 | Rewarded Bang a Gong! or IP's Simply Bang a Gong | AQ gates and outdoor war |
| 5 | Rewarded Chaos and Destruction | Remaining AQ war progression |
| 6 | C'Thun | Restored Naxxramas 40 and Scourge progression |
| 7 | Kel'Thuzad in restored Naxxramas 40 | Into the Breach transition |
| 8 | Rewarded Into the Breach, after the Vanilla chain | TBC and level 61–70 XP |
| 9 | Prince Malchezaar | Serpentshrine Cavern / Tempest Keep progression |
| 10 | Kael'thas | Hyjal / Black Temple progression |
| 12 | Illidan | Sunwell progression |
| 13 | Kil'jaeden | Wrath and level 71–80 XP |
| 14 | Wrath Kel'Thuzad | Ulduar progression |
| 15 | Yogg-Saron | Trial of the Crusader progression |
| 16 | Anub'arak in Trial of the Crusader | Icecrown Citadel progression |
| 17 | The Lich King | Ruby Sanctum progression |
| 18 | Halion | Completed default chain |

Tier 11 is reserved and has no default milestone. The chain moves from 10 to 12;
module-owned item/vendor/quest conditions that depended on the unused tier have
been corrected to 12 without awarding a fictitious completion.

Boss credit requires eligible participation in the tapped encounter. Nearby
eligible party members can receive their own credit; merely sharing a group,
being elsewhere in the instance, copying its leader's tier or possessing a broad
raid achievement is insufficient. Ordinary group-attunement commands and bot
progression synchronization cannot bypass strict mode. Explicit GM administration
remains available, so playing accounts should not have GM privileges.

If a transition quest was already rewarded, it becomes usable when the preceding
chain is complete and the selected realm ceiling permits advancement. The system
does not reward the ordinary quest again or grant catch-up resources.

## Accounts and the bot population

Race unlocks use rewarded progression markers from characters on **that
account**. Your account's progress does not unlock races on random-bot accounts.
The patched bot factory checks the ordinary account hook before choosing a race;
bot login checks it again. An existing unearned expansion-race bot stays offline
rather than being deleted or rerolled.

An unlocked blood elf or draenei starts at level 1, tier 0, with the normal starter
kit and zero gold. It earns its own levels, equipment and content access. The
nine-class bot account pools are not automatically recycled into expansion races.
Eligible new characters can use unlocked races when requested and an account has
space.

**Strict mode blocks new death knight creation for every account.** Their native
level-55 start cannot meet the level-1 policy. Existing death knights are retained
with native class talents; this change does not redesign their starting zone.

Approximately 5% of random bots are assigned each earned cap at 19, 29, 39, 49,
59, 69 or 79; the remaining 65% continue individual progression. Every fresh bot
levels from 1, and level-69/79 residents first earn TBC/Wrath access. This maintains
companions at lower levels over time without creating pre-levelled populations.
See [earned bot brackets](earned-bot-brackets.md) for cap changes and release.

## Era talents, training and prices

The default [Era Talents integration](era-talents.md) selects each character's
historical tree from earned progression: Vanilla below 8, TBC at 8–12, and native
Wrath at 13+. The Vanilla source is 1.12.1; the TBC talent source is Classic 2.5.4,
which includes changes from the original 2.4.3 game. Players require the matching
EraTalents addon and merged client `Data/patch-V.mpq`; bots use server data only.

Bots add newly earned points to their existing build. Ordinary respecs use the
paid trainer path and normal escalating cost. A real era crossing refunds the
departing tree's earned points once, out of combat, so the character can choose
the new tree. It grants no levels, trained ranks, equipment or gold. Historical
class spell variants require their paid lesson or earned talent/quest source.
Stored glyph ownership in both specializations is retained, with glyph effects
and new glyph use blocked before earned Wrath.

Strict mode quotes riding training costs by the purchasing character's earned
era. The same quote is used for trainer display and the actual purchase; normal
reputation discounts still apply.

| Riding skill | Vanilla below tier 8 | TBC tiers 8–12 | Wrath tier 13+ |
| --- | ---: | ---: | ---: |
| Apprentice | 90g | 35g | 4g |
| Journeyman | 900g | 600g | 50g |
| Expert | Configured cost; ordinary prerequisites apply | 800g | 250g |
| Artisan | Configured cost; ordinary prerequisites apply | 5,000g | 5,000g |

These are base skill-training prices: late Vanilla 1.12.1, original TBC 2.4.3 and
the pinned Wrath dataset. Existing IP level and acquisition prerequisites remain,
including ground riding at 40/60 and flying at 70. This does not lower riding
levels on reaching Wrath, change owned skill ranks, refund old purchases or change
the price of mount items. Other item/vendor and trainer prices still use shared
IP/core SQL. The mixed-era auction house also remains one earned market.

## Updating an existing realm

Use the **complete updated server ZIP**; replacing the launcher alone cannot add
the strict milestone, training or talent hooks.

1. Back up databases and configurations, then stop the launcher and servers.
2. Install the updated ZIP using the existing installation's upgrade procedure.
3. Install the matching `EraTalents-client-<version>.zip` addon and MPQ in every
   human player's client, then fully restart WoW.
4. In PowerShell in the installation folder, run `startup.exe --apply-profiles`.
   If an older shared Vanilla/TBC ceiling should be removed, first run
   `startup.exe --set-expansion individual`.
5. Restart `startup.exe` normally and allow the server's normal SQL updater to
   import the bundled migrations.

The launcher backs up changed configurations, retains unrelated settings and
does not reset characters or databases. Historical talent activation converts
talent/spell state for the character's earned era; see the detailed
[migration notes](era-talents.md#updating-an-existing-realm).

Existing levels, highest stored tiers, items and gold are preserved. Strict mode
does not retroactively certify old grants or import every old raid achievement
as new durable boss evidence. Missing future milestone credit may require another
eligible kill. A fresh database is needed if the aim is to establish that every
character began under the new earned policy; updating does not erase an old realm.

Existing Vanilla/TBC ceilings stay selected until explicitly changed. A normal
upgrade or `--apply-profiles` does not open an established realm automatically.

## Optional realm ceilings and remaining limits

`--show-expansion` displays the selected mode. `--set-expansion vanilla` or
`--set-expansion tbc` adds a shared level 60/tier 7 or level 70/tier 12 ceiling
while retaining individual requirements. `--set-expansion wotlk` retains the
older level-80 phase option; `individual` is recommended with a level-80 minimum
for new dual-spec purchases. The older `wotlk` mode permits dual spec from 40.

Phase changes require initialized active configs and a stopped realm. The
launcher validates updates, creates timestamped `.backup.*` copies and rolls
back earlier writes if replacement fails. It refuses lower level ceilings after
an expansion has opened; reverting requires matching database/config backups.
The mode in `configs/realm-phase.txt` survives profile updates and missing-config
creation. Do not edit that marker alone. Core `Expansion = 2` remains required
for the restored Vanilla Naxxramas map.

AutoBalance counts actual non-GM occupants, including bots. Full groups retain
ordinary creature stats; smaller parties use instance scaling with reduced
XP/money. Creature levels remain unchanged, bonus tokens are disabled, and
Vanilla/TBC damage and healing modifiers remain 1.0 for humans and bots.

Dungeon Finder and later bot battlegrounds/arenas remain disabled. Some upstream
encounter AI has special movement or combat shortcuts, and autonomous completion
of every raid or class/profession quest is unverified. Historical talents do not
replace every Wrath combat, profession, pet or world-data rule. See
[the configuration audit](vanilla-config-audit.md) for the scope of source checks
and live-gameplay limits.
