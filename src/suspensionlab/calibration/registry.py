"""SuspensionLab PRO — Calibratable Parameter Registry (Phase 3J).

Every calibratable parameter must define:
- name: canonical parameter identifier
- family: one of the 11 authorized physical parameter families
- physical_meaning: physical description of what the parameter represents
- units: dimensional SI or standard engineering units
- nominal_value: reference baseline value
- bounds: (lower_bound, upper_bound)
- prior: probability distribution over allowable parameter values
- source: engineering specification / provenance of nominal value
- model_dependency: models that depend on this parameter
- validity_domain: operating envelope where the parameterization is valid
- observable_channels: physical telemetry channels that provide sensitivity/observability

Do NOT invent parameters simply because they improve optimization.
Only parameters already represented by the model are authorized.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


class ParameterFamily(str, Enum):
    """The 11 authorized physical parameter families represented in SuspensionLab PRO models."""
    TIRE_STIFFNESS = "TIRE_STIFFNESS"
    TIRE_LOAD_SENSITIVITY = "TIRE_LOAD_SENSITIVITY"
    CAMBER_SENSITIVITY = "CAMBER_SENSITIVITY"
    AERO_COEFFICIENTS = "AERO_COEFFICIENTS"
    AERO_BALANCE = "AERO_BALANCE"
    DRIVETRAIN_EFFICIENCY = "DRIVETRAIN_EFFICIENCY"
    ROLLING_RESISTANCE = "ROLLING_RESISTANCE"
    SUSPENSION_STIFFNESS = "SUSPENSION_STIFFNESS"
    DAMPING = "DAMPING"
    MASS_INERTIA = "MASS_INERTIA"
    POWERTRAIN = "POWERTRAIN"


class PriorDistribution(ABC):
    """Abstract base class for parameter prior distributions."""

    @abstractmethod
    def log_prob(self, value: float) -> float:
        """Compute log-prior probability density at value."""
        pass

    @abstractmethod
    def sample(self, size: int = 1, rng: Optional[np.random.Generator] = None) -> np.ndarray:
        """Sample from the prior distribution."""
        pass

    @property
    @abstractmethod
    def mean(self) -> float:
        pass

    @property
    @abstractmethod
    def std(self) -> float:
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


@dataclass
class GaussianPrior(PriorDistribution):
    """Gaussian prior: theta ~ N(mean, std^2)."""
    mu: float
    sigma: float

    def __post_init__(self):
        if self.sigma <= 0:
            raise ValueError(f"Gaussian prior sigma must be positive: {self.sigma}")

    def log_prob(self, value: float) -> float:
        diff = value - self.mu
        return -0.5 * math.log(2.0 * math.pi * (self.sigma ** 2)) - 0.5 * ((diff / self.sigma) ** 2)

    def sample(self, size: int = 1, rng: Optional[np.random.Generator] = None) -> np.ndarray:
        gen = rng if rng is not None else np.random.default_rng()
        return gen.normal(self.mu, self.sigma, size=size)

    @property
    def mean(self) -> float:
        return self.mu

    @property
    def std(self) -> float:
        return self.sigma

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "GaussianPrior",
            "mu": self.mu,
            "sigma": self.sigma,
        }


@dataclass
class UniformPrior(PriorDistribution):
    """Uniform prior: theta ~ U(lower, upper)."""
    lower: float
    upper: float

    def __post_init__(self):
        if self.lower >= self.upper:
            raise ValueError(f"Uniform prior lower ({self.lower}) must be < upper ({self.upper})")

    def log_prob(self, value: float) -> float:
        if self.lower <= value <= self.upper:
            return -math.log(self.upper - self.lower)
        return -float("inf")

    def sample(self, size: int = 1, rng: Optional[np.random.Generator] = None) -> np.ndarray:
        gen = rng if rng is not None else np.random.default_rng()
        return gen.uniform(self.lower, self.upper, size=size)

    @property
    def mean(self) -> float:
        return 0.5 * (self.lower + self.upper)

    @property
    def std(self) -> float:
        return (self.upper - self.lower) / math.sqrt(12.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "UniformPrior",
            "lower": self.lower,
            "upper": self.upper,
        }


@dataclass
class LogNormalPrior(PriorDistribution):
    """Log-normal prior: log(theta) ~ N(log_mu, log_sigma^2)."""
    log_mu: float
    log_sigma: float

    def __post_init__(self):
        if self.log_sigma <= 0:
            raise ValueError(f"LogNormal prior log_sigma must be positive: {self.log_sigma}")

    def log_prob(self, value: float) -> float:
        if value <= 0:
            return -float("inf")
        log_val = math.log(value)
        diff = log_val - self.log_mu
        return (
            -log_val
            - 0.5 * math.log(2.0 * math.pi * (self.log_sigma ** 2))
            - 0.5 * ((diff / self.log_sigma) ** 2)
        )

    def sample(self, size: int = 1, rng: Optional[np.random.Generator] = None) -> np.ndarray:
        gen = rng if rng is not None else np.random.default_rng()
        return gen.lognormal(self.log_mu, self.log_sigma, size=size)

    @property
    def mean(self) -> float:
        return math.exp(self.log_mu + 0.5 * (self.log_sigma ** 2))

    @property
    def std(self) -> float:
        var = (math.exp(self.log_sigma ** 2) - 1.0) * math.exp(2.0 * self.log_mu + (self.log_sigma ** 2))
        return math.sqrt(max(var, 0.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "LogNormalPrior",
            "log_mu": self.log_mu,
            "log_sigma": self.log_sigma,
        }


@dataclass
class ValidityDomain:
    """Rigorous physical validity envelope for a parameter."""
    min_operational: float
    max_operational: float
    speed_range_mps: Tuple[float, float] = (0.0, 100.0)
    temperature_range_c: Tuple[float, float] = (-10.0, 85.0)
    normal_force_range_n: Tuple[float, float] = (0.0, 20000.0)
    notes: str = ""

    def contains(self, value: float) -> bool:
        return self.min_operational <= value <= self.max_operational

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_operational": self.min_operational,
            "max_operational": self.max_operational,
            "speed_range_mps": list(self.speed_range_mps),
            "temperature_range_c": list(self.temperature_range_c),
            "normal_force_range_n": list(self.normal_force_range_n),
            "notes": self.notes,
        }


@dataclass
class ParameterDefinition:
    """Full scientific metadata for a calibratable physical parameter."""
    name: str
    family: ParameterFamily
    physical_meaning: str
    units: str
    nominal_value: float
    bounds: Tuple[float, float]
    prior: PriorDistribution
    source: str
    model_dependency: List[str]
    validity_domain: ValidityDomain
    observable_channels: List[str] = field(default_factory=list)

    def __post_init__(self):
        low, high = self.bounds
        if low >= high:
            raise ValueError(f"Parameter '{self.name}' has invalid bounds: lower {low} >= upper {high}")
        if not (low <= self.nominal_value <= high):
            raise ValueError(
                f"Parameter '{self.name}' nominal value {self.nominal_value} is outside bounds [{low}, {high}]"
            )

    def validate_value(self, value: float) -> Tuple[bool, Optional[str]]:
        low, high = self.bounds
        if value < low or value > high:
            return False, f"Value {value} violates physical bounds [{low}, {high}] for {self.name}"
        if not self.validity_domain.contains(value):
            return False, f"Value {value} is outside operational domain [{self.validity_domain.min_operational}, {self.validity_domain.max_operational}]"
        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family.value,
            "physical_meaning": self.physical_meaning,
            "units": self.units,
            "nominal_value": self.nominal_value,
            "bounds": list(self.bounds),
            "prior": self.prior.to_dict(),
            "source": self.source,
            "model_dependency": self.model_dependency,
            "validity_domain": self.validity_domain.to_dict(),
            "observable_channels": self.observable_channels,
        }


class ParameterRegistry:
    """Authoritative registry for all calibratable vehicle parameters."""

    def __init__(self):
        self._registry: Dict[str, ParameterDefinition] = {}

    def register(self, definition: ParameterDefinition) -> None:
        """Register a parameter definition."""
        if definition.name in self._registry:
            raise ValueError(f"Parameter '{definition.name}' is already registered in registry.")
        self._registry[definition.name] = definition

    def get(self, name: str) -> ParameterDefinition:
        """Retrieve a parameter definition by name."""
        if name not in self._registry:
            raise KeyError(
                f"Parameter '{name}' not found in registry. Authorized parameters: {list(self._registry.keys())}"
            )
        return self._registry[name]

    def has(self, name: str) -> bool:
        return name in self._registry

    def list_all(self) -> List[ParameterDefinition]:
        return list(self._registry.values())

    def list_names(self) -> List[str]:
        return list(self._registry.keys())

    def get_by_family(self, family: ParameterFamily) -> List[ParameterDefinition]:
        return [p for p in self._registry.values() if p.family == family]

    def to_dict(self) -> Dict[str, Any]:
        return {name: p.to_dict() for name, p in self._registry.items()}


def create_standard_registry() -> ParameterRegistry:
    """Create the authoritative standard parameter registry with all 11 parameter families."""
    reg = ParameterRegistry()

    # 1. TIRE_STIFFNESS
    reg.register(ParameterDefinition(
        name="k_tire_front",
        family=ParameterFamily.TIRE_STIFFNESS,
        physical_meaning="Radial vertical stiffness of front tire carcass under radial compression",
        units="N/m",
        nominal_value=210000.0,
        bounds=(120000.0, 320000.0),
        prior=GaussianPrior(mu=210000.0, sigma=25000.0),
        source="Pirelli P-Zero Trofeo R 235/35R19 OEM Cleat Test Rig",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=100000.0, max_operational=350000.0, notes="Radial inflation pressure 2.0-3.0 bar"),
        observable_channels=["vert_g", "wheelspeed_fl", "wheelspeed_fr", "damper_fl"],
    ))
    reg.register(ParameterDefinition(
        name="k_tire_rear",
        family=ParameterFamily.TIRE_STIFFNESS,
        physical_meaning="Radial vertical stiffness of rear tire carcass under radial compression",
        units="N/m",
        nominal_value=210000.0,
        bounds=(120000.0, 320000.0),
        prior=GaussianPrior(mu=210000.0, sigma=25000.0),
        source="Pirelli P-Zero Trofeo R 235/35R19 OEM Cleat Test Rig",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=100000.0, max_operational=350000.0),
        observable_channels=["vert_g", "wheelspeed_rl", "wheelspeed_rr", "damper_rl"],
    ))
    reg.register(ParameterDefinition(
        name="cornering_stiff_front",
        family=ParameterFamily.TIRE_STIFFNESS,
        physical_meaning="Total cornering stiffness of front axle tires at zero slip angle (C_alpha_f)",
        units="N/rad",
        nominal_value=85000.0,
        bounds=(40000.0, 160000.0),
        prior=GaussianPrior(mu=85000.0, sigma=15000.0),
        source="Calspan Tire Research Facility (TIRF) Flat Belt Dynamometer",
        model_dependency=["HandlingBicycleModel", "FullCar7DOF", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=35000.0, max_operational=180000.0, speed_range_mps=(5.0, 90.0)),
        observable_channels=["ay", "yaw_rate", "steering", "slip_angle"],
    ))
    reg.register(ParameterDefinition(
        name="cornering_stiff_rear",
        family=ParameterFamily.TIRE_STIFFNESS,
        physical_meaning="Total cornering stiffness of rear axle tires at zero slip angle (C_alpha_r)",
        units="N/rad",
        nominal_value=95000.0,
        bounds=(45000.0, 180000.0),
        prior=GaussianPrior(mu=95000.0, sigma=15000.0),
        source="Calspan Tire Research Facility (TIRF) Flat Belt Dynamometer",
        model_dependency=["HandlingBicycleModel", "FullCar7DOF", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=40000.0, max_operational=200000.0, speed_range_mps=(5.0, 90.0)),
        observable_channels=["ay", "yaw_rate", "steering", "slip_angle"],
    ))

    # 2. TIRE_LOAD_SENSITIVITY
    reg.register(ParameterDefinition(
        name="tire_load_degressivity",
        family=ParameterFamily.TIRE_LOAD_SENSITIVITY,
        physical_meaning="Degressivity parameter governing normalized friction reduction with increased vertical load (mu_peak vs Fz)",
        units="1/kN",
        nominal_value=0.150,
        bounds=(0.020, 0.500),
        prior=GaussianPrior(mu=0.150, sigma=0.040),
        source="Pacejka MF5.2 empirical fit coefficient (a1/a2 curvature)",
        model_dependency=["PacejkaMF52TireModel", "FullCar7DOF", "HandlingBicycleModel"],
        validity_domain=ValidityDomain(min_operational=0.010, max_operational=0.600, normal_force_range_n=(500.0, 15000.0)),
        observable_channels=["ay", "ax", "yaw_rate"],
    ))

    # 3. CAMBER_SENSITIVITY
    reg.register(ParameterDefinition(
        name="camber_stiffness_front",
        family=ParameterFamily.CAMBER_SENSITIVITY,
        physical_meaning="Camber thrust stiffness coefficient C_gamma for front tires (lateral force generated per radian of inclination angle)",
        units="N/rad",
        nominal_value=6500.0,
        bounds=(2000.0, 15000.0),
        prior=GaussianPrior(mu=6500.0, sigma=1500.0),
        source="Flat-belt camber thrust sweep data (Pacejka C_gamma0)",
        model_dependency=["HandlingBicycleModel", "FullCar7DOF", "KinematicsFacade"],
        validity_domain=ValidityDomain(min_operational=1500.0, max_operational=18000.0),
        observable_channels=["ay", "yaw_rate", "roll_angle"],
    ))
    reg.register(ParameterDefinition(
        name="camber_stiffness_rear",
        family=ParameterFamily.CAMBER_SENSITIVITY,
        physical_meaning="Camber thrust stiffness coefficient C_gamma for rear tires",
        units="N/rad",
        nominal_value=7000.0,
        bounds=(2000.0, 15000.0),
        prior=GaussianPrior(mu=7000.0, sigma=1500.0),
        source="Flat-belt camber thrust sweep data (Pacejka C_gamma0)",
        model_dependency=["HandlingBicycleModel", "FullCar7DOF", "KinematicsFacade"],
        validity_domain=ValidityDomain(min_operational=1500.0, max_operational=18000.0),
        observable_channels=["ay", "yaw_rate", "roll_angle"],
    ))

    # 4. AERO_COEFFICIENTS
    reg.register(ParameterDefinition(
        name="aero_cd",
        family=ParameterFamily.AERO_COEFFICIENTS,
        physical_meaning="Total aerodynamic drag coefficient (Cd) multiplied by frontal area (Cd*A or dimensionless Cd)",
        units="-",
        nominal_value=0.320,
        bounds=(0.220, 0.550),
        prior=GaussianPrior(mu=0.320, sigma=0.030),
        source="Volkswagen Group Wind Tunnel Acoustic & Aerodynamic Calibration (Wolfsburg)",
        model_dependency=["PowertrainLongitudinalModel", "DynamicLapSim", "FullCar7DOF"],
        validity_domain=ValidityDomain(min_operational=0.200, max_operational=0.600, speed_range_mps=(15.0, 90.0)),
        observable_channels=["Vx", "ax", "throttle", "engine_rpm"],
    ))
    reg.register(ParameterDefinition(
        name="aero_cl",
        family=ParameterFamily.AERO_COEFFICIENTS,
        physical_meaning="Total aerodynamic lift/downforce coefficient (negative indicates downforce)",
        units="-",
        nominal_value=-0.150,
        bounds=(-1.200, 0.200),
        prior=GaussianPrior(mu=-0.150, sigma=0.080),
        source="Wind Tunnel Balance Scaled Telemetry Polar",
        model_dependency=["FullCar7DOF", "DynamicLapSim", "HandlingBicycleModel"],
        validity_domain=ValidityDomain(min_operational=-1.500, max_operational=0.300, speed_range_mps=(20.0, 90.0)),
        observable_channels=["vert_g", "damper_fl", "damper_fr", "damper_rl", "damper_rr"],
    ))

    # 5. AERO_BALANCE
    reg.register(ParameterDefinition(
        name="aero_front_balance",
        family=ParameterFamily.AERO_BALANCE,
        physical_meaning="Aerodynamic center of pressure / downforce distribution percentage acting on front axle",
        units="-",
        nominal_value=0.420,
        bounds=(0.250, 0.650),
        prior=GaussianPrior(mu=0.420, sigma=0.050),
        source="Front splitter / rear wing chord balance analysis",
        model_dependency=["FullCar7DOF", "HandlingBicycleModel", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=0.200, max_operational=0.700, speed_range_mps=(20.0, 90.0)),
        observable_channels=["damper_fl", "damper_rl", "pitch_angle", "ay"],
    ))

    # 6. DRIVETRAIN_EFFICIENCY
    reg.register(ParameterDefinition(
        name="drivetrain_efficiency",
        family=ParameterFamily.DRIVETRAIN_EFFICIENCY,
        physical_meaning="Lumped mechanical transmission and final drive power efficiency (eta_dt)",
        units="-",
        nominal_value=0.920,
        bounds=(0.750, 0.980),
        prior=GaussianPrior(mu=0.920, sigma=0.030),
        source="BorgWarner DQ250 Dual-Clutch Transmission Dynamometer Efficiency Map",
        model_dependency=["PowertrainLongitudinalModel", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=0.700, max_operational=0.990),
        observable_channels=["Vx", "ax", "engine_rpm", "throttle", "gear"],
    ))

    # 7. ROLLING_RESISTANCE
    reg.register(ParameterDefinition(
        name="rolling_resistance_coeff",
        family=ParameterFamily.ROLLING_RESISTANCE,
        physical_meaning="Baseline zero-speed rolling resistance coefficient (C_rr0) under ISO 28580 test conditions",
        units="-",
        nominal_value=0.012,
        bounds=(0.006, 0.035),
        prior=GaussianPrior(mu=0.012, sigma=0.003),
        source="ISO 28580 Laboratory Drum Rolling Resistance Rating",
        model_dependency=["PowertrainLongitudinalModel", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=0.005, max_operational=0.040),
        observable_channels=["Vx", "ax"],
    ))

    # 8. SUSPENSION_STIFFNESS
    reg.register(ParameterDefinition(
        name="spring_rate_front",
        family=ParameterFamily.SUSPENSION_STIFFNESS,
        physical_meaning="Linear coil spring rate at front suspension corner (k_s_f)",
        units="N/m",
        nominal_value=32000.0,
        bounds=(15000.0, 75000.0),
        prior=GaussianPrior(mu=32000.0, sigma=4000.0),
        source="KW Clubsport 2-way Coilover Bench Spring Dyno",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HalfCarModel"],
        validity_domain=ValidityDomain(min_operational=12000.0, max_operational=90000.0),
        observable_channels=["vert_g", "damper_fl", "damper_fr", "roll_angle"],
    ))
    reg.register(ParameterDefinition(
        name="spring_rate_rear",
        family=ParameterFamily.SUSPENSION_STIFFNESS,
        physical_meaning="Linear coil spring rate at rear suspension corner (k_s_r)",
        units="N/m",
        nominal_value=36000.0,
        bounds=(15000.0, 85000.0),
        prior=GaussianPrior(mu=36000.0, sigma=4000.0),
        source="KW Clubsport 2-way Coilover Bench Spring Dyno",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HalfCarModel"],
        validity_domain=ValidityDomain(min_operational=12000.0, max_operational=95000.0),
        observable_channels=["vert_g", "damper_rl", "damper_rr", "pitch_angle"],
    ))
    reg.register(ParameterDefinition(
        name="anti_roll_bar_front",
        family=ParameterFamily.SUSPENSION_STIFFNESS,
        physical_meaning="Torsional roll stiffness contributed by front anti-roll bar (K_phi_f_arb)",
        units="N*m/rad",
        nominal_value=35000.0,
        bounds=(10000.0, 90000.0),
        prior=GaussianPrior(mu=35000.0, sigma=6000.0),
        source="H&R Solid Anti-Roll Bar Torsional Test Rig (26mm OD)",
        model_dependency=["FullCar7DOF", "HandlingBicycleModel"],
        validity_domain=ValidityDomain(min_operational=8000.0, max_operational=100000.0),
        observable_channels=["roll_angle", "ay", "damper_fl", "damper_fr"],
    ))
    reg.register(ParameterDefinition(
        name="anti_roll_bar_rear",
        family=ParameterFamily.SUSPENSION_STIFFNESS,
        physical_meaning="Torsional roll stiffness contributed by rear anti-roll bar (K_phi_r_arb)",
        units="N*m/rad",
        nominal_value=25000.0,
        bounds=(5000.0, 70000.0),
        prior=GaussianPrior(mu=25000.0, sigma=5000.0),
        source="H&R Solid Anti-Roll Bar Torsional Test Rig (24mm OD)",
        model_dependency=["FullCar7DOF", "HandlingBicycleModel"],
        validity_domain=ValidityDomain(min_operational=4000.0, max_operational=80000.0),
        observable_channels=["roll_angle", "ay", "damper_rl", "damper_rr"],
    ))

    # 9. DAMPING
    reg.register(ParameterDefinition(
        name="damper_bump_front",
        family=ParameterFamily.DAMPING,
        physical_meaning="Front shock absorber low/mid-speed compression damping rate (c_bump_f)",
        units="N*s/m",
        nominal_value=2200.0,
        bounds=(800.0, 5500.0),
        prior=GaussianPrior(mu=2200.0, sigma=350.0),
        source="Roehrig 2VS Damper Dyno (velocity sweep 0.05-0.50 m/s)",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HalfCarModel"],
        validity_domain=ValidityDomain(min_operational=600.0, max_operational=6500.0),
        observable_channels=["vert_g", "damper_fl", "damper_fr"],
    ))
    reg.register(ParameterDefinition(
        name="damper_bump_rear",
        family=ParameterFamily.DAMPING,
        physical_meaning="Rear shock absorber low/mid-speed compression damping rate (c_bump_r)",
        units="N*s/m",
        nominal_value=2400.0,
        bounds=(800.0, 6000.0),
        prior=GaussianPrior(mu=2400.0, sigma=350.0),
        source="Roehrig 2VS Damper Dyno (velocity sweep 0.05-0.50 m/s)",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HalfCarModel"],
        validity_domain=ValidityDomain(min_operational=600.0, max_operational=7000.0),
        observable_channels=["vert_g", "damper_rl", "damper_rr"],
    ))
    reg.register(ParameterDefinition(
        name="damper_rebound_front",
        family=ParameterFamily.DAMPING,
        physical_meaning="Front shock absorber rebound damping rate (c_rebound_f)",
        units="N*s/m",
        nominal_value=3500.0,
        bounds=(1200.0, 8500.0),
        prior=GaussianPrior(mu=3500.0, sigma=500.0),
        source="Roehrig 2VS Damper Dyno (velocity sweep 0.05-0.50 m/s)",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HalfCarModel"],
        validity_domain=ValidityDomain(min_operational=1000.0, max_operational=9500.0),
        observable_channels=["vert_g", "damper_fl", "damper_fr"],
    ))
    reg.register(ParameterDefinition(
        name="damper_rebound_rear",
        family=ParameterFamily.DAMPING,
        physical_meaning="Rear shock absorber rebound damping rate (c_rebound_r)",
        units="N*s/m",
        nominal_value=3800.0,
        bounds=(1200.0, 9000.0),
        prior=GaussianPrior(mu=3800.0, sigma=500.0),
        source="Roehrig 2VS Damper Dyno (velocity sweep 0.05-0.50 m/s)",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HalfCarModel"],
        validity_domain=ValidityDomain(min_operational=1000.0, max_operational=10000.0),
        observable_channels=["vert_g", "damper_rl", "damper_rr"],
    ))

    # 10. MASS_INERTIA
    reg.register(ParameterDefinition(
        name="sprung_mass",
        family=ParameterFamily.MASS_INERTIA,
        physical_meaning="Total sprung vehicle body chassis mass (m_s = m_total - sum(m_u))",
        units="kg",
        nominal_value=1320.0,
        bounds=(900.0, 1900.0),
        prior=GaussianPrior(mu=1320.0, sigma=60.0),
        source="Intercomp 4-pad Electronic Corner Weight Scales with 75kg driver",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF", "HandlingBicycleModel", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=850.0, max_operational=2100.0),
        observable_channels=["ax", "ay", "vert_g", "damper_fl", "damper_rl"],
    ))
    reg.register(ParameterDefinition(
        name="unsprung_mass_front",
        family=ParameterFamily.MASS_INERTIA,
        physical_meaning="Unsprung corner mass (knuckle, hub, rotor, wheel, tire, half-control-arm)",
        units="kg",
        nominal_value=42.0,
        bounds=(25.0, 70.0),
        prior=GaussianPrior(mu=42.0, sigma=4.0),
        source="Component teardown scale measurements",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF"],
        validity_domain=ValidityDomain(min_operational=20.0, max_operational=80.0),
        observable_channels=["vert_g", "wheelspeed_fl", "wheelspeed_fr"],
    ))
    reg.register(ParameterDefinition(
        name="unsprung_mass_rear",
        family=ParameterFamily.MASS_INERTIA,
        physical_meaning="Unsprung corner mass for rear suspension corner",
        units="kg",
        nominal_value=38.0,
        bounds=(20.0, 65.0),
        prior=GaussianPrior(mu=38.0, sigma=4.0),
        source="Component teardown scale measurements",
        model_dependency=["QuarterCarRideModel", "FullCar7DOF"],
        validity_domain=ValidityDomain(min_operational=18.0, max_operational=75.0),
        observable_channels=["vert_g", "wheelspeed_rl", "wheelspeed_rr"],
    ))
    reg.register(ParameterDefinition(
        name="yaw_inertia_Izz",
        family=ParameterFamily.MASS_INERTIA,
        physical_meaning="Vehicle principal moment of inertia about the z-axis (yaw inertia I_zz)",
        units="kg*m^2",
        nominal_value=2150.0,
        bounds=(1200.0, 3800.0),
        prior=GaussianPrior(mu=2150.0, sigma=180.0),
        source="Trifilar pendulum inertial measurement rig",
        model_dependency=["HandlingBicycleModel", "FullCar7DOF", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=1000.0, max_operational=4200.0),
        observable_channels=["yaw_rate", "ay", "steering"],
    ))

    # 11. POWERTRAIN
    reg.register(ParameterDefinition(
        name="engine_peak_torque",
        family=ParameterFamily.POWERTRAIN,
        physical_meaning="Maximum wide-open throttle engine crankshaft torque (T_max)",
        units="N*m",
        nominal_value=370.0,
        bounds=(200.0, 600.0),
        prior=GaussianPrior(mu=370.0, sigma=30.0),
        source="SuperFlow Engine Dynamometer (EA888 Gen 3 2.0 TSI calibration)",
        model_dependency=["PowertrainLongitudinalModel", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=180.0, max_operational=650.0),
        observable_channels=["ax", "Vx", "engine_rpm", "throttle"],
    ))
    reg.register(ParameterDefinition(
        name="final_drive_ratio",
        family=ParameterFamily.POWERTRAIN,
        physical_meaning="Differential final drive reduction ratio (N_diff)",
        units="-",
        nominal_value=3.820,
        bounds=(2.500, 5.500),
        prior=GaussianPrior(mu=3.820, sigma=0.150),
        source="Volkswagen DQ250 Transaxle Technical Spec",
        model_dependency=["PowertrainLongitudinalModel", "DynamicLapSim"],
        validity_domain=ValidityDomain(min_operational=2.000, max_operational=6.000),
        observable_channels=["Vx", "engine_rpm", "gear"],
    ))
    reg.register(ParameterDefinition(
        name="shift_duration_s",
        family=ParameterFamily.POWERTRAIN,
        physical_meaning="Duration of clutch handover during dual-clutch transmission shift event (delta_t_shift)",
        units="s",
        nominal_value=0.080,
        bounds=(0.020, 0.350),
        prior=GaussianPrior(mu=0.080, sigma=0.015),
        source="TCU CAN bus clutch pressure handover log analysis",
        model_dependency=["TransmissionStateMachine", "PowertrainLongitudinalModel"],
        validity_domain=ValidityDomain(min_operational=0.010, max_operational=0.500),
        observable_channels=["ax", "engine_rpm", "gear"],
    ))
    reg.register(ParameterDefinition(
        name="clutch_inertia",
        family=ParameterFamily.POWERTRAIN,
        physical_meaning="Rotational moment of inertia of dual-clutch pack and flywheel (J_clutch)",
        units="kg*m^2",
        nominal_value=0.120,
        bounds=(0.040, 0.400),
        prior=GaussianPrior(mu=0.120, sigma=0.020),
        source="Dual mass flywheel CAD assembly inertia ledger",
        model_dependency=["TransmissionStateMachine", "PowertrainLongitudinalModel"],
        validity_domain=ValidityDomain(min_operational=0.030, max_operational=0.500),
        observable_channels=["engine_rpm", "ax"],
    ))

    return reg


STANDARD_PARAMETER_REGISTRY = create_standard_registry()
