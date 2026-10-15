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

The paths below refer to the server ZIP unless indicated otherwise. Client
addon notices are included in their separate packages. A root license file can
coexist with notices applying to individual source files; those notices remain
applicable.

| Project | Upstream license and notices | Packaged notice |
| --- | --- | --- |
| [AzerothCore Playerbots core](https://github.com/mod-playerbots/azerothcore-wotlk) | GPL version 2 license text; source includes GPL-2.0-or-later and AGPL-3.0-or-later files. | `licenses/azerothcore-wotlk.txt`, `licenses/azerothcore-wotlk/AUTHORS`, `licenses/AGPL-3.0.txt` |
| [Playerbots](https://github.com/mod-playerbots/mod-playerbots) | GPL version 2 license text and GPL-2.0-or-later source notices. | `licenses/mod-playerbots/LICENSE`, `licenses/mod-playerbots/AUTHORS.md` |
| [AutoBalance](https://github.com/azerothcore/mod-autobalance) | GPL-2.0-or-later source notice. | `licenses/mod-autobalance/NOTICE.txt`, `licenses/GPL-2.0.txt` |
| [Individual Progression](https://github.com/ZhengPeiRu21/mod-individual-progression) | MIT root license; source also includes GPL and AGPL notices. | Server: `licenses/mod-individual-progression/LICENSE`, `licenses/GPL-2.0.txt`, `licenses/AGPL-3.0.txt`. Combined client pack, for its base `patch-V` archive: `licenses/mod-individual-progression.txt`. |
| [Dungeon Clear](https://github.com/jrad7/mod-dungeon-clear) | AGPL-3.0-or-later upstream license declaration. | `licenses/mod-dungeon-clear/LICENSE`, `licenses/AGPL-3.0.txt` |
| [Raid Clear](https://github.com/buildthehomelab/wow-mod-raid-clear) | MIT upstream license text. | `licenses/mod-raid-clear/LICENSE` |
| [Quest Loot Party](https://github.com/pangolp/mod-quest-loot-party) | AGPL version 3 license text and source notice. | `licenses/mod-quest-loot-party/LICENSE`, `licenses/AGPL-3.0.txt` |
| [World Buff Bots](https://github.com/Rockhopper1776/mod-world-buff-bots) | AGPL version 3 declaration in the upstream README. | `licenses/mod-world-buff-bots/NOTICE.txt`, `licenses/AGPL-3.0.txt` |
| [Era Events](https://github.com/buildthehomelab/wow-mod-era-events) | MIT upstream license text. | `licenses/mod-era-events/LICENSE` |
| [LFG Progression](https://github.com/buildthehomelab/wow-mod-lfg-progression) | AGPL version 3 upstream license text. | `licenses/mod-lfg-progression/LICENSE`, `licenses/AGPL-3.0.txt` |
| [MultiBot Bridge](https://github.com/Wishmaster117/mod-multibot-bridge) | No explicit license declaration at the locked revision; provenance notice retained. | `licenses/mod-multibot-bridge/NOTICE.txt` |
| [Era Talents](https://github.com/lathcf/azerothcore-mod-era-talents) | MIT upstream license; portable integration files also carry GPL-2.0-or-later notices. | Server: `licenses/mod-era-talents/LICENSE`, `licenses/GPL-2.0.txt`. Combined client pack: `Interface/AddOns/EraTalents/LICENSE`, `licenses/mod-era-talents.txt`. |
| [MultiBot Chatless](https://github.com/Wishmaster117/MultiBot-Chatless) | GPL version 3 upstream license text. | `MultiBot/LICENSE` in the separate addon ZIP. |
| [StormLib](https://github.com/ladislav-zezula/StormLib) | MIT; used to build and verify the client patch. | `licenses/StormLib.txt` in the combined client pack |
| [CMaNGOS Classic DB](https://github.com/cmangos/classic-db) and [TBC DB](https://github.com/cmangos/tbc-db) | GPL version 3 project license texts; historical quest and trainer data retain their original terms. | `licenses/historical-class-data/NOTICE.txt`, `licenses/GPL-3.0.txt` in the server and combined client pack |
| [CMaNGOS Classic core](https://github.com/cmangos/mangos-classic) and [TBC core](https://github.com/cmangos/mangos-tbc) | GPL version 2 root texts and GPL-2.0-or-later source notices; historical spell corrections retain their source notices. | `licenses/historical-class-data/NOTICE.txt`, `licenses/GPL-2.0.txt` in the server and combined client pack |
| [German client text](https://github.com/Haeniken/TrinityCore-3.3.5-data-multilang) | Extracted WoW 3.3.5a client text; it retains its original terms. Neither this project's MIT license nor the repository's code license applies to it. | `licenses/client-locales.txt` in the combined client pack |
| [wowgaming client-data](https://github.com/wowgaming/client-data) | Extracted WoW client data (DBC, maps, vmaps, mmaps); it retains its original terms. | Not packaged; downloaded on first start |
| [MySQL Community](https://www.mysql.com/products/community/) | GPL version 2 with the package's additional permissions and third-party terms. | `licenses/mysql/`, preserving package license and `INFO_BIN`/`INFO_SRC` files where present |
| [OpenSSL](https://www.openssl.org/) | Apache-2.0; provider notices are preserved separately. | `licenses/openssl/` |
| [Boost](https://www.boost.org/) | Boost Software License 1.0. | `licenses/boost/LICENSE_1_0.txt` |
| [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) | Distributable code under the Microsoft Visual Studio license terms. | Runtime DLLs at the ZIP root and in `mysql/bin`; no separate notice file |

The core also contains third-party libraries with their own license notices.
Their available license files and notices are preserved under
`licenses/core-dependencies/`, using paths from the pinned upstream `deps/`
directory. Additional notices remain in individual upstream source files.
These libraries and the bundled runtime dependencies are not covered by this
project's MIT license. The [bundled runtime versions](docs/module-versions.md#bundled-runtime)
are listed with the build provenance; the
[release workflow](https://github.com/Syntax555/mod-playerbots-portable/blob/main/.github/workflows/release.yml)
pins their download checksums.

## Attribution

AzerothCore and Playerbots maintain their authorship records in the preserved
`AUTHORS` files listed above and their upstream Git histories. Module and addon
copyright notices remain in their license files, source files and documentation.
The manifest links to each project's source repository.

The MultiBot Bridge provenance notice records its upstream credits and the
absence of an explicit license at the locked revision. It does not grant or
infer permission to reuse that project's code.
