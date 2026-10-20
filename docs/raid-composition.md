# Raid composition building block

The earned raid integration supplies a world-thread recruitment function and a
roster planner in the [Dungeon Clear patch](../patches/mod-dungeon-clear-earned-raid-composition.patch).
No timer, chat command or Dungeon Clear route calls this function. Autonomous
raid travel and clears remain unavailable; this is a tested component for
their later integration.

## Roles and subgroups

Tank, healer and ranged roles come from Playerbots' active strategies, rather
than class or talent-tree guesses. Missing tanks or healers refuse formation;
damage dealers never replace them. Extra tanks or healers do not fill damage
slots. The melee column is a ceiling; ranged damage fills the remaining slots.
Unknown map, size or era combinations are refused.

The numerical defaults follow
[Optimal Bot Raid at `1d5476f7c782`](https://github.com/buildthehomelab/wow-mod-optimal-bot-raid/blob/1d5476f7c782f824d6813786a50ba94a8f2b5ebd/src/cs_optimal_bot_raid.cpp).
That module is a reference, not an installed dependency. Its class quotas,
role-shortfall fallback and character-changing commands are not included.

| Era | Raid | Size | Tanks | Healers | Maximum melee DPS |
| --- | --- | ---: | ---: | ---: | ---: |
| Vanilla | Zul'Gurub | 20 | 3 | 6 | 3 |
| Vanilla | Ruins of Ahn'Qiraj | 20 | 3 | 5 | 3 |
| Vanilla | Onyxia | 40 | 3 | 10 | 4 |
| Vanilla | Molten Core | 40 | 5 | 11 | 8 |
| Vanilla | Blackwing Lair | 40 | 5 | 13 | 7 |
| Vanilla | Temple of Ahn'Qiraj | 40 | 5 | 12 | 7 |
| Vanilla | Naxxramas | 40 | 8 | 12 | 6 |
| TBC | Karazhan, Zul'Aman | 10 | 2 | 3 | 2 |
| TBC | Gruul, Black Temple | 25 | 3 | 7 | 4 |
| TBC | Magtheridon, Tempest Keep, Hyjal | 25 | 3 | 7 | 5 |
| TBC | Serpentshrine Cavern | 25 | 4 | 7 | 4 |
| TBC | Sunwell | 25 | 3 | 8 | 4 |
| Wrath | Onyxia | 10 / 25 | 2 / 3 | 2 / 5 | 1 / 3 |
| Wrath | Naxxramas | 10 / 25 | 2 / 3 | 2 / 5 | 2 / 5 |
| Wrath | Obsidian Sanctum | 10 / 25 | 2 / 2 | 2 / 5 | 1 / 5 |
| Wrath | Eye of Eternity, Vault of Archavon | 10 / 25 | 2 / 2 | 2 / 5 | 2 / 5 |
| Wrath | Ulduar | 10 / 25 | 2 / 3 | 3 / 6 | 1 / 4 |
| Wrath | Trial of the Crusader | 10 / 25 | 2 / 3 | 2 / 6 | 2 / 4 |
| Wrath | Icecrown Citadel | 10 / 25 | 2 / 2 | 3 / 6 | 1 / 5 |
| Wrath | Ruby Sanctum | 10 / 25 | 2 / 2 | 3 / 6 | 1 / 6 |

Subgroups contain five members, with healers spread evenly and physical roles
and casters clustered. Buff preferences use the ordinary AI spell resolver's
actually learned, active current-spec ranks, including historical variants.
Class, talents and level alone establish no buff capability. Raid-wide effects
do not justify subgroup rearrangements. The planner supplies preferences, not
a guarantee of buff coverage or successful casts.

The scope check reads the learned spell's native effects and, for summoned
totems, the creature's two pulse spells. The pinned historical Windfury pulse
is raid-wide, while TBC Trueshot Aura has a real party effect. Active shouts,
Trueshot and utility totems are considered; passive talent auras and effects
provided only by scripts are outside this preference calculation.

Naxxramas' eight-tank Vanilla quota follows the reference's full-raid profile,
including the Horsemen; it is not a separate Patchwerk tactic. A roster profile
does not establish encounter support for Naxxramas or any other listed raid.

## Recruitment and access

`EarnedRaidGroups::Recruit(entrance, size, expansion, online)` accepts an existing
native outdoor portal and a pool of online bots. The leader must be within
1,000 yards of its entrance; members must share its map, faction and phase and
be within the smaller of 60 yards and Playerbots' sight distance. Every bot must
already have its own earned era, level cap (60/70/80) and selected native raid
difficulty. Vanilla and TBC use normal difficulty; Individual Progression's
Vanilla Onyxia and Naxxramas use their native difficulty `2`. Wrath uses normal
10- or 25-player difficulty. The function never changes difficulty or level.

Only available headless random-account bots without a player master may be
invited. Players, SelfBot characters, controlled altbots, existing groups and
queued, travelling or busy candidates are excluded. Control and personal access
are checked again immediately before inviting. Recruitment reuses Dungeon
Clear's eligibility functions, native invitations and Playerbots' ordinary
acceptance; raid conversion and subgroup placement use the core's group API.
Conversion also retains the native `Group.Raid.LevelRestriction` check.

Each bot passes Individual Progression's own map gates and the native access
requirements before invitation. A leader's key or completed quest cannot stand
in for another bot's. After grouping, every member must also pass the complete
native entry check and resolve to the same destination instance. Different
permanent lockouts refuse formation and remain intact. Role or
ownership changes during acceptance also refuse formation.

Failed formation cancels its own pending invitations, releases its bot group
outside the instance and restores the accepted bots' saved navigation settings.
A group with a changed leader, taken over by a player or moved inside is left
alone. No teleport,
summon, factory refresh, level relaxation, item, money or progression grant is
part of formation.

## Validation and limits

Native fixtures exercise the production planner and recruitment functions,
including quotas, learned spell contracts, subgroup capacity, personal entry
checks, control changes and rollback. Mutation checks remove individual gates
and require the fixtures to reject the result. These are component checks;
complete raids have not been validated in game.

The component does not acquire attunements or keys, choose a raid difficulty,
find a missing entrance, navigate, start Dungeon Clear, douse runes or supply
encounter mechanics. In particular, the pinned Vanilla Naxxramas integration
has no ordinary area-trigger teleport for this API to use. Its composition can
be planned, but formation through a fabricated portal is not supported.
Remaining work is tracked in the [raid integration checklist](todo.md#raid-integration).
