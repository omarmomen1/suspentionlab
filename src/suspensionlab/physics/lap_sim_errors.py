from __future__ import annotations

from typing import Any, Dict, List, Optional


class LapSimError(Exception):
    """
    Base class for all lap simulation errors.
    
    Attributes:
        message (str): A descriptive error message.
        station_index (Optional[int]): The track station index where the error occurred, if applicable.
        context (Dict[str, Any]): Additional context about the error state.
    """
    
    def __init__(self, message: str, station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.station_index = station_index
        self.context = context or {}
        
    def __str__(self) -> str:
        base = f"{self.__class__.__name__}: {self.message}"
        if self.station_index is not None:
            base += f" [Station: {self.station_index}]"
        return base
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the error to a dictionary suitable for JSON serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "station_index": self.station_index,
            "context": self.context,
        }


class InvalidTrackError(LapSimError):
    """
    Raised when the track data validation fails (e.g., non-continuous geometry).
    
    Attributes:
        issues (List[str]): List of specific validation issues found in the track data.
    """
    
    def __init__(self, issues: List[str], message: str = "Track validation failed", station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.issues = issues
        
    def __str__(self) -> str:
        base = super().__str__()
        issues_str = ", ".join(self.issues)
        return f"{base} | Issues: {issues_str}"
        
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["issues"] = self.issues
        return data


class TireModelError(LapSimError):
    """
    Raised when the tire model receives or produces invalid data (e.g., NaN, negative Fz).
    
    Attributes:
        tire_corner (str): The corner of the vehicle (FL, FR, RL, RR).
        Fz (float): Normal load [N].
        alpha (float): Slip angle [rad].
        kappa (float): Slip ratio [-].
    """
    
    def __init__(self, tire_corner: str, Fz: float, alpha: float, kappa: float, message: str = "Tire model invalid state", station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.tire_corner = tire_corner
        self.Fz = Fz
        self.alpha = alpha
        self.kappa = kappa
        
    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | Corner: {self.tire_corner}, Fz: {self.Fz:.2f} N, Alpha: {self.alpha:.4f} rad, Kappa: {self.kappa:.4f}"

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "tire_corner": self.tire_corner,
            "Fz": self.Fz,
            "alpha": self.alpha,
            "kappa": self.kappa
        })
        return data


class SolverNonConvergenceError(LapSimError):
    """
    Raised when the numerical speed solver fails to converge within the allowed iterations.
    
    Attributes:
        phase (str): The solver phase ('apex', 'forward', 'backward').
        max_residual (float): The final maximum residual error.
        iteration_count (int): The number of iterations completed.
    """
    
    def __init__(self, phase: str, max_residual: float, iteration_count: int, message: str = "Solver failed to converge", station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.phase = phase
        self.max_residual = max_residual
        self.iteration_count = iteration_count
        
    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | Phase: '{self.phase}', Max Residual: {self.max_residual:.4e}, Iterations: {self.iteration_count}"
        
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "phase": self.phase,
            "max_residual": self.max_residual,
            "iteration_count": self.iteration_count
        })
        return data


class ImpossibleSpeedError(LapSimError):
    """
    Raised when a calculated speed is physically impossible (e.g., negative, NaN).
    
    Attributes:
        speed_mps (float): The calculated speed in meters per second [m/s].
    """
    
    def __init__(self, speed_mps: float, station_index: int, message: str = "Physically impossible speed calculated", context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.speed_mps = speed_mps
        
    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | Speed: {self.speed_mps} m/s"
        
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["speed_mps"] = self.speed_mps
        return data


class MissingVehicleDataError(LapSimError):
    """
    Raised when required vehicle parameters are missing for the simulation.
    
    Attributes:
        missing_fields (List[str]): List of missing required parameter names.
    """
    
    def __init__(self, missing_fields: List[str], message: str = "Missing required vehicle data", station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.missing_fields = missing_fields
        
    def __str__(self) -> str:
        base = super().__str__()
        fields_str = ", ".join(self.missing_fields)
        return f"{base} | Missing fields: {fields_str}"
        
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["missing_fields"] = self.missing_fields
        return data


class PowertrainError(LapSimError):
    """
    Raised when powertrain limits are violated, such as no valid gear for the current speed/RPM.
    
    Attributes:
        speed_mps (float): Current vehicle speed [m/s].
        rpm (float): Engine or motor speed [RPM].
    """
    
    def __init__(self, speed_mps: float, rpm: float, message: str = "Powertrain operating limit violated", station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.speed_mps = speed_mps
        self.rpm = rpm
        
    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | Speed: {self.speed_mps:.2f} m/s, RPM: {self.rpm:.2f}"
        
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "speed_mps": self.speed_mps,
            "rpm": self.rpm
        })
        return data


class EnergyBudgetError(LapSimError):
    """
    Raised when the energy budget (e.g., ERS allocation or battery capacity) is exceeded.
    
    Attributes:
        soc (float): Current State of Charge or energy level.
        limit (float): The minimum limit that was violated.
    """
    
    def __init__(self, soc: float, limit: float, message: str = "Energy budget exceeded", station_index: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, station_index, context)
        self.soc = soc
        self.limit = limit
        
    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | SOC: {self.soc:.4f}, Limit: {self.limit:.4f}"
        
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "soc": self.soc,
            "limit": self.limit
        })
        return data
