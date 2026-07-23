#pragma once
#include <Eigen/Dense>
#include <functional>
#include "suspension_kinematics/exceptions.hpp"

namespace suspensionlab {
namespace kinematics {

// Signature for evaluating constraints: F(x)
using ConstraintFunc = std::function<void(const Eigen::VectorXd&, Eigen::VectorXd&)>;

// Signature for evaluating Jacobian: J(x)
using JacobianFunc = std::function<void(const Eigen::VectorXd&, Eigen::MatrixXd&)>;

class NewtonRaphsonSolver {
public:
    struct Options {
        int max_iterations = 50;
        double tolerance = 1e-8;
    };

    NewtonRaphsonSolver(Options options = Options{}) : options_(options) {}

    // Solves the system starting from an initial guess
    Eigen::VectorXd solve(const ConstraintFunc& eval_f, 
                          const JacobianFunc& eval_j, 
                          const Eigen::VectorXd& initial_guess) const;

private:
    Options options_;
};

} // namespace kinematics
} // namespace suspensionlab
