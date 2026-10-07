"""Execute the production MSVC settings to check bounded compiler concurrency."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from PreparedSources import prepared_core


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=prepared_core(repo))
args = parser.parse_args()
cmake = shutil.which('cmake')
assert cmake, 'CMake is required to verify Windows compiler parallelism'
production = (args.source / 'src/cmake/compiler/msvc/settings.cmake').read_text()
start = production.index('# multithreaded compiling on VS\n')
end = production.index('# Define _CRT_SECURE_CPP_OVERLOAD_STANDARD_NAMES', start)
assert 'ACORE_MSVC_COMPILE_JOBS' in production[start:end]
native = production[:start] + '''# multithreaded compiling on VS
target_compile_options(acore-compile-option-interface
  INTERFACE
    /MP)

''' + production[end:]

fixture = '''
cmake_minimum_required(VERSION 3.21)
project(WindowsCompilerParallelism NONE)
set(CMAKE_CXX_COMPILER_VERSION 19.44)
set(PLATFORM 64)
set(BUILD_SHARED_LIBS ON)
set(WITH_WARNINGS OFF)
set(CMAKE_C_FLAGS "/W3 /DKEEP_C_FLAGS")
set(CMAKE_CXX_FLAGS "/W3 /DKEEP_CXX_FLAGS")
set(CMAKE_CXX_FLAGS_DEBUG "/Zi")
foreach(variable IN ITEMS CMAKE_EXE_LINKER_FLAGS_DEBUG
    CMAKE_EXE_LINKER_FLAGS_RELWITHDEBINFO CMAKE_SHARED_LINKER_FLAGS_DEBUG
    CMAKE_SHARED_LINKER_FLAGS_RELWITHDEBINFO)
  set(${variable} "/INCREMENTAL /DEBUG")
endforeach()
add_library(acore-compile-option-interface INTERFACE)
add_library(acore-warning-interface INTERFACE)
include("${TEST_SETTINGS}")
get_target_property(options acore-compile-option-interface INTERFACE_COMPILE_OPTIONS)
get_target_property(definitions acore-compile-option-interface INTERFACE_COMPILE_DEFINITIONS)
get_target_property(warnings acore-warning-interface INTERFACE_COMPILE_OPTIONS)
file(WRITE "${CMAKE_BINARY_DIR}/settings.txt"
  "options=${options}\\ndefinitions=${definitions}\\nwarnings=${warnings}\\n"
  "c_flags=${CMAKE_C_FLAGS}\\ncxx_flags=${CMAKE_CXX_FLAGS}\\n"
  "debug_flags=${CMAKE_CXX_FLAGS_DEBUG}\\n"
  "exe_debug=${CMAKE_EXE_LINKER_FLAGS_DEBUG}\\n"
  "exe_relwithdebinfo=${CMAKE_EXE_LINKER_FLAGS_RELWITHDEBINFO}\\n"
  "shared_debug=${CMAKE_SHARED_LINKER_FLAGS_DEBUG}\\n"
  "shared_relwithdebinfo=${CMAKE_SHARED_LINKER_FLAGS_RELWITHDEBINFO}\\n")
'''

with tempfile.TemporaryDirectory(prefix='windows compiler jobs ') as temp:
    root = Path(temp)
    (root / 'CMakeLists.txt').write_text(fixture)
    (root / 'production.cmake').write_text(production)
    (root / 'native.cmake').write_text(native)

    def configure(name, settings, jobs=None):
        build = root / name
        command = [cmake, '-S', str(root), '-B', str(build),
                   '-DTEST_SETTINGS=' + str(root / settings)]
        if jobs is not None:
            command.append('-DACORE_MSVC_COMPILE_JOBS:STRING=' + jobs)
        result = subprocess.run(command, text=True, capture_output=True)
        return result, build

    result, build = configure('native', 'native.cmake')
    assert result.returncode == 0, result.stdout + result.stderr
    baseline = (build / 'settings.txt').read_text()
    assert '/MP;' in baseline

    for index, jobs in enumerate((None, '', '1', '2', '4')):
        result, build = configure(f'valid {index}', 'production.cmake', jobs)
        assert result.returncode == 0, result.stdout + result.stderr
        actual = (build / 'settings.txt').read_text()
        option = '/MP' + (jobs or '')
        expected = baseline.replace('/MP;', option + ';')
        assert actual == expected, (jobs, actual, expected)
        assert actual.count(option + ';') == 1, (jobs, actual)

    for index, jobs in enumerate(('0', '-1', 'abc', '1.5', '2;3', ' 2', '+2')):
        result, _ = configure(f'invalid {index}', 'production.cmake', jobs)
        assert result.returncode != 0, (jobs, result.stdout, result.stderr)
        assert 'must be empty or a positive decimal integer' in result.stdout + result.stderr

print('Windows compiler parallelism: native fallback, bounded /MP, invalid values and other settings passed')
