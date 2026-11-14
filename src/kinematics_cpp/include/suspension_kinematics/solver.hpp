#pragma once
#include <Eigen/Dense>
#include <functional>
#include <string>
#include "suspension_kinematics/exceptions.hpp"

namespace suspensionlab {
namespace kinematics {

// Signature for evaluating constraints: F(x, f)
using ConstraintFunc = std::function<void(const Eigen::VectorXd&, Eigen::VectorXd&)>;

// Signature for evaluating Jacobian: J(x, J)
using JacobianFunc = std::function<void(const Eigen::VectorXd&, Eigen::MatrixXd&)>;

class NewtonRaphsonSolver {
public:
    enum class SolverResult {
        CONVERGED,
        MAX_ITERATIONS,
        SINGULAR_JACOBIAN,
        ILL_CONDITIONED,
        OUT_OF_DOMAIN,
        INFEASIBLE_GEOMETRY,
        LINE_SEARCH_FAILED,
        INVALID_HARDPOINTS,
        NUMERICAL_DIVERGENCE
    };

    static std::string result_to_string(SolverResult res) {
        switch (res) {
            case SolverResult::CONVERGED: return "CONVERGED";
            case SolverResult::MAX_ITERATIONS: return "MAX_ITERATIONS";
            case SolverResult::SINGULAR_JACOBIAN: return "SINGULAR_JACOBIAN";
            case SolverResult::ILL_CONDITIONED: return "ILL_CONDITIONED";
            case SolverResult::OUT_OF_DOMAIN: return "OUT_OF_DOMAIN";
            case SolverResult::INFEASIBLE_GEOMETRY: return "INFEASIBLE_GEOMETRY";
            case SolverResult::LINE_SEARCH_FAILED: return "LINE_SEARCH_FAILED";
            case SolverResult::INVALID_HARDPOINTS: return "INVALID_HARDPOINTS";
            case SolverResult::NUMERICAL_DIVERGENCE: return "NUMERICAL_DIVERGENCE";
            default: return "UNKNOWN";
        }
    }

    struct Result {
        Eigen::VectorXd state;
        SolverResult status = SolverResult::NUMERICAL_DIVERGENCE;
        int iterations = 0;
        double residual_norm = 0.0;
        double condition_number = 1.0;
        int line_search_steps = 0;

        Result() = default;
        Result(Eigen::VectorXd s, SolverResult st, int it, double rn, double cn, int ls)
            : state(std::move(s)), status(st), iterations(it), residual_norm(rn), condition_number(cn), line_search_steps(ls) {}
    };

    struct Options {
        int max_iterations = 60;
        double tolerance = 1e-8;
        double max_step_norm = 1e3;          // Domain check: step norm in mm or rad
        double min_alpha = 1e-4;             // Line search alpha floor
        double armijo_c1 = 1e-4;             // Armijo parameter
        double max_condition_number = 1e10;  // Threshold for ill-conditioned Jacobian
        double damping_lambda = 1e-6;        // Levenberg-Marquardt damping factor
        bool enable_damping = true;          // Enable trust-region damping if ill-conditioned
    };

    NewtonRaphsonSolver() : options_(Options{}) {}
    explicit NewtonRaphsonSolver(Options options) : options_(options) {}

    const Options& options() const { return options_; }
    void set_options(const Options& options) { options_ = options; }

    // Solves the system starting from an initial guess
    Result solve(const ConstraintFunc& eval_f, 
                 const JacobianFunc& eval_j, 
                 const Eigen::VectorXd& initial_guess) const;

private:
    Options options_;
};

} // namespace kinematics
} // namespace suspensionlab
