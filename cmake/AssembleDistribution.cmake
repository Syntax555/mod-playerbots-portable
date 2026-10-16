cmake_minimum_required(VERSION 3.19)

if(NOT PORTABLE_SOURCE_DIR OR NOT PORTABLE_DIST_DIR)
    message(FATAL_ERROR "PORTABLE_SOURCE_DIR and PORTABLE_DIST_DIR are required")
endif()

set(core "${PORTABLE_CORE_SOURCE_DIR}")
if(NOT core)
    set(core "${PORTABLE_SOURCE_DIR}/.module-cache/prepared-core")
endif()
if(NOT IS_DIRECTORY "${core}/data/sql")
    message(FATAL_ERROR "Prepared AzerothCore SQL is missing: run cmake -P cmake/PrepareModules.cmake")
endif()
# Patches, documentation and module templates are source exports; replace them
# so renamed or removed files cannot survive. User *.conf files stay untouched.
file(REMOVE_RECURSE "${PORTABLE_DIST_DIR}/patches" "${PORTABLE_DIST_DIR}/docs")
file(GLOB old_module_templates "${PORTABLE_DIST_DIR}/configs/modules/*.conf.dist")
if(old_module_templates)
    file(REMOVE ${old_module_templates})
endif()
file(MAKE_DIRECTORY "${PORTABLE_DIST_DIR}/src/data" "${PORTABLE_DIST_DIR}/configs/modules"
    "${PORTABLE_DIST_DIR}/licenses" "${PORTABLE_DIST_DIR}/patches")
# These are generated source exports, not the live MySQL data or configuration.
# Replace them so deleted migrations and SQL from removed modules cannot survive.
file(REMOVE_RECURSE "${PORTABLE_DIST_DIR}/src/data/sql")
file(GLOB old_module_sql "${PORTABLE_DIST_DIR}/src/modules/*/data/sql")
foreach(sql_dir IN LISTS old_module_sql)
    file(REMOVE_RECURSE "${sql_dir}")
endforeach()
# The updater reads base/, archive/, custom/ and updates/; old/ is history it
# never scans or records, so it stays out of the package.
file(COPY "${core}/data/sql" DESTINATION "${PORTABLE_DIST_DIR}/src/data"
    FILES_MATCHING PATTERN "*.sql" REGEX "/data/sql/old$" EXCLUDE)
file(COPY "${core}/LICENSE" DESTINATION "${PORTABLE_DIST_DIR}/licenses")
file(RENAME "${PORTABLE_DIST_DIR}/licenses/LICENSE" "${PORTABLE_DIST_DIR}/licenses/azerothcore-wotlk.txt")

# Preserve bundled library notices, including grants embedded in source headers.
set(core_dependency_notices "${PORTABLE_DIST_DIR}/licenses/core-dependencies")
file(REMOVE_RECURSE "${core_dependency_notices}")
file(GLOB_RECURSE dependency_files LIST_DIRECTORIES FALSE RELATIVE "${core}/deps" "${core}/deps/*")
foreach(relative IN LISTS dependency_files)
    get_filename_component(filename "${relative}" NAME)
    string(TOUPPER "${filename}" notice_name)
    if(notice_name MATCHES "^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT|AUTHORS)"
        OR relative MATCHES "^utf8cpp/utf8(/.*)?[.]h$"
        OR relative STREQUAL "zlib/zlib.h"
        OR relative STREQUAL "gsoap/stdsoap2.h"
        OR relative STREQUAL "gsoap/soapH.h"
        OR relative STREQUAL "fkYAML/fkYAML/node.hpp"
        OR relative STREQUAL "g3dlite/source/license.cpp")
        get_filename_component(parent "${relative}" DIRECTORY)
        file(MAKE_DIRECTORY "${core_dependency_notices}/${parent}")
        configure_file("${core}/deps/${relative}"
            "${core_dependency_notices}/${relative}" COPYONLY)
    endif()
endforeach()

foreach(app authserver worldserver)
    file(COPY "${core}/src/server/apps/${app}/${app}.conf.dist"
        DESTINATION "${PORTABLE_DIST_DIR}/configs")
endforeach()

file(READ "${PORTABLE_SOURCE_DIR}/versions.lock.json" lock)
string(JSON module_count LENGTH "${lock}" modules)
math(EXPR last_module "${module_count} - 1")
foreach(index RANGE 0 ${last_module})
    string(JSON name GET "${lock}" modules ${index} name)
    set(module "${core}/modules/${name}")
    if(NOT IS_DIRECTORY "${module}/src")
        message(FATAL_ERROR "Prepared module is missing: ${name}")
    endif()
    if(IS_DIRECTORY "${module}/data/sql")
        file(MAKE_DIRECTORY "${PORTABLE_DIST_DIR}/src/modules/${name}/data")
        file(COPY "${module}/data/sql" DESTINATION "${PORTABLE_DIST_DIR}/src/modules/${name}/data"
            FILES_MATCHING PATTERN "*.sql")
    endif()
    file(GLOB configs "${module}/conf/*.conf.dist")
    if(NOT configs)
        message(FATAL_ERROR "Module configuration template is missing: ${name}")
    endif()
    file(COPY ${configs} DESTINATION "${PORTABLE_DIST_DIR}/configs/modules")
    file(GLOB licenses "${module}/LICENSE*" "${module}/COPYING*")
    if(licenses)
        file(MAKE_DIRECTORY "${PORTABLE_DIST_DIR}/licenses/${name}")
        file(COPY ${licenses} DESTINATION "${PORTABLE_DIST_DIR}/licenses/${name}")
    elseif(NOT IS_DIRECTORY "${PORTABLE_SOURCE_DIR}/licenses/${name}")
        message(FATAL_ERROR "Missing upstream license notice for ${name}")
    endif()
endforeach()

# Client addons are separate release downloads. Startup embeds its defaults.
# Clear exports from previous assemblies without touching live configuration.
file(REMOVE_RECURSE "${PORTABLE_DIST_DIR}/addons" "${PORTABLE_DIST_DIR}/defaults")
string(JSON addon_count LENGTH "${lock}" clientAddons)
if(addon_count GREATER 0)
    math(EXPR last_addon "${addon_count} - 1")
    foreach(index RANGE 0 ${last_addon})
        string(JSON name GET "${lock}" clientAddons ${index} name)
        file(REMOVE_RECURSE "${PORTABLE_DIST_DIR}/licenses/${name}")
    endforeach()
endif()
file(REMOVE "${PORTABLE_DIST_DIR}/CONTRIBUTING.md")
file(COPY "${PORTABLE_SOURCE_DIR}/licenses/" DESTINATION "${PORTABLE_DIST_DIR}/licenses")
file(COPY "${PORTABLE_SOURCE_DIR}/docs/" DESTINATION "${PORTABLE_DIST_DIR}/docs"
    PATTERN "building.md" EXCLUDE PATTERN "upstream" EXCLUDE)
# Compare manifest contents rather than timestamps when assembling again.
configure_file("${PORTABLE_SOURCE_DIR}/versions.lock.json"
    "${PORTABLE_DIST_DIR}/versions.lock.json" COPYONLY)
foreach(document README.md THIRD_PARTY_NOTICES.md)
    configure_file("${PORTABLE_SOURCE_DIR}/${document}"
        "${PORTABLE_DIST_DIR}/${document}" COPYONLY)
endforeach()
# The MIT License covers the launcher and build tooling, not the distribution
# it sits in. The packaged copy states that scope above the unchanged text.
file(READ "${PORTABLE_SOURCE_DIR}/LICENSE" launcher_license)
string(REPLACE "\r\n" "\n" launcher_license "${launcher_license}")
string(REGEX REPLACE "\n+$" "" launcher_license "${launcher_license}")
set(license_scope "This MIT License covers only the portable launcher (startup.exe) and the
build tooling of mod-playerbots-portable. The server, modules, addons, MySQL,
OpenSSL, Boost and the other bundled components keep their own licenses; see
THIRD_PARTY_NOTICES.md and licenses/.")
file(CONFIGURE OUTPUT "${PORTABLE_DIST_DIR}/LICENSE"
    CONTENT "@license_scope@\n\n@launcher_license@" @ONLY NEWLINE_STYLE LF)
if(NOT PORTABLE_RELEASE_REVISION)
    find_program(PORTABLE_GIT_EXECUTABLE git REQUIRED)
    execute_process(COMMAND "${PORTABLE_GIT_EXECUTABLE}" -C "${PORTABLE_SOURCE_DIR}" rev-parse HEAD
        OUTPUT_VARIABLE PORTABLE_RELEASE_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE revision_result)
    if(NOT revision_result EQUAL 0)
        message(FATAL_ERROR "Cannot determine the portable release source revision")
    endif()
endif()
string(LENGTH "${PORTABLE_RELEASE_REVISION}" revision_length)
if(NOT revision_length EQUAL 40 OR NOT PORTABLE_RELEASE_REVISION MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "PORTABLE_RELEASE_REVISION must be a full lowercase Git commit SHA")
endif()
if(NOT PACKAGE_VERSION)
    set(PACKAGE_VERSION "dev")
endif()
if(NOT PACKAGE_VERSION MATCHES "^[A-Za-z0-9._-]+$")
    message(FATAL_ERROR "PACKAGE_VERSION contains unsupported characters")
endif()
file(WRITE "${PORTABLE_DIST_DIR}/portable-release.json"
    "{\"schema\":1,\"revision\":\"${PORTABLE_RELEASE_REVISION}\",\"package\":\"mod-playerbots-portable-${PACKAGE_VERSION}.zip\",\"version\":\"${PACKAGE_VERSION}\"}\n")
file(GLOB patches "${PORTABLE_SOURCE_DIR}/patches/*.patch")
if(patches)
    file(COPY ${patches} DESTINATION "${PORTABLE_DIST_DIR}/patches")
endif()
message(STATUS "Portable distribution assembled at ${PORTABLE_DIST_DIR}")
