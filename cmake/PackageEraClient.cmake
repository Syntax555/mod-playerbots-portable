# Build the historical talent client patch from locked module sources.
# Native Linux toolchain, Python3 + PyYAML and 7z are required; no Docker.
# cmake -DPACKAGE_VERSION=dev -P cmake/PackageEraClient.cmake
cmake_minimum_required(VERSION 3.19)
if(NOT PORTABLE_SOURCE_DIR)
    get_filename_component(PORTABLE_SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
endif()
if(NOT PACKAGE_OUTPUT_DIR)
    set(PACKAGE_OUTPUT_DIR "${PORTABLE_SOURCE_DIR}/output")
endif()
if(NOT DEFINED PACKAGE_VERSION)
    if(DEFINED ENV{PACKAGE_VERSION})
        set(PACKAGE_VERSION "$ENV{PACKAGE_VERSION}")
    else()
        set(PACKAGE_VERSION dev)
    endif()
endif()
file(READ "${PORTABLE_SOURCE_DIR}/versions.lock.json" lock)
string(JSON client_patch ERROR_VARIABLE client_patch_error GET "${lock}" clientPatch)
if(client_patch_error)
    message(STATUS "Selected source has no historical client patch to package")
    return()
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(Git REQUIRED)
find_program(SEVENZIP_EXECUTABLE NAMES 7z 7zz REQUIRED)
file(MAKE_DIRECTORY "${PORTABLE_SOURCE_DIR}/.module-cache/package-era-client")
file(LOCK "${PORTABLE_SOURCE_DIR}/.module-cache/package-era-client/package.lock" GUARD PROCESS TIMEOUT 60)
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_LIST_DIR}/PackageEraClient.py"
    --repository "${PORTABLE_SOURCE_DIR}" --output "${PACKAGE_OUTPUT_DIR}"
    --version "${PACKAGE_VERSION}" --cmake "${CMAKE_COMMAND}"
    --git "${GIT_EXECUTABLE}" --sevenzip "${SEVENZIP_EXECUTABLE}"
    RESULT_VARIABLE result)
if(NOT result EQUAL 0)
    message(FATAL_ERROR "Historical talent client packaging failed (${result})")
endif()
