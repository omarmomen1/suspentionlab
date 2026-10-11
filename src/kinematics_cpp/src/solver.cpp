#include "suspension_kinematics/solver.hpp"
#include <cmath>
#include <algorithm>
#include <iostream>

namespace suspensionlab {
namespace kinematics {

NewtonRaphsonSolver::Result NewtonRaphsonSolver::solve(
    const ConstraintFunc& eval_f, 
    const JacobianFunc& eval_j, 
    const Eigen::VectorXd& initial_guess) const 
{
    Eigen::VectorXd x = initial_guess;
    Eigen::VectorXd f(x.size());
    Eigen::MatrixXd J(x.size(), x.size());

    // Check initial guess validity
    if (!x.allFinite()) {
        return {x, SolverResult::NUMERICAL_DIVERGENCE, 0, 0.0, 1.0, 0};
    }

    int total_line_search_steps = 0;
    double final_cond = 1.0;

    for (int iter = 0; iter < options_.max_iterations; ++iter) {
        eval_f(x, f);

        if (!f.allFinite()) {
            return {x, SolverResult::NUMERICAL_DIVERGENCE, iter, 0.0, final_cond, total_line_search_steps};
        }
        
        double f_norm = f.cwiseAbs().maxCoeff();
        if (f_norm < options_.tolerance) {
            return {x, SolverResult::CONVERGED, iter, f_norm, final_cond, total_line_search_steps};
        }

        eval_j(x, J);
        if (!J.allFinite()) {
            return {x, SolverResult::NUMERICAL_DIVERGENCE, iter, f_norm, final_cond, total_line_search_steps};
        }

        // ColPivHouseholderQR for robust rank and condition estimation
        Eigen::ColPivHouseholderQR<Eigen::MatrixXd> qr(J);
        int rank = qr.rank();
        if (rank < J.cols()) {
            return {x, SolverResult::SINGULAR_JACOBIAN, iter, f_norm, 1e16, total_line_search_steps};
        }

        // Numerical condition estimation from diagonal of R
        auto R_diag = qr.matrixR().diagonal().cwiseAbs();
        double r_max = R_diag.maxCoeff();
        double r_min = R_diag.minCoeff();
        double cond = (r_min > 1e-15) ? (r_max / r_min) : 1e16;
        final_cond = cond;

        Eigen::VectorXd dx;
        if (cond > options_.max_condition_number) {
            if (options_.enable_damping) {
                // Levenberg-Marquardt damping for ill-conditioned systems
                Eigen::MatrixXd JT_J = J.transpose() * J;
                Eigen::MatrixXd damped_H = JT_J + options_.damping_lambda * r_max * Eigen::MatrixXd::Identity(J.cols(), J.cols());
                dx = damped_H.ldlt().solve(-J.transpose() * f);
            } else {
                return {x, SolverResult::ILL_CONDITIONED, iter, f_norm, cond, total_line_search_steps};
            }
        } else {
            dx = qr.solve(-f);
        }

        if (!dx.allFinite()) {
            return {x, SolverResult::NUMERICAL_DIVERGENCE, iter, f_norm, cond, total_line_search_steps};
        }

        double dx_norm = dx.cwiseAbs().maxCoeff();
        if (dx_norm < options_.tolerance) {
            // Step size vanishingly small: check if residual is within acceptable bound
            if (f_norm < 10.0 * options_.tolerance) {
                return {x, SolverResult::CONVERGED, iter, f_norm, cond, total_line_search_steps};
            }
        }

        // Domain check: step magnitude
        if (dx_norm > options_.max_step_norm) {
            return {x, SolverResult::OUT_OF_DOMAIN, iter, f_norm, cond, total_line_search_steps};
        }

        // Armijo Backtracking Line Search: strictly reject if no residual reduction found
        double alpha = 1.0;
        Eigen::VectorXd f_trial(x.size());
        bool step_accepted = false;
        double current_norm = f.norm();

        while (alpha >= options_.min_alpha) {
            total_line_search_steps++;
            Eigen::VectorXd x_trial = x + alpha * dx;
            eval_f(x_trial, f_trial);

            if (f_trial.allFinite() && (f_trial.norm() < (1.0 - options_.armijo_c1 * alpha) * current_norm)) {
                x = x_trial;
                step_accepted = true;
                break;
            }
            alpha *= 0.5;
        }

        if (!step_accepted) {
            // Strictly reject unverified step after line search failure (Non-negotiable Rule)
            return {x, SolverResult::LINE_SEARCH_FAILED, iter, f_norm, cond, total_line_search_steps};
        }
    }

    // Final residual check
    eval_f(x, f);
    double final_f_norm = f.allFinite() ? f.cwiseAbs().maxCoeff() : 1e9;
    if (final_f_norm < options_.tolerance) {
        return {x, SolverResult::CONVERGED, options_.max_iterations, final_f_norm, final_cond, total_line_search_steps};
    }

    return {x, SolverResult::MAX_ITERATIONS, options_.max_iterations, final_f_norm, final_cond, total_line_search_steps};
}

} // namespace kinematics
} // namespace suspensionlab
