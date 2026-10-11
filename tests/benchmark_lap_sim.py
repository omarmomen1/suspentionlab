"""
tests/benchmark_lap_sim.py
==========================
SuspensionLab PRO — Quasi-Steady-State Lap Simulator Performance Benchmark

Comprehensive benchmarking suite measuring execution speed, throughput, numerical
stability, and peak memory consumption for the 4-wheel quasi-steady-state (QSS)
lap time simulator.

Scenarios Benchmarked
---------------------
1. Single Lap: Wall-clock latency of apex velocity equilibrium and forward-backward
   speed integration on a representative 5,000 m circuit.
2. GGV Build: Generation of the multi-speed, multi-lateral acceleration envelope
   table with combined-slip Pacejka MF 5.2 tire forces.
3. 10 Laps (repeated): Consecutive lap solve throughput and cache consistency.
4. 100 Candidates: Batch evaluation of 100 suspension setups with varied front and
   rear spring rates, tracking failure rates and convergence.
5. Peak Memory: Memory profiling via stdlib tracemalloc during a 100-candidate batch.

Physics Formulation & References
---------------------------------
- Curvature definition: kappa(s) = 1 / R(s) [1/m]
- Frenet-Serret heading relation: dpsi/ds = kappa(s) [rad/m]
- Roll stiffness per axle: K_phi = (k_spring + k_arb) * track^2 / 2 [Nm/rad]
- Power-limited terminal velocity: P_max = F_drag * v -> v = (2 * P / (rho * Cd * A))^(1/3) [m/s]
- Milliken & Milliken, "Race Car Vehicle Dynamics", SAE 1995.
- Pacejka, H.B., "Tire and Vehicle Dynamics", 3rd Ed., Elsevier 2012.
"""

from __future__ import annotations

import copy
import math
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from suspensionlab.physics.lap_sim import (
    AeroMap,
    LapSimResult,
    LapSimVehicle,
    MassProperties,
    PowertrainModel,
    TrackSegment,
    parse_track_from_curvature,
    solve_lap,
)
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Result Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SingleLapBenchmarkResult:
    """Benchmark result for single lap simulation execution.

    Attributes
    ----------
    elapsed_time_s : float
        Elapsed wall-clock execution time [s].
    lap_time_s : float
        Simulated lap time [s].
    converged : bool
        Whether the solver achieved convergence without NaN or unphysical values.
    """
    elapsed_time_s: float
    lap_time_s: float
    converged: bool

    def __post_init__(self) -> None:
        if math.isnan(self.elapsed_time_s) or self.elapsed_time_s < 0.0:
            raise ValueError(f"Elapsed time must be non-negative, got {self.elapsed_time_s}")
        if math.isnan(self.lap_time_s) or self.lap_time_s <= 0.0:
            raise ValueError(f"Lap time must be strictly positive, got {self.lap_time_s}")


@dataclass
class GGVBuildBenchmarkResult:
    """Benchmark result for GGV envelope computation.

    Attributes
    ----------
    elapsed_time_s : float
        Elapsed wall-clock execution time [s].
    n_speeds : int
        Number of speed evaluation grid points [-].
    n_ay : int
        Number of lateral acceleration fraction evaluation points [-].
    v_term_mps : float
        Power-limited terminal velocity [m/s].
    """
    elapsed_time_s: float
    n_speeds: int
    n_ay: int
    v_term_mps: float

    def __post_init__(self) -> None:
        if math.isnan(self.elapsed_time_s) or self.elapsed_time_s < 0.0:
            raise ValueError(f"Elapsed time must be non-negative, got {self.elapsed_time_s}")
        if self.n_speeds < 2 or self.n_ay < 2:
            raise ValueError(f"Grid dimensions must be >= 2, got ({self.n_speeds}, {self.n_ay})")
        if math.isnan(self.v_term_mps) or self.v_term_mps <= 0.0:
            raise ValueError(f"Terminal velocity must be strictly positive, got {self.v_term_mps}")


@dataclass
class RepeatedLapsBenchmarkResult:
    """Benchmark result for repeated consecutive lap simulations.

    Attributes
    ----------
    total_time_s : float
        Total elapsed wall-clock execution time for all iterations [s].
    avg_time_s : float
        Average execution time per lap simulation [s].
    num_laps : int
        Number of consecutive laps simulated [-].
    all_converged : bool
        Whether all simulated laps completed successfully with valid convergence.
    """
    total_time_s: float
    avg_time_s: float
    num_laps: int
    all_converged: bool

    def __post_init__(self) -> None:
        if math.isnan(self.total_time_s) or self.total_time_s < 0.0:
            raise ValueError(f"Total time must be non-negative, got {self.total_time_s}")
        if math.isnan(self.avg_time_s) or self.avg_time_s < 0.0:
            raise ValueError(f"Average time must be non-negative, got {self.avg_time_s}")
        if self.num_laps <= 0:
            raise ValueError(f"Number of laps must be strictly positive, got {self.num_laps}")


@dataclass
class CandidateSweepBenchmarkResult:
    """Benchmark result for batch candidate setup parameter sweeps.

    Attributes
    ----------
    total_time_s : float
        Total elapsed wall-clock execution time for the entire batch [s].
    avg_time_s : float
        Average execution time per candidate setup [s].
    num_candidates : int
        Total number of candidate suspension setups evaluated [-].
    failed_count : int
        Number of candidate evaluations that raised exceptions or failed convergence [-].
    """
    total_time_s: float
    avg_time_s: float
    num_candidates: int
    failed_count: int

    def __post_init__(self) -> None:
        if math.isnan(self.total_time_s) or self.total_time_s < 0.0:
            raise ValueError(f"Total time must be non-negative, got {self.total_time_s}")
        if math.isnan(self.avg_time_s) or self.avg_time_s < 0.0:
            raise ValueError(f"Average time must be non-negative, got {self.avg_time_s}")
        if self.num_candidates <= 0:
            raise ValueError(f"Candidate count must be strictly positive, got {self.num_candidates}")
        if self.failed_count < 0 or self.failed_count > self.num_candidates:
            raise ValueError(f"Failed count must be within [0, {self.num_candidates}], got {self.failed_count}")


@dataclass
class MemoryBenchmarkResult:
    """Benchmark result for memory consumption during candidate batching.

    Attributes
    ----------
    peak_memory_mb : float
        Peak memory allocated during batch execution [MB].
    current_memory_mb : float
        Current memory allocation after batch execution [MB].
    num_candidates : int
        Number of candidates executed during memory profiling [-].
    """
    peak_memory_mb: float
    current_memory_mb: float
    num_candidates: int

    def __post_init__(self) -> None:
        if math.isnan(self.peak_memory_mb) or self.peak_memory_mb < 0.0:
            raise ValueError(f"Peak memory must be non-negative, got {self.peak_memory_mb}")
        if math.isnan(self.current_memory_mb) or self.current_memory_mb < 0.0:
            raise ValueError(f"Current memory must be non-negative, got {self.current_memory_mb}")
        if self.num_candidates <= 0:
            raise ValueError(f"Candidate count must be strictly positive, got {self.num_candidates}")


@dataclass
class LapSimBenchmarkSuiteResult:
    """Aggregated benchmark suite results containing all five benchmark scenarios."""
    single_lap: SingleLapBenchmarkResult
    ggv_build: GGVBuildBenchmarkResult
    repeated_laps: RepeatedLapsBenchmarkResult
    candidate_sweep: CandidateSweepBenchmarkResult
    memory_usage: MemoryBenchmarkResult


# ─────────────────────────────────────────────────────────────────────────────
# Factory Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_default_vehicle() -> LapSimVehicle:
    """Create a default racing prototype vehicle for QSS lap simulation.

    Configures a representative sports prototype race car with:
    - Mass: 800 kg total, 50:50 static distribution, CoG height 0.30 m
    - Aero: Base CL 1.80, CD 0.95, frontal area 1.70 m², 45% front CoP
    - Powertrain: 6-speed sequential transmission, 12,000 RPM redline
    - Tires: Canonical Pacejka MF 5.2 combined-slip parameters
    - Suspension: 35 kN/m front, 45 kN/m rear springs; 15 kN/m front, 10 kN/m rear ARB

    Returns
    -------
    LapSimVehicle
        Pre-configured vehicle instance ready for simulation.
    """
    mass = MassProperties(
        total_mass=800.0,
        h_cog=0.30,
        wheelbase=2.70,
        cog_dist_front=1.35,
        track_front=1.55,
        track_rear=1.52,
    )
    aero = AeroMap(
        cl_base=1.80,
        cd_base=0.95,
        frontal_area=1.70,
        cop_fraction=0.45,
        rho_air=1.225,
        cl_rh_sens=0.0,
        cl_pitch_sens=0.0,
    )
    powertrain = PowertrainModel(
        gear_ratios=[13.5, 9.8, 7.4, 5.9, 4.8, 4.0],
        torque_curve_rpm=[2000.0, 4000.0, 6000.0, 8000.0, 10000.0, 12000.0],
        torque_curve_nm=[290.0, 310.0, 315.0, 300.0, 270.0, 220.0],
        rev_limit=12000.0,
        wheel_radius=0.305,
        drivetrain_loss=0.12,
        shift_time_s=0.05,
        max_brake_force_n=28000.0,
        brake_front_bias=0.65,
    )
    tire_coeffs = TireCoeffs()
    suspension = SuspensionConfig(
        k_spring_front=35000.0,
        k_spring_rear=45000.0,
        k_arb_front=15000.0,
        k_arb_rear=10000.0,
        motion_ratio_front=0.85,
        motion_ratio_rear=0.90,
        ride_height_front=30.0,
        ride_height_rear=60.0,
    )
    return LapSimVehicle(
        mass_props=mass,
        aero=aero,
        powertrain=powertrain,
        tire_coeffs=tire_coeffs,
        suspension=suspension,
        use_coupling=False,
    )


def make_test_track(n_points: int = 500, length_m: float = 5000.0) -> List[TrackSegment]:
    """Create a realistic synthetic racetrack with varying curvature.

    Features a realistic circuit geometry combining high-speed straights,
    medium-speed sweepers, a tight hairpin, and a technical S-bend chicane.
    Curvature transitions use C1-smooth squared-sine windowing to prevent
    spurious curvature discontinuities (|dkappa/ds| <= 0.01 1/m²).

    Parameters
    ----------
    n_points : int, default=500
        Total number of discretized station points along the circuit [-].
    length_m : float, default=5000.0
        Total cumulative circuit length [m].

    Returns
    -------
    list[TrackSegment]
        Discretized track station points with monotonic distances, valid curvatures,
        integrated Frenet-Serret headings, and sector divisions.
    """
    if n_points < 2:
        raise ValueError(f"Track must contain at least 2 points, got {n_points}")
    if length_m <= 0.0:
        raise ValueError(f"Track length must be strictly positive, got {length_m}")

    distances = np.linspace(0.0, float(length_m), int(n_points))
    curvatures = np.zeros(n_points, dtype=float)

    # Corner 1: Medium-speed right-hander R=80 m (kappa = 0.0125 1/m)
    # Location: 16% to 28% of track length (800 m to 1400 m on 5000 m circuit)
    s_c1_start = 0.16 * length_m
    s_c1_end = 0.28 * length_m
    mask_c1 = (distances >= s_c1_start) & (distances <= s_c1_end)
    if np.any(mask_c1):
        u1 = (distances[mask_c1] - s_c1_start) / (s_c1_end - s_c1_start)
        curvatures[mask_c1] = 0.0125 * (np.sin(np.pi * u1) ** 2)

    # Corner 2: Tight hairpin left-hander R=40 m (kappa = -0.025 1/m)
    # Location: 40% to 52% of track length (2000 m to 2600 m on 5000 m circuit)
    s_c2_start = 0.40 * length_m
    s_c2_end = 0.52 * length_m
    mask_c2 = (distances >= s_c2_start) & (distances <= s_c2_end)
    if np.any(mask_c2):
        u2 = (distances[mask_c2] - s_c2_start) / (s_c2_end - s_c2_start)
        curvatures[mask_c2] = -0.025 * (np.sin(np.pi * u2) ** 2)

    # Corner 3: Technical chicane S-bend (kappa = +/- 0.016 1/m)
    # Location: 64% to 80% of track length (3200 m to 4000 m on 5000 m circuit)
    s_c3_start = 0.64 * length_m
    s_c3_end = 0.80 * length_m
    mask_c3 = (distances >= s_c3_start) & (distances <= s_c3_end)
    if np.any(mask_c3):
        u3 = (distances[mask_c3] - s_c3_start) / (s_c3_end - s_c3_start)
        curvatures[mask_c3] = 0.016 * np.sin(2.0 * np.pi * u3) * (np.sin(np.pi * u3) ** 2)

    # Integrate Frenet-Serret heading: dpsi/ds = kappa(s)
    ds = np.diff(distances)
    headings = np.zeros(n_points, dtype=float)
    if len(ds) > 0:
        headings[1:] = np.cumsum(0.5 * (curvatures[:-1] + curvatures[1:]) * ds)

    # Standard 3-sector division for circuit telemetry
    sectors = [
        1 if d < (length_m / 3.0) else (2 if d < (2.0 * length_m / 3.0) else 3)
        for d in distances
    ]

    return parse_track_from_curvature(
        distances=distances.tolist(),
        curvatures=curvatures.tolist(),
        sectors=sectors,
        headings=headings.tolist(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Scenarios
# ─────────────────────────────────────────────────────────────────────────────

def bench_single_lap(
    vehicle: Optional[LapSimVehicle] = None,
    track: Optional[List[TrackSegment]] = None,
) -> SingleLapBenchmarkResult:
    """Benchmark raw execution latency of a single QSS lap time solution.

    Ensures the vehicle has a pre-computed GGV envelope so that the benchmark
    isolates the numerical integration speed of apex search and forward-backward
    passes.

    Parameters
    ----------
    vehicle : LapSimVehicle, optional
        Vehicle model instance. If None, uses make_default_vehicle().
    track : list[TrackSegment], optional
        Discretized circuit model. If None, uses make_test_track().

    Returns
    -------
    SingleLapBenchmarkResult
        Measured wall-clock execution time and convergence status.
    """
    v = vehicle if vehicle is not None else make_default_vehicle()
    t = track if track is not None else make_test_track()

    # Pre-build GGV envelope if not yet populated
    if v._ggv_ay_max is None:
        v.build_ggv(n_speeds=20, n_ay=10)

    t0 = time.perf_counter()
    result = solve_lap(v, t, build_ggv=False)
    elapsed = time.perf_counter() - t0

    is_converged = (
        bool(result.solver_converged)
        and not math.isnan(result.total_time)
        and result.total_time > 0.0
    )

    return SingleLapBenchmarkResult(
        elapsed_time_s=elapsed,
        lap_time_s=float(result.total_time),
        converged=is_converged,
    )


def bench_ggv_build(
    vehicle: Optional[LapSimVehicle] = None,
    n_speeds: int = 20,
    n_ay: int = 10,
) -> GGVBuildBenchmarkResult:
    """Benchmark multi-axis GGV acceleration envelope generation.

    Evaluates combined-slip Pacejka MF 5.2 equilibrium across speed and lateral
    acceleration fraction grids, fitting 2D regular interpolators for subsequent
    high-speed lap solving.

    Parameters
    ----------
    vehicle : LapSimVehicle, optional
        Vehicle model instance. If None, uses make_default_vehicle().
    n_speeds : int, default=20
        Number of speed evaluation slices from 5 m/s to terminal velocity [-].
    n_ay : int, default=10
        Number of lateral acceleration fraction slices [0 to 1] [-].

    Returns
    -------
    GGVBuildBenchmarkResult
        Measured build time, grid dimensions, and terminal velocity.
    """
    v = copy.copy(vehicle) if vehicle is not None else make_default_vehicle()
    # Reset any cached GGV data to ensure a cold computation benchmark
    v._ggv_speeds = None
    v._ggv_ay_max = None
    v._ggv_ax_accel = None
    v._ggv_ax_brake = None
    v._ggv_ay_frac = None

    t0 = time.perf_counter()
    v.build_ggv(n_speeds=n_speeds, n_ay=n_ay)
    elapsed = time.perf_counter() - t0

    v_term = float(v.terminal_velocity())

    return GGVBuildBenchmarkResult(
        elapsed_time_s=elapsed,
        n_speeds=n_speeds,
        n_ay=n_ay,
        v_term_mps=v_term,
    )


def bench_10_laps(
    vehicle: Optional[LapSimVehicle] = None,
    track: Optional[List[TrackSegment]] = None,
) -> RepeatedLapsBenchmarkResult:
    """Benchmark throughput and cache consistency across 10 consecutive lap solutions.

    Parameters
    ----------
    vehicle : LapSimVehicle, optional
        Vehicle model instance. If None, uses make_default_vehicle().
    track : list[TrackSegment], optional
        Discretized circuit model. If None, uses make_test_track().

    Returns
    -------
    RepeatedLapsBenchmarkResult
        Total elapsed execution time, average lap solve latency, and convergence check.
    """
    v = vehicle if vehicle is not None else make_default_vehicle()
    t = track if track is not None else make_test_track()

    if v._ggv_ay_max is None:
        v.build_ggv(n_speeds=20, n_ay=10)

    num_laps = 10
    all_converged = True

    t0 = time.perf_counter()
    for _ in range(num_laps):
        res = solve_lap(v, t, build_ggv=False)
        if math.isnan(res.total_time) or res.total_time <= 0.0 or not res.solver_converged:
            all_converged = False
    total_time = time.perf_counter() - t0
    avg_time = total_time / float(num_laps)

    return RepeatedLapsBenchmarkResult(
        total_time_s=total_time,
        avg_time_s=avg_time,
        num_laps=num_laps,
        all_converged=all_converged,
    )


def bench_100_candidates(
    base_vehicle: Optional[LapSimVehicle] = None,
    track: Optional[List[TrackSegment]] = None,
) -> CandidateSweepBenchmarkResult:
    """Benchmark batch evaluation of 100 candidate setups with varied spring rates.

    Simulates an automated engineering design-space exploration sweeping front
    and rear wheel rates across 10 x 10 = 100 setup variants, reusing the base
    GGV envelope to achieve production optimization throughput.

    Parameters
    ----------
    base_vehicle : LapSimVehicle, optional
        Base vehicle model instance. If None, uses make_default_vehicle().
    track : list[TrackSegment], optional
        Discretized circuit model. If None, uses make_test_track().

    Returns
    -------
    CandidateSweepBenchmarkResult
        Batch total time, average evaluation time, candidate count, and failure count.
    """
    v_base = base_vehicle if base_vehicle is not None else make_default_vehicle()
    t = track if track is not None else make_test_track()

    if v_base._ggv_ay_max is None:
        v_base.build_ggv(n_speeds=20, n_ay=10)

    # 10 front spring rates x 10 rear spring rates = 100 distinct candidate setups
    k_front_grid = np.linspace(25000.0, 55000.0, 10)  # [N/m]
    k_rear_grid = np.linspace(35000.0, 65000.0, 10)   # [N/m]
    candidate_rates = [
        (float(kf), float(kr))
        for kf in k_front_grid
        for kr in k_rear_grid
    ]

    failed_count = 0
    t0 = time.perf_counter()
    for kf, kr in candidate_rates:
        try:
            cand = copy.copy(v_base)
            cand.suspension = copy.copy(v_base.suspension)
            cand.suspension.k_spring_front = kf
            cand.suspension.k_spring_rear = kr

            res = solve_lap(cand, t, build_ggv=False)
            if math.isnan(res.total_time) or res.total_time <= 0.0 or not res.solver_converged:
                failed_count += 1
        except Exception:
            failed_count += 1

    total_time = time.perf_counter() - t0
    avg_time = total_time / float(len(candidate_rates))

    return CandidateSweepBenchmarkResult(
        total_time_s=total_time,
        avg_time_s=avg_time,
        num_candidates=len(candidate_rates),
        failed_count=failed_count,
    )


def bench_memory(
    base_vehicle: Optional[LapSimVehicle] = None,
    track: Optional[List[TrackSegment]] = None,
    num_candidates: int = 100,
) -> MemoryBenchmarkResult:
    """Measure peak heap memory consumption during batch candidate evaluation.

    Uses standard library tracemalloc to trace all Python object allocations
    during a 100-candidate sweep where full LapSimResult telemetry payloads are
    retained in memory.

    Parameters
    ----------
    base_vehicle : LapSimVehicle, optional
        Base vehicle model instance. If None, uses make_default_vehicle().
    track : list[TrackSegment], optional
        Discretized circuit model. If None, uses make_test_track().
    num_candidates : int, default=100
        Number of candidate setups to evaluate during memory profiling [-].

    Returns
    -------
    MemoryBenchmarkResult
        Peak memory allocation [MB] and post-execution retained memory [MB].
    """
    v_base = base_vehicle if base_vehicle is not None else make_default_vehicle()
    t = track if track is not None else make_test_track()

    if v_base._ggv_ay_max is None:
        v_base.build_ggv(n_speeds=20, n_ay=10)

    k_front_grid = np.linspace(25000.0, 55000.0, 10)
    k_rear_grid = np.linspace(35000.0, 65000.0, 10)
    candidate_rates = [
        (float(kf), float(kr))
        for kf in k_front_grid
        for kr in k_rear_grid
    ][:num_candidates]

    tracemalloc.start()
    tracemalloc.reset_peak()
    results: List[LapSimResult] = []

    try:
        for kf, kr in candidate_rates:
            cand = copy.copy(v_base)
            cand.suspension = copy.copy(v_base.suspension)
            cand.suspension.k_spring_front = kf
            cand.suspension.k_spring_rear = kr
            res = solve_lap(cand, t, build_ggv=False)
            results.append(res)
        current_b, peak_b = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    peak_mb = max(peak_b / (1024.0 * 1024.0), 0.0)
    current_mb = max(current_b / (1024.0 * 1024.0), 0.0)

    return MemoryBenchmarkResult(
        peak_memory_mb=peak_mb,
        current_memory_mb=current_mb,
        num_candidates=len(candidate_rates),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Suite Execution & Table Formatting
# ─────────────────────────────────────────────────────────────────────────────

def run_all_benchmarks(
    n_track_points: int = 500,
    track_length_m: float = 5000.0,
) -> LapSimBenchmarkSuiteResult:
    """Execute all lap simulator benchmarks and aggregate structured results.

    Parameters
    ----------
    n_track_points : int, default=500
        Track discretization resolution [-].
    track_length_m : float, default=5000.0
        Track cumulative length [m].

    Returns
    -------
    LapSimBenchmarkSuiteResult
        Complete aggregated results across all five benchmark scenarios.
    """
    track = make_test_track(n_points=n_track_points, length_m=track_length_m)
    vehicle = make_default_vehicle()

    # 1. Single lap benchmark (builds GGV once)
    single_result = bench_single_lap(vehicle, track)

    # 2. GGV build benchmark
    ggv_result = bench_ggv_build(vehicle, n_speeds=20, n_ay=10)

    # 3. 10 consecutive laps benchmark
    laps_result = bench_10_laps(vehicle, track)

    # 4. 100 candidate setup sweep benchmark
    sweep_result = bench_100_candidates(vehicle, track)

    # 5. Peak memory profiling benchmark
    memory_result = bench_memory(vehicle, track, num_candidates=100)

    return LapSimBenchmarkSuiteResult(
        single_lap=single_result,
        ggv_build=ggv_result,
        repeated_laps=laps_result,
        candidate_sweep=sweep_result,
        memory_usage=memory_result,
    )


def format_benchmark_table(suite: LapSimBenchmarkSuiteResult) -> str:
    """Format benchmark suite results into the standard unicode presentation table.

    Produces an aligned boxed ASCII/Unicode table matching the SuspensionLab PRO
    benchmark specification:

    ╔════════════════════════════════════════════════╗
    ║     SuspensionLab PRO — Lap Sim Benchmark      ║
    ╠════════════════════════════════════════════════╣
    ║ Scenario              │ Time    │ Notes        ║
    ╠───────────────────────┼─────────┼──────────────╣
    ║ Single Lap            │   0.12s │              ║
    ║ GGV Build             │   0.85s │              ║
    ║ 10 Laps (repeated)    │   1.15s │ avg=0.115s   ║
    ║ 100 Candidates        │  12.30s │ failed=0     ║
    ║ Peak Memory           │ 45.2 MB │              ║
    ╚════════════════════════════════════════════════╝

    Parameters
    ----------
    suite : LapSimBenchmarkSuiteResult
        Aggregated benchmark measurements.

    Returns
    -------
    str
        Formatted table string ready for stdout or log output.
    """
    c1_width = 22  # "Scenario" column
    c2_width = 8   # "Time" column
    c3_width = 13  # "Notes" column
    total_inner = c1_width + 1 + 1 + c2_width + 1 + 1 + c3_width + 1  # 48 chars

    title = "SuspensionLab PRO — Lap Sim Benchmark"

    single_time = f"{suite.single_lap.elapsed_time_s:>6.2f}s"
    ggv_time = f"{suite.ggv_build.elapsed_time_s:>6.2f}s"
    laps_time = f"{suite.repeated_laps.total_time_s:>6.2f}s"
    laps_note = f"avg={suite.repeated_laps.avg_time_s:.3f}s"
    sweep_time = f"{suite.candidate_sweep.total_time_s:>6.2f}s"
    sweep_note = f"failed={suite.candidate_sweep.failed_count}"
    mem_time = f"{suite.memory_usage.peak_memory_mb:>4.1f} MB"

    lines = [
        f"╔{'═' * total_inner}╗",
        f"║{title:^{total_inner}}║",
        f"╠{'═' * total_inner}╣",
        f"║ {'Scenario':<{c1_width}}│ {'Time':<{c2_width}}│ {'Notes':<{c3_width}}║",
        f"╠{'─' * (c1_width + 1)}┼{'─' * (c2_width + 1)}┼{'─' * (c3_width + 1)}╣",
        f"║ {'Single Lap':<{c1_width}}│ {single_time:<{c2_width}}│ {'':<{c3_width}}║",
        f"║ {'GGV Build':<{c1_width}}│ {ggv_time:<{c2_width}}│ {'':<{c3_width}}║",
        f"║ {'10 Laps (repeated)':<{c1_width}}│ {laps_time:<{c2_width}}│ {laps_note:<{c3_width}}║",
        f"║ {'100 Candidates':<{c1_width}}│ {sweep_time:<{c2_width}}│ {sweep_note:<{c3_width}}║",
        f"║ {'Peak Memory':<{c1_width}}│ {mem_time:<{c2_width}}│ {'':<{c3_width}}║",
        f"╚{'═' * total_inner}╝",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Ensure Windows console uses UTF-8 encoding for unicode box-drawing characters
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    benchmark_suite = run_all_benchmarks(n_track_points=500, track_length_m=5000.0)
    table_output = format_benchmark_table(benchmark_suite)
    sys.stdout.write(table_output + "\n")
