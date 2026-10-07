"""Check production Visual Studio resource include metadata with native CMake.

The Windows release additionally compiles the real RC targets before compiling
the server. This portable fixture checks metadata parsing, paths with spaces,
both server applications, generator isolation and the supported CMake version.
"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PreparedSources import prepared_core


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=prepared_core(repo))
args = parser.parse_args()
cmake = shutil.which('cmake')
assert cmake, 'CMake is required to verify resource compiler metadata'
source = (args.source / 'src/server/apps/CMakeLists.txt').read_text()
lines = source.splitlines(keepends=True)
start = next(index for index, line in enumerate(lines)
             if re.search(r'if\(CMAKE_GENERATOR MATCHES "\^Visual Studio"\)', line))
depth = 0
for end in range(start, len(lines)):
    if re.match(r'\s*if\(', lines[end]):
        depth += 1
    elif re.match(r'\s*endif\(', lines[end]):
        depth -= 1
        if depth == 0:
            break
else:
    raise AssertionError('Unterminated production resource compiler configuration')
production = ''.join(lines[start:end + 1])

fixture = '''
cmake_minimum_required(VERSION 3.21)
project(ResourceIncludeMetadata NONE)
set(CMAKE_GENERATOR "${TEST_GENERATOR}")
if(DEFINED TEST_CMAKE_VERSION)
  set(CMAKE_VERSION "${TEST_CMAKE_VERSION}")
endif()
foreach(APPLICATION_NAME IN ITEMS authserver worldserver)
  set(SOURCE_APP_PATH "${CMAKE_CURRENT_SOURCE_DIR}/${APPLICATION_NAME} resources")
  file(MAKE_DIRECTORY "${SOURCE_APP_PATH}")
  file(WRITE "${SOURCE_APP_PATH}/${APPLICATION_NAME}.rc" "")
  include("${CMAKE_CURRENT_SOURCE_DIR}/production.cmake")
  get_source_file_property(settings "${SOURCE_APP_PATH}/${APPLICATION_NAME}.rc" VS_SETTINGS)
  if(TEST_GENERATOR MATCHES "^Visual Studio")
    list(LENGTH settings count)
    if(NOT count EQUAL 1)
      message(FATAL_ERROR "Resource metadata split into ${count} settings: ${settings}")
    endif()
    foreach(setting IN LISTS settings)
      if(NOT setting MATCHES "^AdditionalIncludeDirectories=")
        message(FATAL_ERROR "Unexpected resource metadata: ${setting}")
      endif()
      string(REGEX REPLACE "^AdditionalIncludeDirectories=" "" includes "${setting}")
      if(NOT includes STREQUAL "${SOURCE_APP_PATH};${CMAKE_BINARY_DIR}")
        message(FATAL_ERROR "Resource include paths are incomplete or inherited: ${includes}")
      endif()
    endforeach()
    get_source_file_property(cpp_settings "${SOURCE_APP_PATH}/Main.cpp" VS_SETTINGS)
    if(cpp_settings)
      message(FATAL_ERROR "C++ includes must retain their ordinary target settings")
    endif()
  elseif(settings)
    message(FATAL_ERROR "Resource metadata must not change other generators")
  endif()
endforeach()
'''

with tempfile.TemporaryDirectory(prefix='resource includes ') as temp:
    root = Path(temp)
    (root / 'CMakeLists.txt').write_text(fixture)
    (root / 'production.cmake').write_text(production)
    cases = [('Visual Studio 17 2022', None, True),
             ('Ninja', None, True),
             ('Unix Makefiles', '3.21.0', True),
             ('Visual Studio 17 2022', '3.21.0', False)]
    for index, (generator, version, succeeds) in enumerate(cases):
        command = [cmake, '-S', str(root), '-B', str(root / f'build {index}'),
                   '-DTEST_GENERATOR=' + generator]
        if version:
            command.append('-DTEST_CMAKE_VERSION=' + version)
        result = subprocess.run(command, text=True, capture_output=True)
        assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
        if not succeeds:
            assert 'requires CMake 3.22 or newer' in result.stdout + result.stderr

print('Windows resource includes: both applications, escaped paths, generator/version guards passed')
