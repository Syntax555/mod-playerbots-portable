if(NOT PORTABLE_DIST_DIR OR NOT IS_DIRECTORY "${PORTABLE_DIST_DIR}")
    message(FATAL_ERROR "PORTABLE_DIST_DIR must point to a built distribution")
endif()

foreach(required startup.exe authserver.exe worldserver.exe legacy.dll msvcp140_atomic_wait.dll
    mysql/bin/mysqld.exe mysql/bin/mysql.exe mysql/bin/mysqladmin.exe)
    if(NOT EXISTS "${PORTABLE_DIST_DIR}/${required}")
        message(FATAL_ERROR "Cannot package an incomplete build: missing ${required}")
    endif()
endforeach()

# Client data arrives as pre-extracted files, and the server imports SQL itself.
# Clear optional tools from reused install directories as well as fresh builds.
foreach(optional_file dbimport.exe map_extractor.exe vmap4_extractor.exe
    vmap4_assembler.exe mmaps_generator.exe mmaps-config.yaml
    configs/dbimport.conf.dist dbimport.conf.dist)
    file(REMOVE "${PORTABLE_DIST_DIR}/${optional_file}")
endforeach()

# MySQL's maintenance/development clients are not used by the launcher. Preserve
# the server, SQL client, readiness/shutdown client and all runtime libraries.
file(GLOB mysql_executables "${PORTABLE_DIST_DIR}/mysql/bin/*.exe")
foreach(executable IN LISTS mysql_executables)
    get_filename_component(name "${executable}" NAME)
    if(NOT name STREQUAL "mysqld.exe" AND NOT name STREQUAL "mysql.exe" AND NOT name STREQUAL "mysqladmin.exe")
        file(REMOVE "${executable}")
    endif()
endforeach()

# MySQL headers, documentation and debug plugins are build inputs only. The
# MeCab full-text dictionaries serve a parser plugin that is never installed,
# and the *-debug.dll libraries need the debug C runtime and load nowhere.
file(REMOVE_RECURSE "${PORTABLE_DIST_DIR}/mysql/include" "${PORTABLE_DIST_DIR}/mysql/docs"
    "${PORTABLE_DIST_DIR}/mysql/lib/plugin/debug" "${PORTABLE_DIST_DIR}/mysql/lib/mecab")
file(GLOB mysql_debug_libraries "${PORTABLE_DIST_DIR}/mysql/bin/*-debug.dll")
if(mysql_debug_libraries)
    file(REMOVE ${mysql_debug_libraries})
endif()

file(GLOB_RECURSE development_files
    "${PORTABLE_DIST_DIR}/*.pdb" "${PORTABLE_DIST_DIR}/*.lib"
    "${PORTABLE_DIST_DIR}/*.exp" "${PORTABLE_DIST_DIR}/*.ilk")
if(development_files)
    file(REMOVE ${development_files})
endif()
