add_test([=[NewtonRaphsonTest.SimpleQuadratic]=]  D:/project/build/tests/Release/kinematics_tests.exe [==[--gtest_filter=NewtonRaphsonTest.SimpleQuadratic]==] --gtest_also_run_disabled_tests)
set_tests_properties([=[NewtonRaphsonTest.SimpleQuadratic]=]
  PROPERTIES
    
    DEF_SOURCE_LINE [==[D:\project\src\kinematics_cpp\tests\test_solver.cpp:6]==]
    WORKING_DIRECTORY [==[D:/project/build/tests]==]
    SKIP_REGULAR_EXPRESSION [==[\[  SKIPPED \]]==]
    
)
add_test([=[NewtonRaphsonTest.Divergence]=]  D:/project/build/tests/Release/kinematics_tests.exe [==[--gtest_filter=NewtonRaphsonTest.Divergence]==] --gtest_also_run_disabled_tests)
set_tests_properties([=[NewtonRaphsonTest.Divergence]=]
  PROPERTIES
    
    DEF_SOURCE_LINE [==[D:\project\src\kinematics_cpp\tests\test_solver.cpp:28]==]
    WORKING_DIRECTORY [==[D:/project/build/tests]==]
    SKIP_REGULAR_EXPRESSION [==[\[  SKIPPED \]]==]
    
)
set(kinematics_tests_TESTS [==[NewtonRaphsonTest.SimpleQuadratic]==] [==[NewtonRaphsonTest.Divergence]==])
