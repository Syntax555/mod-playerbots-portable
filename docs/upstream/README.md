# Generic upstream fixes

These proposals contain only generic fixes, exported with `git format-patch`
from clean upstream revisions. They are review artifacts, outside the ordered
runtime patch chain and the server ZIP. Keep the local fixes until an accepted
upstream revision is pinned and the corresponding local hunks can be removed
safely.

| Fix | Upstream status | Review artifacts |
| --- | --- | --- |
| Formation velocity guard | [#28141](https://github.com/azerothcore/azerothcore-wotlk/issues/28141) is open; absent from both checked core branches | [Patch](formation-velocity.patch), [proposal](formation-velocity.md) |
| Talent reset cost underflow | [#28142](https://github.com/azerothcore/azerothcore-wotlk/issues/28142) is open; absent from both checked core branches | [Patch](talent-reset-cost.patch), [proposal](talent-reset-cost.md) |
| Empty random-battleground candidates | [#28143](https://github.com/azerothcore/azerothcore-wotlk/issues/28143) is open; absent from both checked core branches | [Patch](random-battleground.patch), [proposal](random-battleground.md) |
| Empty Individual Progression account filters | Absent from the checked `master`; the merged account cache still queries disabled filters | [Patch](individual-progression-filters.patch), [proposal](individual-progression-filters.md) |

The core issues include the complete minimal diff and validation results.
The pinned Individual Progression revision includes the account-cache change
[PR #1308](https://github.com/ZhengPeiRu21/mod-individual-progression/pull/1308).
Its current empty-filter guards live in the numeric account overloads in
[the runtime patch](../../patches/mod-individual-progression-empty-account-filters.patch).
The review artifacts below retain their recorded base for reproducible checks.

The Individual Progression proposal only includes account classification and
character-creation filters. The local transition-quest changes, custom talent
reset hooks and earned-era arena selection rules are outside these proposals.

## Integration status

The source comparison uses AzerothCore `master`
[`aa921a00a2789f7594a99f535ef30f90780f8cda`](https://github.com/azerothcore/azerothcore-wotlk/commit/aa921a00a2789f7594a99f535ef30f90780f8cda)
and the required Playerbots core `Playerbot` branch
[`3f2969ddb0da42b48b4fca050c02b19163ba1e20`](https://github.com/mod-playerbots/azerothcore-wotlk/commit/3f2969ddb0da42b48b4fca050c02b19163ba1e20).
The latter is already the locked core revision. Open issues alone do not
establish that a fix is available in either branch.

| Production method in both checked cores | Missing behavior | Retained local change |
| --- | --- | --- |
| `FormationMovementGenerator::LaunchMovement` | Falls back only for `velocity == 0.0f`, although the spline validator rejects velocities at or below `0.01f` | [Formation guard](../../patches/azerothcore-formation-minimum-velocity.patch) |
| `Player::resetTalentsCost` | Converts negative elapsed months to unsigned and subtracts the decay before clamping | Cost guard in [respec accounting](../../patches/azerothcore-era-respec-accounting.patch) |
| `BattlegroundMgr::GetRandomBG` | Dereferences the weighted selection without checking `ids.empty()` | Empty-selection guard in [earned-era arena matching](../../patches/azerothcore-earned-era-arena-matching.patch) |

Individual Progression `master`
[`4933d455d2f611eed50c74c68c78832df4ed37a3`](https://github.com/ZhengPeiRu21/mod-individual-progression/commit/4933d455d2f611eed50c74c68c78832df4ed37a3)
is the locked revision and includes the Scarab Gong gossip correction. Both
numeric account predicates still call `GetAccountMatch` unconditionally, and character creation shares
those predicates. The cache therefore still performs an initial account-name
query when both filters are empty. The local guards remain necessary for each
disabled filter, including after a configuration reload.

None of these four fixes has a replacement in the checked sources. The locked
revisions and runtime patch chain remain intact. A future removal requires a
compatible fix in the relevant branch, API and profile-key checks, regeneration
of affected patches through `scripts/patchwork.py`, and the native regression
and mutation checks. In particular, a generic fix does not replace the custom
talent-reset hooks, personal earned-era admission or rated-arena team filters.

## Reproduce validation

The core patches use upstream `azerothcore/azerothcore-wotlk` commit
`a64665927de9d23cf81b0b623ee7117131f0919a`. The progression patch uses
`ZhengPeiRu21/mod-individual-progression` commit
`c87e666fc034978cffbb287f1be5e53df522539d`. Each format-patch export records its
base commit. Obtain checkouts containing those commits, then run:

```sh
python3 docs/upstream/checks.py \
  --core /path/to/azerothcore-wotlk \
  --progression /path/to/mod-individual-progression
```

The script extracts pristine snapshots, applies the exported patches and compiles
the proposed production methods with C++20, AddressSanitizer and
UndefinedBehaviorSanitizer. Reset-cost, battleground and filter checks reject the
unmodified upstream methods. The existing native formation fixture exercises
both its baseline and corrected source against the production spline validator.
No checkout, running realm or database is changed. All checks passed; a full
upstream server build has not been run.
