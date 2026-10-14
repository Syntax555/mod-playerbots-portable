# Project identity and maintenance

**AzerothCore Playerbots Portable** is maintained by Syntax555 as an independent
continuation of [onur/mod-playerbots-portable](https://github.com/onur/mod-playerbots-portable/tree/fa643d6d63a53a4b5973298818e311523371543a), created by Onur Aslan.
It keeps the portable Windows foundation and integrates earned progression,
historical talents, bot group play, auction trading and automatic server updates.
Independent maintenance does not require removing GitHub's fork relationship.

## Origins and scope

The original project supplies the portable CMake build, Go startup supervisor,
database initialization, configuration setup and first-run server-data download.
Its contribution remains part of this project's history and [MIT License](../LICENSE).

The comparison below uses the original project's source at
[`fa643d6`](https://github.com/onur/mod-playerbots-portable/tree/fa643d6d63a53a4b5973298818e311523371543a) and this distribution's documented behavior. It describes
integration work, not ownership of the underlying game engine or module AI.

| Area | Original portable project | This continuation |
| --- | --- | --- |
| Windows distribution | [CMake packaging](https://github.com/onur/mod-playerbots-portable/blob/fa643d6d63a53a4b5973298818e311523371543a/CMakeLists.txt) of AzerothCore, Playerbots, MySQL and runtime libraries. | The same portable foundation, with pinned modules, separate matching client packages and [source manifests](module-versions.md). |
| Startup | [Go launcher](https://github.com/onur/mod-playerbots-portable/blob/fa643d6d63a53a4b5973298818e311523371543a/cmd/startup/main.go) initializes data and databases, configures paths and supervises server processes. | [Incremental server updates](updating.md) add file verification, transactional recovery and configuration migration that preserves custom values. |
| Progression and talents | [Core and Playerbots integration](https://github.com/onur/mod-playerbots-portable/blob/fa643d6d63a53a4b5973298818e311523371543a/.gitmodules), without a separate historical talent package. | [Individual Progression](changing-expansions.md) and [Era Talents](era-talents.md) are integrated with each character's earned era, paid training and selected historical class quests. |
| Dungeons and raids | [Playerbots group play](https://github.com/onur/mod-playerbots-portable/blob/fa643d6d63a53a4b5973298818e311523371543a/README.md). | [Dungeon Clear and Raid Clear integration](bot-dungeons.md): autonomous nearby five-bot parties for audited normal dungeons; player-led dungeon and raid clears with supported tactics. Autonomous raid recruitment is not implemented. |
| Bot economy | The bundled Playerbots behavior and configuration. | [Earned auction trading](earned-auctions.md) uses owned items, the bot's gold, ordinary auction fees and mailbox delivery. It does not promise a complete crafting economy. |
| Releases | [Tag-triggered Windows ZIP builds](https://github.com/onur/mod-playerbots-portable/blob/fa643d6d63a53a4b5973298818e311523371543a/.github/workflows/release.yml). | [Build checks](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/workflows/release.yml) and a [separate publisher](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/workflows/publish-latest.yml) maintain one rolling `latest` release with stable server/client assets and checksums. |

AzerothCore supplies the engine and native gameplay systems. Playerbots supplies
bot AI; Individual Progression, Era Talents, Dungeon Clear, Raid Clear and the
other included modules retain their authorship. This repository maintains the
integration patches, earned-play rules, distribution defaults, launcher changes
and verification around them. Exact dependencies and patch order are recorded
in the [dependency manifest](https://github.com/Syntax555/mod-playerbots-portable/blob/main/versions.lock.json) and [source guide](module-versions.md).

The launcher and build tooling retain the original MIT notice. Server, module,
addon and data licenses remain separate; see [third-party notices](../THIRD_PARTY_NOTICES.md).
Neither independent branding nor fork detachment changes these obligations.

Supported behavior and limits belong in the [README](../README.md),
[adaptations](adaptations.md) and [roadmap](todo.md). Automated checks do not
establish that every encounter, historical quest or large bot population has
been verified in a running realm.

## GitHub presentation

The repository name and location remain
`Syntax555/mod-playerbots-portable`. Keep existing release asset names and URLs;
the launcher and installed copies use them. A branding update needs no change
to the Git history, default branch, tags, releases or integrations.

These are suggested **About** values for the repository owner to review using
the gear beside **About** on the repository home page:

| Field | Suggested value |
| --- | --- |
| Description | Portable Windows AzerothCore server with earned Vanilla, TBC and Wrath progression, historical talents, autonomous bot dungeons, raid support, bot auction trading and automatic updates. |
| Website | `https://github.com/Syntax555/mod-playerbots-portable/releases/latest` |
| Topics | `azerothcore`, `playerbots`, `world-of-warcraft`, `wotlk`, `windows`, `portable`, `individual-progression`, `bot-ai` |

These fields are GitHub metadata, not repository files. Review and save only the
desired About fields. Keep the existing Codex/GitHub App access, Actions
permissions, secrets, environments, rules, branch settings and webhooks.
The README links to the existing build workflow, downloads and scoped license;
badges report only what their destinations establish.

## Fork relationship

**Keeping the fork relationship is the recommended option when preserving all
repository data and integrations is required.** It does not prevent independent
development, releases or a distinct project description.

GitHub's [official detachment guide](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/detaching-a-fork) documents **Leave fork
network** for public forks smaller than 1 GB with no child forks. It explicitly
warns that the resulting repository does **not** retain issues, pull requests,
wikis, stars, watchers, comments, child forks or other associated metadata.
Git commit metadata is preserved. Leaving is permanent, reconnection is not
supported, and some operations are briefly unavailable during detachment.

The guide does not guarantee preservation of the repository ID, release assets,
Actions history, secrets, webhooks or GitHub App/Codex connections. Retaining a
name or clone URL is not evidence that those resources will survive. The
documented self-service operation therefore does not meet a requirement to keep
all existing repository data and integrations.

If detachment remains desirable, the repository owner should:

1. Read the [current GitHub guidance](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/detaching-a-fork) and check the repository's
   eligibility. Do not initiate the operation while its effects are unresolved.
2. Contact [GitHub Support's fork request page](https://support.github.com/request/fork) and ask whether
   they can detach this repository in place while preserving its ID and URL,
   branches and tags, releases and asset URLs, issues and pull requests, wiki,
   stars and watchers, Actions history and permissions, secrets, environments,
   rules, webhooks and Codex/GitHub App access. Request explicit confirmation;
   the existence of a support form is not a preservation guarantee.
3. Preserve a read-only Git backup and inventory repository metadata, releases,
   assets and integration settings using supported export methods. A Git mirror
   or bundle backs up Git objects and refs, not GitHub metadata or integrations,
   and cannot restore secrets that GitHub does not expose for export.
4. Proceed only through a method whose documented effects satisfy the required
   preservation. The documented self-service location is **Settings → General
   → Danger Zone → Leave fork network**; its warning and name confirmation are
   the final destructive steps, not a harmless presentation setting.
5. If a satisfactory method is confirmed and performed by the owner, verify the
   repository identity, clone/download URLs, branches/tags, release assets,
   Actions and Codex integration before resuming normal maintenance.

If preservation cannot be confirmed, keep the fork relationship. Deleting and
recreating the repository, mirror-pushing over existing refs, rewriting history
or force-pushing is not part of this project's presentation procedure.
