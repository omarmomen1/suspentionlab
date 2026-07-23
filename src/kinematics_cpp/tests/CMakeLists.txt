FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.14.0
)
FetchContent_MakeAvailable(googletest)

add_executable(kinematics_tests
    test_solver.cpp
)
target_link_libraries(kinematics_tests PRIVATE kinematics_core gtest_main)

include(GoogleTest)
gtest_discover_tests(kinematics_tests)
