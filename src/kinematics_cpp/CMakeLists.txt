cmake_minimum_required(VERSION 3.24)
project(suspensionlab_kinematics VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# BUG FIX: Prevent MSVC ABI stack-alignment access violations (segfaults) for fixed-size Eigen matrices
add_compile_definitions(EIGEN_DONT_ALIGN_STATICALLY)

include(FetchContent)

# Fetch Eigen
FetchContent_Declare(
    eigen
    GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
    GIT_TAG        3.4.0
)
FetchContent_MakeAvailable(eigen)

# Fetch pybind11
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# Core Library (Static)
add_library(kinematics_core STATIC
    src/solver.cpp
    src/topologies_double_wishbone.cpp
    src/topologies_macpherson.cpp
)
target_include_directories(kinematics_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(kinematics_core PUBLIC Eigen3::Eigen)

# Python Extension Module
pybind11_add_module(suspensionlab_kinematics bindings/pybind_module.cpp)
target_link_libraries(suspensionlab_kinematics PRIVATE kinematics_core)

# Install rules for scikit-build-core
install(TARGETS suspensionlab_kinematics DESTINATION .)

# Tests
option(BUILD_TESTING "Build tests" ON)
if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()
