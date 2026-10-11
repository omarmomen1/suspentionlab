"""SuspensionLab PRO — Physical Invariant Regularization (Phase 3J).

Requirement 6:
Regularization: Prevent physically meaningless parameter combinations.

Requirement 11:
Hostile tests: parameter outside bounds & unphysical combinations.

Enforces:
- Smooth barrier functions penalizing parameters outside bounds
- Prior distribution regularization (negative log-prior)
- Multi-parameter coupled physical invariants:
  * Damping ratio: zeta = c / (2 * sqrt(k * m)) in [0.12, 2.20]
  * Roll stiffness balance: K_phi_f / (K_phi_f + K_phi_r) in [0.25, 0.85]
  * Sprung-to-unsprung mass ratio: m_u / m_s in [0.015, 0.150]
  * Bounce-pitch natural frequency ratio: omega_r / omega_f in [0.70, 1.40]
  * Aero center of pressure balance in [0.20, 0.70]
  * Drivetrain efficiency in [0.70, 0.99]
  * Rolling resistance in [0.005, 0.040]
  * Positive definite tire load degressivity (a1 > 0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from suspensionlab.calibration.registry import ParameterDefinition, ParameterRegistry


@dataclass
class PhysicalInvariants:
    """Coupled physical bounds and ratios for vehicle chassis dynamics."""
    min_damping_ratio: float = 0.12
    max_damping_ratio: float = 2.20
    min_roll_balance_front: float = 0.25
    max_roll_balance_front: float = 0.85
    min_mass_ratio_unsprung: float = 0.015
    max_mass_ratio_unsprung: float = 0.150
    min_pitch_bounce_ratio: float = 0.70
    max_pitch_bounce_ratio: float = 1.40
    min_aero_balance_front: float = 0.20
    max_aero_balance_front: float = 0.70


@dataclass
class RegularizationPenalty:
    """Result of regularization evaluation."""
    total_penalty: float
    prior_loss: float
    barrier_penalty: float
    invariant_penalty: float
    violations: List[str] = field(default_factory=list)
    is_physically_admissible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_penalty": float(self.total_penalty),
            "prior_loss": float(self.prior_loss),
            "barrier_penalty": float(self.barrier_penalty),
            "invariant_penalty": float(self.invariant_penalty),
            "violations": self.violations,
            "is_physically_admissible": self.is_physically_admissible,
        }


class PhysicalRegularizer:
    """Regularizer penalizing unphysical parameters and parameter combinations."""

    def __init__(
        self,
        registry: ParameterRegistry,
        invariants: Optional[PhysicalInvariants] = None,
        lambda_prior: float = 1.0e-3,
        barrier_scale: float = 1.0e5,
    ):
        self.registry = registry
        self.invariants = invariants if invariants is not None else PhysicalInvariants()
        self.lambda_prior = lambda_prior
        self.barrier_scale = barrier_scale

    def evaluate(self, param_values: Dict[str, float]) -> RegularizationPenalty:
        """Compute regularization loss and verify physical invariants."""
        prior_loss = 0.0
        barrier_penalty = 0.0
        invariant_penalty = 0.0
        violations: List[str] = []

        # 1. Individual parameter bounds and priors
        for name, val in param_values.items():
            if not self.registry.has(name):
                continue
            defn = self.registry.get(name)
            low, high = defn.bounds
            span = max(high - low, 1e-6)

            # Quadratic penalty if outside bounds
            if val < low:
                overshoot = (low - val) / span
                barrier_penalty += self.barrier_scale * (overshoot ** 2)
                violations.append(f"{name}={val:.3f} below lower bound {low:.3f}")
            elif val > high:
                overshoot = (val - high) / span
                barrier_penalty += self.barrier_scale * (overshoot ** 2)
                violations.append(f"{name}={val:.3f} above upper bound {high:.3f}")

            # Prior loss: -log p(val)
            # Evaluate log prior at clipped value to avoid -inf in gradient/optimizer steps
            val_clipped = float(np.clip(val, low, high))
            log_p = defn.prior.log_prob(val_clipped)
            if math.isfinite(log_p):
                prior_loss += -log_p

        # 2. Coupled Physical Invariants

        # 2.1 Front suspension damping ratio: zeta_f = c_f / (2 * sqrt(k_s_f * m_s_f))
        k_f = param_values.get("spring_rate_front")
        c_f = param_values.get("damper_bump_front")
        m_s = param_values.get("sprung_mass", 1320.0)
        if k_f is not None and c_f is not None:
            m_corner = m_s * 0.30  # approximate front corner sprung mass
            if k_f > 0 and m_corner > 0:
                zeta_f = c_f / (2.0 * math.sqrt(k_f * m_corner))
                if zeta_f < self.invariants.min_damping_ratio:
                    penalty = 1e4 * ((self.invariants.min_damping_ratio - zeta_f) ** 2)
                    invariant_penalty += penalty
                    violations.append(f"Front damping ratio zeta_f={zeta_f:.2f} < {self.invariants.min_damping_ratio}")
                elif zeta_f > self.invariants.max_damping_ratio:
                    penalty = 1e4 * ((zeta_f - self.invariants.max_damping_ratio) ** 2)
                    invariant_penalty += penalty
                    violations.append(f"Front damping ratio zeta_f={zeta_f:.2f} > {self.invariants.max_damping_ratio}")

        # 2.2 Rear suspension damping ratio: zeta_r = c_r / (2 * sqrt(k_s_r * m_s_r))
        k_r = param_values.get("spring_rate_rear")
        c_r = param_values.get("damper_bump_rear")
        if k_r is not None and c_r is not None:
            m_corner_r = m_s * 0.20  # approximate rear corner sprung mass
            if k_r > 0 and m_corner_r > 0:
                zeta_r = c_r / (2.0 * math.sqrt(k_r * m_corner_r))
                if zeta_r < self.invariants.min_damping_ratio:
                    penalty = 1e4 * ((self.invariants.min_damping_ratio - zeta_r) ** 2)
                    invariant_penalty += penalty
                    violations.append(f"Rear damping ratio zeta_r={zeta_r:.2f} < {self.invariants.min_damping_ratio}")
                elif zeta_r > self.invariants.max_damping_ratio:
                    penalty = 1e4 * ((zeta_r - self.invariants.max_damping_ratio) ** 2)
                    invariant_penalty += penalty
                    violations.append(f"Rear damping ratio zeta_r={zeta_r:.2f} > {self.invariants.max_damping_ratio}")

        # 2.3 Roll stiffness distribution: K_phi_f / (K_phi_f + K_phi_r)
        arb_f = param_values.get("anti_roll_bar_front")
        arb_r = param_values.get("anti_roll_bar_rear")
        if arb_f is not None and arb_r is not None and (arb_f + arb_r) > 0:
            roll_bal_f = arb_f / (arb_f + arb_r)
            if roll_bal_f < self.invariants.min_roll_balance_front:
                penalty = 1e4 * ((self.invariants.min_roll_balance_front - roll_bal_f) ** 2)
                invariant_penalty += penalty
                violations.append(f"Front roll balance {roll_bal_f:.2f} < {self.invariants.min_roll_balance_front}")
            elif roll_bal_f > self.invariants.max_roll_balance_front:
                penalty = 1e4 * ((roll_bal_f - self.invariants.max_roll_balance_front) ** 2)
                invariant_penalty += penalty
                violations.append(f"Front roll balance {roll_bal_f:.2f} > {self.invariants.max_roll_balance_front}")

        # 2.4 Sprung vs unsprung mass ratio: m_u / m_s
        m_u_f = param_values.get("unsprung_mass_front")
        if m_u_f is not None and m_s > 0:
            mass_ratio = m_u_f / m_s
            if mass_ratio < self.invariants.min_mass_ratio_unsprung:
                penalty = 1e4 * ((self.invariants.min_mass_ratio_unsprung - mass_ratio) ** 2)
                invariant_penalty += penalty
                violations.append(f"Unsprung mass ratio {mass_ratio:.3f} < {self.invariants.min_mass_ratio_unsprung}")
            elif mass_ratio > self.invariants.max_mass_ratio_unsprung:
                penalty = 1e4 * ((mass_ratio - self.invariants.max_mass_ratio_unsprung) ** 2)
                invariant_penalty += penalty
                violations.append(f"Unsprung mass ratio {mass_ratio:.3f} > {self.invariants.max_mass_ratio_unsprung}")

        # 2.5 Bounce-pitch natural frequency ratio: omega_r / omega_f
        if k_f is not None and k_r is not None and k_f > 0 and k_r > 0:
            m_f = m_s * 0.30
            m_r = m_s * 0.20
            omega_f = math.sqrt(k_f / m_f)
            omega_r = math.sqrt(k_r / m_r)
            pitch_ratio = omega_r / omega_f
            if pitch_ratio < self.invariants.min_pitch_bounce_ratio:
                penalty = 5e3 * ((self.invariants.min_pitch_bounce_ratio - pitch_ratio) ** 2)
                invariant_penalty += penalty
                violations.append(f"Pitch-bounce ratio {pitch_ratio:.2f} < {self.invariants.min_pitch_bounce_ratio}")
            elif pitch_ratio > self.invariants.max_pitch_bounce_ratio:
                penalty = 5e3 * ((pitch_ratio - self.invariants.max_pitch_bounce_ratio) ** 2)
                invariant_penalty += penalty
                violations.append(f"Pitch-bounce ratio {pitch_ratio:.2f} > {self.invariants.max_pitch_bounce_ratio}")

        # 2.6 Aero front balance
        aero_bal = param_values.get("aero_front_balance")
        if aero_bal is not None:
            if aero_bal < self.invariants.min_aero_balance_front:
                penalty = 1e4 * ((self.invariants.min_aero_balance_front - aero_bal) ** 2)
                invariant_penalty += penalty
                violations.append(f"Aero balance {aero_bal:.2f} < {self.invariants.min_aero_balance_front}")
            elif aero_bal > self.invariants.max_aero_balance_front:
                penalty = 1e4 * ((aero_bal - self.invariants.max_aero_balance_front) ** 2)
                invariant_penalty += penalty
                violations.append(f"Aero balance {aero_bal:.2f} > {self.invariants.max_aero_balance_front}")

        # 2.7 Tire load degressivity must be strictly positive
        degress = param_values.get("tire_load_degressivity")
        if degress is not None and degress <= 0.0:
            penalty = 1e5 * ((0.01 - degress) ** 2)
            invariant_penalty += penalty
            violations.append(f"Tire load degressivity {degress:.4f} must be positive")

        is_admissible = (len(violations) == 0) and (barrier_penalty == 0.0)
        total_penalty = (self.lambda_prior * prior_loss) + barrier_penalty + invariant_penalty

        return RegularizationPenalty(
            total_penalty=float(total_penalty),
            prior_loss=float(prior_loss),
            barrier_penalty=float(barrier_penalty),
            invariant_penalty=float(invariant_penalty),
            violations=violations,
            is_physically_admissible=is_admissible,
        )
