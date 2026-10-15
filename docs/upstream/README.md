# Generic upstream fixes

These proposals contain only generic fixes, exported with `git format-patch`
from clean upstream revisions. They are review artifacts, outside the ordered
runtime patch chain. Keep the local fixes until an accepted upstream revision
is pinned and the corresponding local hunks can be removed safely.

| Fix | Upstream offer | Review artifacts |
| --- | --- | --- |
| Formation velocity guard | [AzerothCore #28141](https://github.com/azerothcore/azerothcore-wotlk/issues/28141) | [Patch](formation-velocity.patch), [proposal](formation-velocity.md) |
| Talent reset cost underflow | [AzerothCore #28142](https://github.com/azerothcore/azerothcore-wotlk/issues/28142) | [Patch](talent-reset-cost.patch), [proposal](talent-reset-cost.md) |
| Empty random-battleground candidates | [AzerothCore #28143](https://github.com/azerothcore/azerothcore-wotlk/issues/28143) | [Patch](random-battleground.patch), [proposal](random-battleground.md) |
| Empty Individual Progression account filters | Submission blocked by GitHub integration permissions | [Patch](individual-progression-filters.patch), [proposal](individual-progression-filters.md) |

The three core offers include the complete minimal diff and validation results.
Creating a GitHub fork returned HTTP 403, so the proposals were offered as issues
instead of pull requests. Individual Progression issue creation and a comment on
the related [account-cache PR #1308](https://github.com/ZhengPeiRu21/mod-individual-progression/pull/1308)
both returned HTTP 403, `Resource not accessible by integration`. The prepared
Individual Progression proposal can be submitted unchanged with an account that
can write to that upstream repository:

```sh
gh api --method POST repos/ZhengPeiRu21/mod-individual-progression/issues \
  -f title='fix: skip account lookups for empty progression filters' \
  -F body=@docs/upstream/individual-progression-filters.md
```

The Individual Progression proposal only includes account classification and
character-creation filters. The local transition-quest changes, custom talent
reset hooks and earned-era arena selection rules are outside these proposals.

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
