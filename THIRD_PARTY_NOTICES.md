# Third-party notices

The [MIT License](LICENSE) covers the portable launcher and build tooling.
The server, modules, addons and their dependencies retain their upstream
copyright notices and licenses. The MIT license does not replace those terms.
Local changes to upstream code retain the applicable source notices.

## Sources and versions

[versions.lock.json](versions.lock.json) records the source repository and exact
revision of each core, module, addon and client build dependency. It also lists
the ordered [local patches](patches/) applied to those sources. Use the manifest
and patches from the same repository commit as the downloaded build when
retrieving or rebuilding its source.

The server ZIP includes `versions.lock.json`, `patches/` and `licenses/`.
Client addons include their upstream license and `SOURCE_REVISION.txt`; the
combined EraTalents client pack includes dependency licenses and
`SOURCE_MANIFEST.json` with source revisions and patch hashes.

## Included projects

The paths below refer to the server ZIP unless indicated otherwise. A root
license file can coexist with notices applying to individual source files;
those notices remain applicable.

| Project | Upstream license and notices | Packaged notice |
| --- | --- | --- |
| [AzerothCore Playerbots core](https://github.com/mod-playerbots/azerothcore-wotlk) | GPL version 2 license text; source includes GPL-2.0-or-later and AGPL-3.0-or-later files. | `licenses/azerothcore-wotlk.txt`, `licenses/azerothcore-wotlk/AUTHORS`, `licenses/AGPL-3.0.txt` |
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | GPL version 2 license text and GPL-2.0-or-later source notices. | `licenses/mod-playerbots/LICENSE`, `licenses/mod-playerbots/AUTHORS.md` |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | GPL-2.0-or-later source notice. | `licenses/mod-autobalance/NOTICE.txt`, `licenses/GPL-2.0.txt` |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | MIT root license; source also includes GPL and AGPL notices. | `licenses/mod-individual-progression/LICENSE`, `licenses/GPL-2.0.txt`, `licenses/AGPL-3.0.txt` |
| [AH Bot Plus](https://github.com/NathanHandley/mod-ah-bot-plus) | GPL-2.0-or-later source notice. | `licenses/mod-ah-bot-plus/NOTICE.txt`, `licenses/GPL-2.0.txt` |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | AGPL-3.0-or-later upstream license declaration. | `licenses/mod-dungeon-clear/LICENSE`, `licenses/AGPL-3.0.txt` |
| [Quest Loot Party](https://github.com/pangolp/mod-quest-loot-party) | AGPL version 3 license text and source notice. | `licenses/mod-quest-loot-party/LICENSE`, `licenses/AGPL-3.0.txt` |
| [MultiBot Bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | No explicit license declaration at the locked revision; provenance notice retained. | `licenses/mod-multibot-bridge/NOTICE.txt` |
| [Token Turn-in](https://github.com/Zerathane/mod-token-turnin) | MIT root license; loader also carries an AGPL version 3 source notice. | `licenses/mod-token-turnin/LICENSE`, `licenses/AGPL-3.0.txt` |
| [Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents) | MIT upstream license; portable integration files also carry GPL-2.0-or-later notices. | `licenses/mod-era-talents/LICENSE`, `licenses/EraTalents/LICENSE`, `licenses/GPL-2.0.txt` |
| [MultiBot Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) | GPL version 3 upstream license text. | `licenses/MultiBot/LICENSE` and `addons/MultiBot/LICENSE` |
| [StormLib](https://github.com/ladislav-zezula/StormLib) | MIT; used to build and verify the client patch. | `licenses/StormLib.txt` in the combined client pack |
| [MySQL Community](https://www.mysql.com/products/community/) | GPL version 2 with the package's additional permissions and third-party terms. | `licenses/mysql/`, preserving package license and `INFO_BIN`/`INFO_SRC` files where present |
| [OpenSSL](https://www.openssl.org/) | Apache-2.0; provider notices are preserved separately. | `licenses/openssl/` |
| [Boost](https://www.boost.org/) | Boost Software License 1.0. | `licenses/boost/LICENSE_1_0.txt` |

The core also contains third-party libraries with their own license notices.
Their available license files and notices are preserved under
`licenses/core-dependencies/`, using paths from the pinned upstream `deps/`
directory. Additional notices remain in individual upstream source files.
These libraries and the bundled runtime dependencies are not covered by this
project's MIT license. Runtime dependency versions are pinned in the
[release workflow](.github/workflows/release.yml).

## Attribution

AzerothCore and Playerbots maintain their authorship records in the preserved
`AUTHORS` files listed above and their upstream Git histories. Module and addon
copyright notices remain in their license files, source files and documentation.
The manifest links to each project's source repository.

The MultiBot Bridge provenance notice records its upstream credits and the
absence of an explicit license at the locked revision. It does not grant or
infer permission to reuse that project's code.
