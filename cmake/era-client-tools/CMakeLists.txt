cmake_minimum_required(VERSION 3.19)
project(PortableEraClientTools LANGUAGES C CXX)

if(NOT STORM_SOURCE_DIR OR NOT ERA_SOURCE_DIR)
    message(FATAL_ERROR "STORM_SOURCE_DIR and ERA_SOURCE_DIR are required")
endif()
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(STORM_USE_BUNDLED_LIBRARIES ON CACHE BOOL "" FORCE)
set(STORM_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${STORM_SOURCE_DIR}" storm)
foreach(tool mpqpack mpqread)
    add_executable(${tool} "${ERA_SOURCE_DIR}/client-patch/${tool}.c")
    target_include_directories(${tool} PRIVATE "${STORM_SOURCE_DIR}/src")
    # The upstream era tools use the newer alias; the locked StormLib 9.30
    # exports the established GetLastError name on Linux.
    target_compile_definitions(${tool} PRIVATE SErrGetLastError=GetLastError)
    target_link_libraries(${tool} PRIVATE storm)
    set_target_properties(${tool} PROPERTIES LINKER_LANGUAGE CXX)
endforeach()
