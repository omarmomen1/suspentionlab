set(GTEST_DIR "${CMAKE_SOURCE_DIR}/../../build/_deps/googletest-src")
if(EXISTS "${GTEST_DIR}/CMakeLists.txt")
    add_subdirectory("${GTEST_DIR}" "${CMAKE_BINARY_DIR}/_deps/googletest-build" EXCLUDE_FROM_ALL)
else()
    find_package(GTest REQUIRED)
endif()

add_executable(kinematics_tests
    test_solver.cpp
)
target_link_libraries(kinematics_tests PRIVATE kinematics_static gtest_main)
target_include_directories(kinematics_tests PRIVATE 
    ${EIGEN3_INCLUDE_DIR}
    ${CMAKE_SOURCE_DIR}/include
)

include(GoogleTest)
gtest_discover_tests(kinematics_tests)
