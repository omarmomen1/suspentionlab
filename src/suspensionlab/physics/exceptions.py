class MathConvergenceError(Exception):
    """Raised when an optimization or physics solver fails to converge."""
    pass

class SolverNonConvergenceError(MathConvergenceError):
    """Raised when a physical algebraic loop or DAE solver fails to reach numerical convergence."""
    pass

class PhysicsValidationError(ValueError):
    """Raised when physics input parameters are invalid."""
    pass

