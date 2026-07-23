#include <gtest/gtest.h>
#include "suspension_kinematics/solver.hpp"

using namespace suspensionlab::kinematics;

TEST(NewtonRaphsonTest, SimpleQuadratic) {
    NewtonRaphsonSolver solver;
    
    // Solve x^2 - 4 = 0. Roots at x=2, x=-2
    auto eval_f = [](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
        f.resize(1);
        f(0) = x(0) * x(0) - 4.0;
    };
    
    auto eval_j = [](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
        j.resize(1, 1);
        j(0, 0) = 2.0 * x(0);
    };
    
    Eigen::VectorXd guess(1);
    guess(0) = 3.0;
    
    Eigen::VectorXd root = solver.solve(eval_f, eval_j, guess);
    
    EXPECT_NEAR(root(0), 2.0, 1e-6);
}

TEST(NewtonRaphsonTest, Divergence) {
    NewtonRaphsonSolver solver;
    
    // Solve e^x = -1 (no solution)
    auto eval_f = [](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
        f.resize(1);
        f(0) = std::exp(x(0)) + 1.0;
    };
    
    auto eval_j = [](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
        j.resize(1, 1);
        j(0, 0) = std::exp(x(0));
    };
    
    Eigen::VectorXd guess(1);
    guess(0) = 0.0;
    
    EXPECT_THROW(solver.solve(eval_f, eval_j, guess), KinematicDivergenceException);
}
