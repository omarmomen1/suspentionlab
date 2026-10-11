cmake_minimum_required(VERSION 3.20)
project(kinematics_core VERSION 3.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Prevent MSVC ABI stack-alignment issues
add_compile_definitions(EIGEN_DONT_ALIGN_STATICALLY)
if (MSVC)
    add_compile_options(/O2 /W3 /EHsc /MP /D_USE_MATH_DEFINES)
else()
    add_compile_options(-O3 -Wall -Wextra -fno-strict-aliasing -fPIC)
endif()

# Locate Python & pybind11
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# Eigen include directory (system package, find_package, or local)
find_package(Eigen3 3.3 QUIET)
if(NOT TARGET Eigen3::Eigen)
    set(EIGEN3_INCLUDE_DIR "${CMAKE_SOURCE_DIR}/../../build/_deps/eigen-src")
    if(NOT EXISTS "${EIGEN3_INCLUDE_DIR}")
        if(EXISTS "/usr/include/eigen3")
            set(EIGEN3_INCLUDE_DIR "/usr/include/eigen3")
        elseif(EXISTS "/usr/local/include/eigen3")
            set(EIGEN3_INCLUDE_DIR "/usr/local/include/eigen3")
        else()
            set(EIGEN3_INCLUDE_DIR "${CMAKE_SOURCE_DIR}/../kinematics_core/_build_gcc/_deps/eigen3-src")
        endif()
    endif()
endif()

# pybind11 include directory (local, config, or python -m pybind11)
set(PYBIND11_DIR "${CMAKE_SOURCE_DIR}/../../build/_deps/pybind11-src")
if(EXISTS "${PYBIND11_DIR}/CMakeLists.txt")
    add_subdirectory("${PYBIND11_DIR}" "${CMAKE_BINARY_DIR}/_deps/pybind11-build" EXCLUDE_FROM_ALL)
else()
    find_package(pybind11 CONFIG QUIET)
    if(NOT pybind11_FOUND)
        execute_process(
            COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
            OUTPUT_VARIABLE pybind11_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
        find_package(pybind11 CONFIG REQUIRED)
    endif()
endif()

# Core Static Library
add_library(kinematics_static STATIC
    src/solver.cpp
    src/hardpoint_validation.cpp
    src/bushing_compliance.cpp
    src/topologies_double_wishbone.cpp
    src/topologies_macpherson.cpp
)
set_target_properties(kinematics_static PROPERTIES POSITION_INDEPENDENT_CODE ON)

target_include_directories(kinematics_static PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${EIGEN3_INCLUDE_DIR}>
    $<INSTALL_INTERFACE:include>
)
if(TARGET Eigen3::Eigen)
    target_link_libraries(kinematics_static PUBLIC Eigen3::Eigen)
endif()

# Python Extension Module
pybind11_add_module(kinematics_core bindings/pybind_module.cpp)
target_link_libraries(kinematics_core PRIVATE kinematics_static)
if(TARGET Eigen3::Eigen)
    target_link_libraries(kinematics_core PRIVATE Eigen3::Eigen)
else()
    target_include_directories(kinematics_core PRIVATE ${EIGEN3_INCLUDE_DIR})
endif()

# MinGW runtime linkage: statically link libgcc, libstdc++, and winpthread
if (MINGW)
    target_link_options(kinematics_core PRIVATE -static -static-libgcc -static-libstdc++ -Wl,-Bstatic -lwinpthread -Wl,-Bdynamic)
endif()

# Output directly to suspensionlab/physics directory and root src for seamless Python loading
set_target_properties(kinematics_core PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../suspensionlab/physics"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../suspensionlab/physics"
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../suspensionlab/physics"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../suspensionlab/physics"
)

# Tests
option(BUILD_TESTING "Build tests" ON)
if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()
