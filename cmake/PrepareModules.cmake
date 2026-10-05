# Used both by the superbuild and by `cmake -P cmake/PrepareModules.cmake`.
# The submodules stay pristine; generated module copies are managed by this file.
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

function(portable_git)
    # Generated staging directories must not inherit the enclosing workspace's
    # Git repository: git apply would silently skip patches outside its subdir.
    execute_process(COMMAND "${CMAKE_COMMAND}" -E env
        "GIT_CEILING_DIRECTORIES=${PORTABLE_SOURCE_DIR}/.module-cache"
        "${GIT_EXECUTABLE}" ${ARGN}
        RESULT_VARIABLE _result OUTPUT_VARIABLE _output ERROR_VARIABLE _error)
    if(NOT _result EQUAL 0)
        message(FATAL_ERROR "Git failed (${_result}): ${ARGN}\n${_output}${_error}")
    endif()
endfunction()

string(JSON _core_source GET "${PORTABLE_VERSIONS_JSON}" core source)
string(JSON _core_revision GET "${PORTABLE_VERSIONS_JSON}" core revision)
set(PORTABLE_CORE_SOURCE_DIR "${PORTABLE_SOURCE_DIR}/${_core_source}")
execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${PORTABLE_CORE_SOURCE_DIR}" rev-parse HEAD
    RESULT_VARIABLE _core_result OUTPUT_VARIABLE _core_head ERROR_QUIET
    OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT _core_result EQUAL 0 OR NOT _core_head STREQUAL _core_revision)
    message(FATAL_ERROR "Initialize the pinned submodules first: git submodule update --init --recursive.\nExpected AzerothCore ${_core_revision}; found '${_core_head}'.")
endif()

set(PORTABLE_MODULE_NAMES)
string(JSON _module_count LENGTH "${PORTABLE_VERSIONS_JSON}" modules)
math(EXPR _last_module "${_module_count} - 1")
foreach(_index RANGE 0 ${_last_module})
    string(JSON _name GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} name)
    string(JSON _url GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} url)
    string(JSON _revision GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} revision)
    if(NOT _name MATCHES "^mod-[a-z0-9-]+$" OR NOT _revision MATCHES "^[a-f0-9]+$")
        message(FATAL_ERROR "Invalid module name or revision in versions.lock.json: ${_name}")
    endif()
    string(LENGTH "${_revision}" _revision_length)
    if(NOT _revision_length EQUAL 40 OR NOT _url MATCHES "^https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+[.]git$")
        message(FATAL_ERROR "Each module must have a full commit SHA and GitHub repository URL: ${_name}")
    endif()
    list(APPEND PORTABLE_MODULE_NAMES "${_name}")

    string(JSON _source ERROR_VARIABLE _source_error GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} source)
    if(_source_error)
        set(_source_dir "${PORTABLE_SOURCE_DIR}/.module-cache/${_name}")
        if(NOT EXISTS "${_source_dir}/.git")
            file(MAKE_DIRECTORY "${_source_dir}")
            portable_git(init --quiet "${_source_dir}")
        endif()
        execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${_source_dir}" cat-file -e "${_revision}^{commit}"
            RESULT_VARIABLE _has_revision OUTPUT_QUIET ERROR_QUIET)
        if(NOT _has_revision EQUAL 0)
            message(STATUS "Fetching pinned ${_name} ${_revision}")
            portable_git(-C "${_source_dir}" fetch --depth=1 "${_url}" "${_revision}")
        endif()
    else()
        set(_source_dir "${PORTABLE_SOURCE_DIR}/${_source}")
        execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${_source_dir}" rev-parse HEAD
            RESULT_VARIABLE _source_result OUTPUT_VARIABLE _source_head ERROR_QUIET
            OUTPUT_STRIP_TRAILING_WHITESPACE)
        if(NOT _source_result EQUAL 0 OR NOT _source_head STREQUAL _revision)
            message(FATAL_ERROR "Initialize the pinned submodules first: git submodule update --init --recursive.\nExpected ${_name} ${_revision}; found '${_source_head}'.")
        endif()
    endif()

    set(_patches)
    set(_stamp "prepare: ${_prepare_script_hash}\n${_url}\n${_revision}\n")
    string(JSON _patch_count ERROR_VARIABLE _patch_error LENGTH "${PORTABLE_VERSIONS_JSON}" modules ${_index} patches)
    if(NOT _patch_error AND _patch_count GREATER 0)
        math(EXPR _last_patch "${_patch_count} - 1")
        foreach(_patch_index RANGE 0 ${_last_patch})
            string(JSON _patch GET "${PORTABLE_VERSIONS_JSON}" modules ${_index} patches ${_patch_index})
            set(_patch_file "${PORTABLE_SOURCE_DIR}/${_patch}")
            if(NOT EXISTS "${_patch_file}")
                message(FATAL_ERROR "Missing module patch: ${_patch_file}")
            endif()
            if(NOT CMAKE_SCRIPT_MODE_FILE)
                set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_patch_file}")
            endif()
            file(SHA256 "${_patch_file}" _patch_hash)
            string(APPEND _stamp "${_patch}: ${_patch_hash}\n")
            # Windows checkouts created before the LF attribute can still have
            # CRLF patches. Apply an LF copy against the archived source files;
            # keep the checked-in patch and its dependency/hash unchanged.
            file(READ "${_patch_file}" _patch_contents)
            string(REPLACE "\r\n" "\n" _patch_contents "${_patch_contents}")
            file(MAKE_DIRECTORY "${PORTABLE_SOURCE_DIR}/.module-cache/patches")
            set(_prepared_patch "${PORTABLE_SOURCE_DIR}/.module-cache/patches/${_name}-${_patch_index}.patch")
            # file(WRITE) uses Windows text mode and would restore CRLF here.
            # Expand the contents once to preserve any literal @VAR@/${VAR}.
            # CONFIGURE adds a final LF, so remove one from the input first.
            string(REGEX REPLACE "\n$" "" _patch_contents "${_patch_contents}")
            file(CONFIGURE OUTPUT "${_prepared_patch}"
                CONTENT "@_patch_contents@" @ONLY NEWLINE_STYLE LF)
            list(APPEND _patches "${_prepared_patch}")
        endforeach()
    endif()

    set(_target "${PORTABLE_CORE_SOURCE_DIR}/modules/${_name}")
    set("PORTABLE_MODULE_SOURCE_${_name}" "${_target}")
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
    foreach(_patch_file IN LISTS _patches)
        execute_process(COMMAND "${CMAKE_COMMAND}" -E env
            "GIT_CEILING_DIRECTORIES=${PORTABLE_SOURCE_DIR}/.module-cache"
            "${GIT_EXECUTABLE}" -C "${_stage}" apply --numstat "${_patch_file}"
            RESULT_VARIABLE _patch_stat_result OUTPUT_VARIABLE _patch_stat
            ERROR_VARIABLE _patch_stat_error OUTPUT_STRIP_TRAILING_WHITESPACE)
        if(NOT _patch_stat_result EQUAL 0 OR _patch_stat STREQUAL "")
            message(FATAL_ERROR "Patch has no applicable files: ${_patch_file}\n${_patch_stat_error}")
        endif()
        portable_git(-C "${_stage}" apply --check "${_patch_file}")
        portable_git(-C "${_stage}" apply "${_patch_file}")
        portable_git(-C "${_stage}" apply --reverse --check "${_patch_file}")
    endforeach()
    file(WRITE "${_stage}/.portable-source" "${_stamp}")
    file(REMOVE_RECURSE "${_target}")
    file(RENAME "${_stage}" "${_target}")
    file(REMOVE "${_archive}")
    message(STATUS "Prepared pinned module: ${_name}")
endforeach()

# Client addons are packaged for the player to copy into the WoW client.
# They never participate in the server build or download at server startup.
set(PORTABLE_CLIENT_ADDON_NAMES)
string(JSON _addon_count LENGTH "${PORTABLE_VERSIONS_JSON}" clientAddons)
if(_addon_count GREATER 0)
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
        set("PORTABLE_CLIENT_ADDON_SOURCE_${_addon_name}" "${_addon_target}")
        set(_addon_stamp "prepare: ${_prepare_script_hash}\n${_addon_url}\n${_addon_revision}\ninterface: ${_addon_interface}\n")
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
        file(WRITE "${_addon_stage}/SOURCE_REVISION.txt" "${_addon_revision}\n")
        file(WRITE "${_addon_stage}/.portable-source" "${_addon_stamp}")
        file(REMOVE_RECURSE "${_addon_target}")
        file(RENAME "${_addon_stage}" "${_addon_target}")
        file(REMOVE "${_addon_archive}")

        if(NOT EXISTS "${_addon_target}/${_addon_toc}" OR NOT EXISTS "${_addon_target}/${_addon_license}"
            OR NOT EXISTS "${_addon_target}/README.md")
            message(FATAL_ERROR "Client addon ${_addon_name} is missing its TOC, upstream license or README")
        endif()
        file(STRINGS "${_addon_target}/${_addon_toc}" _addon_toc_lines ENCODING UTF-8)
        set(_addon_interface_matches FALSE)
        foreach(_addon_line IN LISTS _addon_toc_lines)
            string(STRIP "${_addon_line}" _addon_line)
            if(_addon_line MATCHES "^##[ \t]*Interface[ \t]*:[ \t]*${_addon_interface}[ \t]*$")
                set(_addon_interface_matches TRUE)
            endif()
            if(_addon_line STREQUAL "" OR _addon_line MATCHES "^#")
                continue()
            endif()
            string(REPLACE "\\" "/" _addon_asset "${_addon_line}")
            if(IS_ABSOLUTE "${_addon_asset}" OR _addon_asset MATCHES "(^|/)[.][.](/|$)"
                OR NOT EXISTS "${_addon_target}/${_addon_asset}")
                message(FATAL_ERROR "Client addon ${_addon_name} has a missing or invalid TOC asset: ${_addon_asset}")
            endif()
        endforeach()
        if(NOT _addon_interface_matches)
            message(FATAL_ERROR "Client addon ${_addon_name} must declare WotLK Interface ${_addon_interface}")
        endif()
        message(STATUS "Pinned client addon ready: ${_addon_name}")
    endforeach()
endif()
