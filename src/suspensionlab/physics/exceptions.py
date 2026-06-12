class MathConvergenceError(Exception):
    """Raised when an optimization or physics solver fails to converge."""
    pass

class PhysicsValidationError(ValueError):
    """Raised when physics input parameters are invalid."""
    pass
