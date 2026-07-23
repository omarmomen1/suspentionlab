#include "suspension_kinematics/solver.hpp"
#include <iostream>

namespace suspensionlab {
namespace kinematics {

Eigen::VectorXd NewtonRaphsonSolver::solve(
    const ConstraintFunc& eval_f, 
    const JacobianFunc& eval_j, 
    const Eigen::VectorXd& initial_guess) const 
{
    Eigen::VectorXd x = initial_guess;
    Eigen::VectorXd f(x.size());
    Eigen::MatrixXd J(x.size(), x.size());

    for (int iter = 0; iter < options_.max_iterations; ++iter) {
        std::cout << "Solver iter " << iter << std::endl;
        eval_f(x, f);
        std::cout << "eval_f done" << std::endl;
        
        if (f.cwiseAbs().maxCoeff() < options_.tolerance) {
            return x; // Converged
        }

        eval_j(x, J);
        std::cout << "eval_j done" << std::endl;

        // Solve J * dx = -f
        Eigen::VectorXd dx = J.colPivHouseholderQr().solve(-f);
        std::cout << "solve done" << std::endl;

        if (dx.cwiseAbs().maxCoeff() < options_.tolerance) {
            return x; // Step size too small, effectively converged
        }

        x += dx;
        
        // Singularity check: if step is absurdly large
        if (dx.cwiseAbs().maxCoeff() > 1e6) {
            throw KinematicDivergenceException("Newton-Raphson diverged (Singular Jacobian or bad step).");
        }
    }

    throw KinematicDivergenceException("Newton-Raphson failed to converge within maximum iterations.");
}

} // namespace kinematics
} // namespace suspensionlab
