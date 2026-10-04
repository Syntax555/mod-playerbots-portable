cmake_minimum_required(VERSION 3.19)

project(PlayerbotsWorkspace NONE)

include(ExternalProject)
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/PrepareModules.cmake")

# 1. Install prefix configuration (default: dist/ in repository root)
if(NOT DEFINED CMAKE_INSTALL_PREFIX OR CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
    set(CMAKE_INSTALL_PREFIX "${CMAKE_CURRENT_SOURCE_DIR}/dist" CACHE PATH "Install directory prefix" FORCE)
endif()

# Find Go compiler. A Windows ZIP must include the launcher.
find_program(GO_EXECUTABLE go REQUIRED)

# 2. Set MySQL, Boost, and OpenSSL paths from environment variables
set(MYSQL_ROOT_DIR "$ENV{MYSQL_ROOT_DIR}" CACHE PATH "MySQL root directory")
set(BOOST_ROOT_DIR "$ENV{BOOST_ROOT_DIR}" CACHE PATH "Boost root directory")
set(OPENSSL_ROOT_DIR "$ENV{OPENSSL_ROOT_DIR}" CACHE PATH "OpenSSL root directory")

# Normalize paths to absolute paths with forward slashes
if(MYSQL_ROOT_DIR)
    get_filename_component(MYSQL_ROOT_DIR "${MYSQL_ROOT_DIR}" ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
    file(TO_CMAKE_PATH "${MYSQL_ROOT_DIR}" MYSQL_ROOT_DIR)
    set(MYSQL_ROOT_DIR "${MYSQL_ROOT_DIR}" CACHE PATH "MySQL root directory" FORCE)
endif()
if(BOOST_ROOT_DIR)
    get_filename_component(BOOST_ROOT_DIR "${BOOST_ROOT_DIR}" ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
    file(TO_CMAKE_PATH "${BOOST_ROOT_DIR}" BOOST_ROOT_DIR)
    set(BOOST_ROOT_DIR "${BOOST_ROOT_DIR}" CACHE PATH "Boost root directory" FORCE)
endif()
if(OPENSSL_ROOT_DIR)
    get_filename_component(OPENSSL_ROOT_DIR "${OPENSSL_ROOT_DIR}" ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
    file(TO_CMAKE_PATH "${OPENSSL_ROOT_DIR}" OPENSSL_ROOT_DIR)
    set(OPENSSL_ROOT_DIR "${OPENSSL_ROOT_DIR}" CACHE PATH "OpenSSL root directory" FORCE)
endif()
if(CMAKE_INSTALL_PREFIX)
    get_filename_component(CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}" ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
    file(TO_CMAKE_PATH "${CMAKE_INSTALL_PREFIX}" CMAKE_INSTALL_PREFIX_CLEAN)
    set(CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX_CLEAN}" CACHE PATH "Install directory prefix" FORCE)
endif()

if(NOT DEFINED PACKAGE_VERSION)
    if(DEFINED ENV{PACKAGE_VERSION})
        set(PACKAGE_VERSION "$ENV{PACKAGE_VERSION}")
    else()
        set(PACKAGE_VERSION "dev")
    endif()
endif()
set(PACKAGE_VERSION "${PACKAGE_VERSION}" CACHE STRING "Package version for ZIP archives")
set(PACKAGE_OUTPUT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/output" CACHE PATH "Directory for built packages and installers")

message(STATUS "=== Playerbots Workspace Build Configuration ===")
message(STATUS "  Version        : ${PACKAGE_VERSION}")
message(STATUS "  Install Prefix : ${CMAKE_INSTALL_PREFIX_CLEAN}")
message(STATUS "  Output Dir     : ${PACKAGE_OUTPUT_DIR}")
message(STATUS "  MySQL Root     : ${MYSQL_ROOT_DIR}")
message(STATUS "  Boost Root     : ${BOOST_ROOT_DIR}")
message(STATUS "  OpenSSL Root   : ${OPENSSL_ROOT_DIR}")
message(STATUS "  Go Compiler    : ${GO_EXECUTABLE}")

# 3. Prepare cmake arguments for azerothcore-wotlk
set(ACORE_CMAKE_ARGS
    "-DCMAKE_POLICY_DEFAULT_CMP0175=OLD"
    "-DCMAKE_POLICY_DEFAULT_CMP0153=OLD"
    "-DCMAKE_POLICY_DEFAULT_CMP0144=NEW"
    "-DCMAKE_POLICY_DEFAULT_CMP0167=OLD"
    "-DCMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX_CLEAN}"
    "-DWITH_WARNINGS=1"
    "-DTOOLS_BUILD=all"
    "-DSCRIPTS=static"
    "-DMODULES=static"
    "-DBoost_USE_STATIC_LIBS=ON"
)

if(CMAKE_BUILD_TYPE)
    list(APPEND ACORE_CMAKE_ARGS "-DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}")
endif()

if(MYSQL_ROOT_DIR)
    list(APPEND ACORE_CMAKE_ARGS
        "-DMYSQL_ROOT_DIR=${MYSQL_ROOT_DIR}"
        "-DMYSQL_INCLUDE_DIR=${MYSQL_ROOT_DIR}/include"
        "-DMYSQL_LIBRARY=${MYSQL_ROOT_DIR}/lib/libmysql.lib"
    )
endif()

if(BOOST_ROOT_DIR)
    list(APPEND ACORE_CMAKE_ARGS
        "-DBOOST_ROOT=${BOOST_ROOT_DIR}"
        "-DBoost_ROOT=${BOOST_ROOT_DIR}"
    )
endif()

if(OPENSSL_ROOT_DIR)
    list(APPEND ACORE_CMAKE_ARGS
        "-DOPENSSL_ROOT_DIR=${OPENSSL_ROOT_DIR}"
        "-DOPENSSL_INCLUDE_DIR=${OPENSSL_ROOT_DIR}/include"
        "-DOPENSSL_CRYPTO_LIBRARY=${OPENSSL_ROOT_DIR}/lib/libcrypto.lib"
        "-DOPENSSL_SSL_LIBRARY=${OPENSSL_ROOT_DIR}/lib/libssl.lib"
    )
endif()

# 4. Superbuild AzerothCore and all pinned modules.
ExternalProject_Add(azerothcore
    SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/azerothcore-wotlk"
    BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}/azerothcore-build"
    CMAKE_ARGS ${ACORE_CMAKE_ARGS}
    BUILD_ALWAYS 1
    INSTALL_DIR "${CMAKE_INSTALL_PREFIX_CLEAN}"
)

# 5. Assemble every module's SQL, config templates, defaults and licenses.
ExternalProject_Add_Step(azerothcore assemble_distribution
    COMMAND ${CMAKE_COMMAND}
        "-DPORTABLE_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}"
        "-DPORTABLE_DIST_DIR=${CMAKE_INSTALL_PREFIX_CLEAN}"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/AssembleDistribution.cmake"
    DEPENDEES install
    COMMENT "Assembling portable configuration, module SQL and documentation"
)

if(WIN32)
    foreach(required_path
        "${MYSQL_ROOT_DIR}/bin/mysqld.exe"
        "${MYSQL_ROOT_DIR}/bin/mysql.exe"
        "${MYSQL_ROOT_DIR}/bin/mysqladmin.exe"
        "${MYSQL_ROOT_DIR}/lib/libmysql.dll"
        "${OPENSSL_ROOT_DIR}/bin/libcrypto-3-x64.dll"
        "${OPENSSL_ROOT_DIR}/bin/libssl-3-x64.dll"
    )
        if(NOT EXISTS "${required_path}")
            message(FATAL_ERROR "Missing required portable runtime dependency: ${required_path}")
        endif()
    endforeach()
    # Collect DLLs to copy
    set(DLL_COPY_COMMANDS)
    if(EXISTS "${MYSQL_ROOT_DIR}/lib/libmysql.dll")
        list(APPEND DLL_COPY_COMMANDS
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${MYSQL_ROOT_DIR}/lib/libmysql.dll"
                "${CMAKE_INSTALL_PREFIX_CLEAN}/libmysql.dll"
        )
    endif()

    if(EXISTS "${OPENSSL_ROOT_DIR}/bin/libcrypto-3-x64.dll")
        list(APPEND DLL_COPY_COMMANDS
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${OPENSSL_ROOT_DIR}/bin/libcrypto-3-x64.dll"
                "${CMAKE_INSTALL_PREFIX_CLEAN}/libcrypto-3-x64.dll"
        )
    endif()

    if(EXISTS "${OPENSSL_ROOT_DIR}/bin/libssl-3-x64.dll")
        list(APPEND DLL_COPY_COMMANDS
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${OPENSSL_ROOT_DIR}/bin/libssl-3-x64.dll"
                "${CMAKE_INSTALL_PREFIX_CLEAN}/libssl-3-x64.dll"
        )
    endif()

    if(EXISTS "${OPENSSL_ROOT_DIR}/lib/ossl-modules/legacy.dll")
        list(APPEND DLL_COPY_COMMANDS
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${OPENSSL_ROOT_DIR}/lib/ossl-modules/legacy.dll"
                "${CMAKE_INSTALL_PREFIX_CLEAN}/legacy.dll"
        )
    endif()

    if(DLL_COPY_COMMANDS)
        ExternalProject_Add_Step(azerothcore copy_runtime_dlls
            ${DLL_COPY_COMMANDS}
            DEPENDEES install
            COMMENT "Copying runtime Windows DLLs (MySQL, OpenSSL) to ${CMAKE_INSTALL_PREFIX_CLEAN}"
        )
    endif()

    # Copy and prune MySQL server directory
    if(IS_DIRECTORY "${MYSQL_ROOT_DIR}")
        ExternalProject_Add_Step(azerothcore copy_mysql_distribution
            COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${MYSQL_ROOT_DIR}"
                "${CMAKE_INSTALL_PREFIX_CLEAN}/mysql"
            COMMAND ${CMAKE_COMMAND}
                "-DMYSQL_DIST_DIR=${CMAKE_INSTALL_PREFIX_CLEAN}/mysql"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/CleanMySQLDist.cmake"
            DEPENDEES install
            COMMENT "Copying and pruning MySQL server distribution in ${CMAKE_INSTALL_PREFIX_CLEAN}/mysql"
        )
    endif()

    # Build Go startup launcher
    if(GO_EXECUTABLE)
        ExternalProject_Add_Step(azerothcore build_startup_tool
            COMMAND ${GO_EXECUTABLE} build -o "${CMAKE_INSTALL_PREFIX_CLEAN}/startup.exe" "./cmd/startup"
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            DEPENDEES install
            COMMENT "Building startup executable: ${CMAKE_INSTALL_PREFIX_CLEAN}/startup.exe"
        )
    endif()

    # 6. Portable ZIP Packaging Target
    set(PORTABLE_ZIP_FILE "${PACKAGE_OUTPUT_DIR}/mod-playerbots-portable-${PACKAGE_VERSION}.zip")

    find_program(SEVEN_ZIP_EXECUTABLE NAMES 7z 7za
        PATHS "C:/Program Files/7-Zip"
              "C:/Program Files (x86)/7-Zip"
              "$ENV{ProgramFiles}/7-Zip"
              "$ENV{ProgramFiles\(x86\)}/7-Zip"
        DOC "Path to 7-Zip executable"
    )

    if(SEVEN_ZIP_EXECUTABLE)
        message(STATUS "  7-Zip          : ${SEVEN_ZIP_EXECUTABLE} (Maximum Ultra Compression -mx=9)")

        add_custom_target(package_zip
            COMMAND ${CMAKE_COMMAND}
                "-DPORTABLE_DIST_DIR=${CMAKE_INSTALL_PREFIX_CLEAN}"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/PrunePortableDistribution.cmake"
            COMMAND ${CMAKE_COMMAND} -E make_directory "${PACKAGE_OUTPUT_DIR}"
            COMMAND ${CMAKE_COMMAND} -E rm -f "${PORTABLE_ZIP_FILE}"
            COMMAND "${SEVEN_ZIP_EXECUTABLE}" a -tzip -mx=9 -mmt=on -xr!*.pdb -xr!*.lib "${PORTABLE_ZIP_FILE}" "*"
            WORKING_DIRECTORY "${CMAKE_INSTALL_PREFIX_CLEAN}"
            COMMENT "Creating portable zip package with maximum compression: ${PORTABLE_ZIP_FILE}"
        )
    else()
        message(STATUS "  7-Zip          : NOT FOUND (falling back to cmake -E tar)")

        add_custom_target(package_zip
            COMMAND ${CMAKE_COMMAND}
                "-DPORTABLE_DIST_DIR=${CMAKE_INSTALL_PREFIX_CLEAN}"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/PrunePortableDistribution.cmake"
            COMMAND ${CMAKE_COMMAND} -E make_directory "${PACKAGE_OUTPUT_DIR}"
            COMMAND ${CMAKE_COMMAND} -E rm -f "${PORTABLE_ZIP_FILE}"
            COMMAND ${CMAKE_COMMAND} -E chdir "${CMAKE_INSTALL_PREFIX_CLEAN}" ${CMAKE_COMMAND} -E tar cf "${PORTABLE_ZIP_FILE}" --format=zip .
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            COMMENT "Creating portable zip package: ${PORTABLE_ZIP_FILE}"
        )
    endif()

    add_dependencies(package_zip azerothcore)

    add_custom_target(package_portable
        DEPENDS package_zip
        COMMENT "Alias for package_zip target"
    )
else()
    if(GO_EXECUTABLE)
        ExternalProject_Add_Step(azerothcore build_startup_tool
            COMMAND ${GO_EXECUTABLE} build -o "${CMAKE_INSTALL_PREFIX_CLEAN}/startup" "./cmd/startup"
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            DEPENDEES install
            COMMENT "Building startup executable: ${CMAKE_INSTALL_PREFIX_CLEAN}/startup"
        )
    endif()
endif()
