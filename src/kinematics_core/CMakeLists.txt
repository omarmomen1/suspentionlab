cmake_minimum_required(VERSION 3.18)
project(kinematics_core VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Eigen3 via FetchContent (header-only, no install needed) ──────────────────
include(FetchContent)
FetchContent_Declare(
    eigen3
    GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
    GIT_TAG        3.4.0
    GIT_SHALLOW    TRUE
)
# Disable Eigen's own tests and install rules
set(EIGEN_BUILD_DOC     OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING       OFF CACHE BOOL "" FORCE)
set(EIGEN_BUILD_TESTING OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(eigen3)

# ── pybind11: locate via the pip-installed package ────────────────────────────
find_package(Python COMPONENTS Interpreter Development REQUIRED)
execute_process(
    COMMAND "${Python_EXECUTABLE}" -c
            "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE _pb11_cmake_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY
)
list(APPEND CMAKE_PREFIX_PATH "${_pb11_cmake_dir}")
find_package(pybind11 CONFIG REQUIRED)

# ── Extension module ──────────────────────────────────────────────────────────
pybind11_add_module(kinematics_core
    src/kinematics_solver.cpp
    src/bindings.cpp
)

target_include_directories(kinematics_core PRIVATE
    src
    ${eigen3_SOURCE_DIR}    # populated by FetchContent
)

# Compiler-specific optimisation flags
target_compile_options(kinematics_core PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:
        /O2 /W3 /EHsc /MP
        /D_USE_MATH_DEFINES    # provides M_PI on MSVC
    >
    $<$<CXX_COMPILER_ID:GNU>:
        -O3 -march=native -Wall -Wextra
        -fno-strict-aliasing   # Eigen safety
    >
    $<$<CXX_COMPILER_ID:Clang>:
        -O3 -Wall -Wextra
        -fno-strict-aliasing
    >
)

# MinGW: link against static runtime to produce a self-contained .pyd
if (MINGW)
    target_link_options(kinematics_core PRIVATE
        -static-libgcc -static-libstdc++
    )
endif()

# ── Install: copy the .pyd / .so into the suspensionlab.physics package ───────
# The install prefix should be set to d:/project when invoking cmake --install.
# Default: place next to the source for direct import during development.
set_target_properties(kinematics_core PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY
        "${CMAKE_SOURCE_DIR}/../../src/suspensionlab/physics"
    RUNTIME_OUTPUT_DIRECTORY
        "${CMAKE_SOURCE_DIR}/../../src/suspensionlab/physics"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE
        "${CMAKE_SOURCE_DIR}/../../src/suspensionlab/physics"
    LIBRARY_OUTPUT_DIRECTORY_RELEASE
        "${CMAKE_SOURCE_DIR}/../../src/suspensionlab/physics"
)

message(STATUS "kinematics_core will be built to:")
message(STATUS "  ${CMAKE_SOURCE_DIR}/../../src/suspensionlab/physics")
