cmake_minimum_required(VERSION 3.15)
project(QuarterCarRideModel C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Shared library for FMI 2.0 Co-Simulation
add_library(QuarterCarRideModel SHARED
    src/QuarterCarRideModel.c
)

target_include_directories(QuarterCarRideModel PRIVATE
    include
)

# FMI specification mandates exact library name without 'lib' prefix on Windows
set_target_properties(QuarterCarRideModel PROPERTIES
    PREFIX ""
    OUTPUT_NAME "QuarterCarRideModel"
    C_VISIBILITY_PRESET default
)

if(MSVC)
    target_compile_options(QuarterCarRideModel PRIVATE /W4 /O2)
else()
    target_compile_options(QuarterCarRideModel PRIVATE -Wall -Wextra -O2 -fPIC)
endif()
