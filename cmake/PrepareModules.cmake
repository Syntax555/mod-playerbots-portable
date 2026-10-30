# Used both by the superbuild and by `cmake -P cmake/PrepareModules.cmake`.
# Locked sources are fetched into .module-cache. The server always builds from
# the generated core checkout in prepared-core, which holds the module copies.
cmake_minimum_required(VERSION 3.19)

get_filename_component(PORTABLE_SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
file(MAKE_DIRECTORY "${PORTABLE_SOURCE_DIR}/.module-cache")
if(CMAKE_SCRIPT_MODE_FILE)
    file(LOCK "${PORTABLE_SOURCE_DIR}/.module-cache/prepare.lock" GUARD PROCESS TIMEOUT 60)
else()
    file(LOCK "${PORTABLE_SOURCE_DIR}/.module-cache/prepare.lock" GUARD FILE TIMEOUT 60)
endif()
find_package(Git REQUIRED)
file(READ "${PORTABLE_SOURCE_DIR}/versions.lock.json" PORTABLE_VERSIONS_JSON)
file(SHA256 "${CMAKE_CURRENT_LIST_FILE}" _prepare_script_hash)
if(NOT CMAKE_SCRIPT_MODE_FILE)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${PORTABLE_SOURCE_DIR}/versions.lock.json")
endif()
string(JSON _schema GET "${PORTABLE_VERSIONS_JSON}" schemaVersion)
if(NOT _schema EQUAL 1)
    message(FATAL_ERROR "Unsupported versions.lock.json schema: ${_schema}")
endif()
# Source changes are fork commits; a patch list would otherwise be ignored.
if(PORTABLE_VERSIONS_JSON MATCHES "\"patches\"[ \t\r\n]*:")
    message(FATAL_ERROR "versions.lock.json lists source patches; pin a fork commit instead")
endif()

function(portable_git)
    # Generated staging directories must not inherit the enclosing workspace's
    # Git repository. Sources marked text without an eol attribute follow
    # core.eol, which is CRLF on Windows; exports must keep the committed bytes.
    execute_process(COMMAND "${CMAKE_COMMAND}" -E env
        "GIT_CEILING_DIRECTORIES=${PORTABLE_SOURCE_DIR}/.module-cache"
        "${GIT_EXECUTABLE}" -c "core.autocrlf=false" -c "core.eol=lf" ${ARGN}
        RESULT_VARIABLE _result OUTPUT_VARIABLE _output ERROR_VARIABLE _error)
    if(NOT _result EQUAL 0)
        message(FATAL_ERROR "Git failed (${_result}): ${ARGN}\n${_output}${_error}")
    endif()
endfunction()

# Fetch only missing pinned commits; cached sources also work offline.
function(portable_fetch_source name url revision output_variable)
    string(LENGTH "${revision}" _revision_length)
    if(NOT name MATCHES "^[A-Za-z0-9_-]+$" OR NOT revision MATCHES "^[a-f0-9]+$"
        OR NOT _revision_length EQUAL 40
        OR NOT url MATCHES "^https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+[.]git$")
        message(FATAL_ERROR "Invalid pinned source in versions.lock.json: ${name}")
    endif()
    set(_source_dir "${PORTABLE_SOURCE_DIR}/.module-cache/${name}")
    if(NOT EXISTS "${_source_dir}/.git")
        file(MAKE_DIRECTORY "${_source_dir}")
        portable_git(init --quiet "${_source_dir}")
    endif()
    execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${_source_dir}" cat-file -e "${revision}^{commit}"
        RESULT_VARIABLE _has_revision OUTPUT_QUIET ERROR_QUIET)
    if(NOT _has_revision EQUAL 0)
        message(STATUS "Fetching pinned ${name} ${revision}")
        portable_git(-C "${_source_dir}" fetch --depth=1 "${url}" "${revision}")
    endif()
    set(${output_variable} "${_source_dir}" PARENT_SCOPE)
endfunction()

string(JSON _core_name GET "${PORTABLE_VERSIONS_JSON}" core name)
string(JSON _core_url GET "${PORTABLE_VERSIONS_JSON}" core url)
string(JSON _core_revision GET "${PORTABLE_VERSIONS_JSON}" core revision)
portable_fetch_source("${_core_name}" "${_core_url}" "${_core_revision}" PORTABLE_CORE_SOURCE_DIR)

# A local shared clone keeps the source cache intact and supplies the
# pinned Git revision to genrev.
set(_core_original "${PORTABLE_CORE_SOURCE_DIR}")
set(_core_target "${PORTABLE_SOURCE_DIR}/.module-cache/prepared-core")
set(_core_stamp "prepare: ${_prepare_script_hash}\n${_core_url}\n${_core_revision}\n")
set(_old_core_stamp "")
if(EXISTS "${_core_target}/.portable-source")
    file(READ "${_core_target}/.portable-source" _old_core_stamp)
elseif(EXISTS "${_core_target}")
    message(FATAL_ERROR "${_core_target} is not a generated portable core. Move it aside first.")
endif()
if(NOT _core_stamp STREQUAL _old_core_stamp)
    set(_core_stage "${PORTABLE_SOURCE_DIR}/.module-cache/staging-core")
    file(REMOVE_RECURSE "${_core_stage}")
    # A fetch-only cache has no branch; clone would otherwise treat it as empty.
    portable_git(-C "${_core_original}" update-ref refs/heads/portable-pinned "${_core_revision}")
    portable_git(clone --shared --no-checkout --branch portable-pinned --quiet "${_core_original}" "${_core_stage}")
    portable_git(-C "${_core_stage}" config core.autocrlf false)
    portable_git(-C "${_core_stage}" checkout --detach --quiet "${_core_revision}")
    file(WRITE "${_core_stage}/.portable-source" "${_core_stamp}")
    file(REMOVE_RECURSE "${_core_target}")
    file(RENAME "${_core_stage}" "${_core_target}")
    message(STATUS "Prepared AzerothCore ${_core_revision}")
endif()
set(PORTABLE_CORE_SOURCE_DIR "${_core_target}")

set(PORTABLE_MODULE_NAMES)
string(JSON _module_count LENGTH "${PORTABLE_VERSIONS_JSON}" modules)
math(EXPR _last_module "${_module_count} - 1")
foreach(_index RANGE 0 ${_last_module})
    string(JSON _name GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} name)
    string(JSON _url GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} url)
    string(JSON _revision GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} revision)
    if(NOT _name MATCHES "^mod-[a-z0-9-]+$")
        message(FATAL_ERROR "Invalid module name in versions.lock.json: ${_name}")
    endif()
    list(APPEND PORTABLE_MODULE_NAMES "${_name}")

    portable_fetch_source("${_name}" "${_url}" "${_revision}" _source_dir)

    set(_stamp "prepare: ${_prepare_script_hash}\n${_url}\n${_revision}\n")

    set(_target "${PORTABLE_CORE_SOURCE_DIR}/modules/${_name}")
    set(_stamp_file "${_target}/.portable-source")
    if(EXISTS "${_stamp_file}")
        file(READ "${_stamp_file}" _old_stamp)
        if(_stamp STREQUAL _old_stamp AND EXISTS "${_target}/src")
            message(STATUS "Pinned module ready: ${_name}")
            continue()
        endif()
    elseif(EXISTS "${_target}")
        message(FATAL_ERROR "${_target} exists and is not a generated portable module. Move it aside before preparing the pinned modules.")
    endif()

    # Archive committed files only. The source checkout and local edits never change.
    set(_stage "${PORTABLE_SOURCE_DIR}/.module-cache/staging-${_name}")
    set(_archive "${PORTABLE_SOURCE_DIR}/.module-cache/${_name}.tar")
    file(REMOVE_RECURSE "${_stage}")
    file(MAKE_DIRECTORY "${_stage}")
    portable_git(-C "${_source_dir}" archive --format=tar "--output=${_archive}" "${_revision}")
    execute_process(COMMAND "${CMAKE_COMMAND}" -E tar xf "${_archive}"
        WORKING_DIRECTORY "${_stage}" RESULT_VARIABLE _extract_result)
    if(NOT _extract_result EQUAL 0)
        message(FATAL_ERROR "Cannot extract pinned ${_name}")
    endif()
    file(WRITE "${_stage}/.portable-source" "${_stamp}")
    file(REMOVE_RECURSE "${_target}")
    file(RENAME "${_stage}" "${_target}")
    file(REMOVE "${_archive}")
    message(STATUS "Prepared pinned module: ${_name}")
endforeach()

# Generated copies that the lock no longer names are removed: AzerothCore
# compiles every directory under modules/, and packaging would omit their
# SQL and configuration. Directories without a preparation stamp are kept.
function(portable_remove_unlocked parent kind)
    file(GLOB _entries LIST_DIRECTORIES TRUE "${parent}/*")
    foreach(_entry IN LISTS _entries)
        get_filename_component(_entry_name "${_entry}" NAME)
        if(IS_DIRECTORY "${_entry}" AND EXISTS "${_entry}/.portable-source"
            AND NOT _entry_name IN_LIST ARGN)
            file(REMOVE_RECURSE "${_entry}")
            message(STATUS "Removed ${kind} no longer in versions.lock.json: ${_entry_name}")
        endif()
    endforeach()
endfunction()
portable_remove_unlocked("${PORTABLE_CORE_SOURCE_DIR}/modules" "module" ${PORTABLE_MODULE_NAMES})

# A prepared addon's TOC declares the locked interface, and every file it
# loads is a regular file inside the addon.
function(portable_check_addon_toc directory toc interface label)
    if(NOT EXISTS "${directory}/${toc}" OR IS_DIRECTORY "${directory}/${toc}")
        message(FATAL_ERROR "${label} is missing its TOC")
    endif()
    file(STRINGS "${directory}/${toc}" _toc_lines ENCODING UTF-8)
    # The client resolves addon paths without regard to case.
    file(GLOB_RECURSE _addon_files RELATIVE "${directory}" "${directory}/*")
    string(TOLOWER "${_addon_files}" _addon_files)
    set(_interface_matches FALSE)
    foreach(_line IN LISTS _toc_lines)
        string(STRIP "${_line}" _line)
        if(_line MATCHES "^##[ \t]*Interface[ \t]*:[ \t]*${interface}[ \t]*$")
            set(_interface_matches TRUE)
        endif()
        if(_line STREQUAL "" OR _line MATCHES "^#")
            continue()
        endif()
        string(REPLACE "\\" "/" _asset "${_line}")
        string(TOLOWER "${_asset}" _asset_key)
        if(IS_ABSOLUTE "${_asset}" OR _asset MATCHES "(^|/)[.][.]?(/|$)|:" OR NOT _asset_key IN_LIST _addon_files)
            message(FATAL_ERROR "${label} has a missing or invalid TOC asset: ${_asset}")
        endif()
    endforeach()
    if(NOT _interface_matches)
        message(FATAL_ERROR "${label} must declare WotLK Interface ${interface}")
    endif()
endfunction()

# Client addons are packaged for the player to copy into the WoW client.
# They never participate in the server build or download at server startup.
set(PORTABLE_CLIENT_ADDON_NAMES)
string(JSON _addon_count LENGTH "${PORTABLE_VERSIONS_JSON}" clientAddons)
if(_addon_count GREATER 0)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/ExportClientAddon.py" _addon_export_hash)
    if(NOT CMAKE_SCRIPT_MODE_FILE)
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/ExportClientAddon.py")
    endif()
    math(EXPR _last_addon "${_addon_count} - 1")
    foreach(_addon_index RANGE 0 ${_last_addon})
        string(JSON _addon_name GET "${PORTABLE_VERSIONS_JSON}" clientAddons ${_addon_index} name)
        string(JSON _addon_url GET "${PORTABLE_VERSIONS_JSON}" clientAddons ${_addon_index} url)
        string(JSON _addon_revision GET "${PORTABLE_VERSIONS_JSON}" clientAddons ${_addon_index} revision)
        string(JSON _addon_interface GET "${PORTABLE_VERSIONS_JSON}" clientAddons ${_addon_index} interface)
        string(JSON _addon_toc GET "${PORTABLE_VERSIONS_JSON}" clientAddons ${_addon_index} toc)
        string(JSON _addon_license GET "${PORTABLE_VERSIONS_JSON}" clientAddons ${_addon_index} license)
        string(LENGTH "${_addon_revision}" _addon_revision_length)
        if(NOT _addon_name MATCHES "^[A-Za-z0-9_-]+$" OR NOT _addon_revision MATCHES "^[a-f0-9]+$"
            OR NOT _addon_revision_length EQUAL 40 OR NOT _addon_interface EQUAL 30300
            OR NOT _addon_url MATCHES "^https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+[.]git$"
            OR NOT _addon_toc STREQUAL "${_addon_name}.toc"
            OR NOT _addon_license MATCHES "^[A-Za-z0-9_.-]+$")
            message(FATAL_ERROR "Invalid pinned WotLK client addon in versions.lock.json: ${_addon_name}")
        endif()
        list(APPEND PORTABLE_CLIENT_ADDON_NAMES "${_addon_name}")
        set(_addon_source "${PORTABLE_SOURCE_DIR}/.module-cache/client-addon-${_addon_name}")
        if(NOT EXISTS "${_addon_source}/.git")
            file(MAKE_DIRECTORY "${_addon_source}")
            portable_git(init --quiet "${_addon_source}")
        endif()
        execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${_addon_source}" cat-file -e "${_addon_revision}^{commit}"
            RESULT_VARIABLE _addon_has_revision OUTPUT_QUIET ERROR_QUIET)
        if(NOT _addon_has_revision EQUAL 0)
            message(STATUS "Fetching pinned client addon ${_addon_name} ${_addon_revision}")
            portable_git(-C "${_addon_source}" fetch --depth=1 "${_addon_url}" "${_addon_revision}")
        endif()

        set(_addon_target "${PORTABLE_SOURCE_DIR}/.module-cache/prepared-addons/${_addon_name}")
        set(_addon_stamp "prepare: ${_prepare_script_hash}\n${_addon_url}\n${_addon_revision}\ninterface: ${_addon_interface}\n")
        string(APPEND _addon_stamp "export: ${_addon_export_hash}\n")
        if(EXISTS "${_addon_target}" AND NOT EXISTS "${_addon_target}/.portable-source")
            message(FATAL_ERROR "${_addon_target} is not a generated portable client addon. Move it aside before preparing the pinned addon.")
        endif()

        # A matching stamp does not prove that mutable prepared assets are intact.
        # Re-export the small addon from the pinned commit on every preparation.
        set(_addon_stage "${PORTABLE_SOURCE_DIR}/.module-cache/staging-addon-${_addon_name}")
        set(_addon_archive "${PORTABLE_SOURCE_DIR}/.module-cache/client-addon-${_addon_name}.tar")
        file(REMOVE_RECURSE "${_addon_stage}")
        file(MAKE_DIRECTORY "${_addon_stage}" "${PORTABLE_SOURCE_DIR}/.module-cache/prepared-addons")
        portable_git(-C "${_addon_source}" archive --format=tar "--output=${_addon_archive}" "${_addon_revision}")
        execute_process(COMMAND "${CMAKE_COMMAND}" -E tar xf "${_addon_archive}"
            WORKING_DIRECTORY "${_addon_stage}" RESULT_VARIABLE _addon_extract_result)
        if(NOT _addon_extract_result EQUAL 0)
            message(FATAL_ERROR "Cannot extract pinned client addon ${_addon_name}")
        endif()
        file(REMOVE_RECURSE "${_addon_stage}/.github")
        file(REMOVE "${_addon_stage}/.gitignore" "${_addon_stage}/.coderabbit.yaml"
            "${_addon_stage}/AGENTS.md")
        execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_LIST_DIR}/ExportClientAddon.py"
            --repository "${PORTABLE_SOURCE_DIR}" --addon "${_addon_name}"
            --destination "${_addon_stage}" --manifest-only
            RESULT_VARIABLE _manifest_result ERROR_VARIABLE _manifest_error)
        if(NOT _manifest_result EQUAL 0)
            message(FATAL_ERROR "Cannot record client addon source provenance: ${_manifest_error}")
        endif()
        file(WRITE "${_addon_stage}/.portable-source" "${_addon_stamp}")
        file(REMOVE_RECURSE "${_addon_target}")
        file(RENAME "${_addon_stage}" "${_addon_target}")
        file(REMOVE "${_addon_archive}")

        if(NOT EXISTS "${_addon_target}/${_addon_toc}" OR NOT EXISTS "${_addon_target}/${_addon_license}"
            OR NOT EXISTS "${_addon_target}/README.md")
            message(FATAL_ERROR "Client addon ${_addon_name} is missing its TOC, upstream license or README")
        endif()
        portable_check_addon_toc("${_addon_target}" "${_addon_toc}" "${_addon_interface}" "Client addon ${_addon_name}")
        message(STATUS "Pinned client addon ready: ${_addon_name}")
    endforeach()
endif()
portable_remove_unlocked("${PORTABLE_SOURCE_DIR}/.module-cache/prepared-addons" "client addon"
    ${PORTABLE_CLIENT_ADDON_NAMES})


# Source-only integrations are prepared for local installation and fixtures.
# They deliberately stay outside clientAddons and the release ZIP pipeline.
string(JSON _source_addon_count ERROR_VARIABLE _source_addon_error LENGTH "${PORTABLE_VERSIONS_JSON}" sourceAddons)
if(_source_addon_error)
    set(_source_addon_count 0)
endif()
set(_source_addon_names)
if(_source_addon_count GREATER 0)
    math(EXPR _last_source_addon "${_source_addon_count} - 1")
    foreach(_index RANGE 0 ${_last_source_addon})
        string(JSON _name GET "${PORTABLE_VERSIONS_JSON}" sourceAddons ${_index} name)
        string(JSON _url GET "${PORTABLE_VERSIONS_JSON}" sourceAddons ${_index} url)
        string(JSON _source_revision GET "${PORTABLE_VERSIONS_JSON}" sourceAddons ${_index} revision)
        string(JSON _interface GET "${PORTABLE_VERSIONS_JSON}" sourceAddons ${_index} interface)
        string(JSON _toc GET "${PORTABLE_VERSIONS_JSON}" sourceAddons ${_index} toc)
        # An addon kept in a subdirectory of its repository names that folder.
        string(JSON _path ERROR_VARIABLE _path_error GET "${PORTABLE_VERSIONS_JSON}" sourceAddons ${_index} path)
        if(_path_error)
            set(_path "")
        endif()
        if(NOT _name MATCHES "^[A-Za-z0-9_-]+$" OR NOT _toc STREQUAL "${_name}.toc"
            OR NOT _interface EQUAL 30300 OR _name IN_LIST _source_addon_names
            OR _name IN_LIST PORTABLE_CLIENT_ADDON_NAMES
            OR (NOT _path_error AND NOT _path STREQUAL _name))
            message(FATAL_ERROR "Invalid or duplicate source-only client addon: ${_name}")
        endif()
        list(APPEND _source_addon_names "${_name}")
        portable_fetch_source("client-addon-${_name}" "${_url}" "${_source_revision}" _source)
        set(_stamp "prepare: ${_prepare_script_hash}\n${_url}\n${_source_revision}\ninterface: ${_interface}\npath: ${_path}\n")
        set(_target "${PORTABLE_SOURCE_DIR}/.module-cache/prepared-source-addons/${_name}")
        if(EXISTS "${_target}" AND NOT EXISTS "${_target}/.portable-source")
            message(FATAL_ERROR "${_target} is not a generated source-only addon. Move it aside first.")
        endif()
        set(_source_stage "${PORTABLE_SOURCE_DIR}/.module-cache/staging-source-addon-${_name}")
        set(_source_archive "${PORTABLE_SOURCE_DIR}/.module-cache/source-addon-${_name}.tar")
        file(REMOVE_RECURSE "${_source_stage}")
        file(MAKE_DIRECTORY "${_source_stage}" "${PORTABLE_SOURCE_DIR}/.module-cache/prepared-source-addons")
        portable_git(-C "${_source}" archive --format=tar "--output=${_source_archive}" "${_source_revision}")
        execute_process(COMMAND "${CMAKE_COMMAND}" -E tar xf "${_source_archive}"
            WORKING_DIRECTORY "${_source_stage}" RESULT_VARIABLE _extract_result)
        if(NOT _extract_result EQUAL 0)
            message(FATAL_ERROR "Cannot extract source-only client addon ${_name}")
        endif()
        set(_addon_stage "${_source_stage}")
        if(_path)
            set(_addon_stage "${_source_stage}/${_path}")
        endif()
        portable_check_addon_toc("${_addon_stage}" "${_toc}" "${_interface}" "Source-only client addon ${_name}")
        file(WRITE "${_addon_stage}/SOURCE_REVISION.txt" "${_source_revision}\n")
        file(WRITE "${_addon_stage}/.portable-source" "${_stamp}")
        file(REMOVE_RECURSE "${_target}")
        file(RENAME "${_addon_stage}" "${_target}")
        file(REMOVE_RECURSE "${_source_stage}")
        file(REMOVE "${_source_archive}")
        message(STATUS "Source-only client addon ready: ${_name}")
    endforeach()
endif()
portable_remove_unlocked("${PORTABLE_SOURCE_DIR}/.module-cache/prepared-source-addons" "source-only client addon"
    ${_source_addon_names})
