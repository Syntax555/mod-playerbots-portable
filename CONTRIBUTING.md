# Contributing

Report problems through [GitHub Issues](https://github.com/Syntax555/mod-playerbots-portable/issues). Include the build's source commit, client build, affected activity, relevant configuration and a short reproduction. Attach relevant log excerpts with account passwords removed.

For source changes, follow the [build guide](docs/building.md). Keep upstream revisions and patches reproducible through [versions.lock.json](versions.lock.json), preserve source license notices, and run checks appropriate to the change. Changes to progression should preserve normal XP, inventory, gold and per-character eligibility.

Documentation describes the current product. Keep the README focused on downloads, setup, features and useful limits. Put configuration and technical details in the linked guides. Release notes use [.github/RELEASE_TEMPLATE.md](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/RELEASE_TEMPLATE.md); avoid conversational updates, implementation history and lists of past versions.

Verified builds from `main` update the single **Latest** release. Pull requests and review branches produce build artifacts without publishing. Keep stable asset names and retain the previous download until the replacement packages have passed verification.
