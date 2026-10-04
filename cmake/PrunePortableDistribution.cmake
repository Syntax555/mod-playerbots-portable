if(NOT PORTABLE_DIST_DIR OR NOT IS_DIRECTORY "${PORTABLE_DIST_DIR}")
    message(FATAL_ERROR "PORTABLE_DIST_DIR must point to a built distribution")
endif()

foreach(executable startup.exe authserver.exe worldserver.exe
    mysql/bin/mysqld.exe mysql/bin/mysql.exe mysql/bin/mysqladmin.exe)
    if(NOT EXISTS "${PORTABLE_DIST_DIR}/${executable}")
        message(FATAL_ERROR "Cannot package an incomplete build: missing ${executable}")
    endif()
endforeach()

# Match the 7-Zip exclusions when the CMake ZIP fallback is used as well.
file(GLOB_RECURSE development_files
    "${PORTABLE_DIST_DIR}/*.pdb" "${PORTABLE_DIST_DIR}/*.lib"
    "${PORTABLE_DIST_DIR}/*.exp" "${PORTABLE_DIST_DIR}/*.ilk")
if(development_files)
    file(REMOVE ${development_files})
endif()
