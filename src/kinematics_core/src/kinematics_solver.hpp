/**
 * kinematics_solver.hpp
 * =====================
 * SuspensionLab — Double-Wishbone Kinematic Solver
 *
 * Newton–Raphson constraint solver for a double-wishbone corner.
 *
 * State vector  x = [x_WC, y_WC, φ_x, φ_y, φ_z]  (5 unknowns per step)
 * Prescribed    z_WC = z_WC0 + dz
 *
 * Five kinematic constraints (rigid-link distance equations):
 *   F₀ = |UWO_world − UWI_fwd|² − L²_UWO_fwd  = 0
 *   F₁ = |UWO_world − UWI_aft|² − L²_UWO_aft  = 0
 *   F₂ = |LWO_world − LWI_fwd|² − L²_LWO_fwd  = 0
 *   F₃ = |LWO_world − LWI_aft|² − L²_LWO_aft  = 0
 *   F₄ = |TRO_world − TRI     |² − L²_TR       = 0
 *
 * where for any upright-fixed point P:
 *   P_world = r_WC + R(φ) * d_P
 *
 * R = Rz(φ_z) · Ry(φ_y) · Rx(φ_x)  (intrinsic Z–Y–X Euler rotations)
 *
 * Jacobian: 5×5, computed by central finite differences (h = 1e-5).
 * Linear system solved with ColPivHouseholderQR at each Newton step.
 * Warm-start from previous wheel-travel step for fast convergence.
 */

#pragma once

#include "hardpoints.hpp"

#include <Eigen/Dense>
#include <string>
#include <vector>

namespace suspensionlab {

class KinematicsSolver {
public:
    /**
     * Construct the solver for a given corner.
     * @param hp  Fully constructed HardpointSet (use HardpointSet::from_raw).
     */
    explicit KinematicsSolver(const HardpointSet& hp);

    /**
     * Sweep wheel travel from z_min_mm to z_max_mm, solving kinematics at
     * each of n_steps equally-spaced points.
     *
     * @param z_min_mm  Minimum wheel travel (droop, negative) [mm]
     * @param z_max_mm  Maximum wheel travel (bump, positive)  [mm]
     * @param n_steps   Number of evaluation points (≥ 2)
     * @return KinematicsCurves  One KinematicPoint per step.
     */
    KinematicsCurves solve(double z_min_mm, double z_max_mm, int n_steps) const;

    /**
     * Solve for a single wheel-travel value.
     * @param dz_mm  Wheel travel from neutral [mm] (positive = bump)
     * @return KinematicPoint  Output; check .converged.
     */
    KinematicPoint solve_single(double dz_mm) const;

    /**
     * V2 Phase 3: rack travel. Returns a solver whose inboard tie-rod pivot (TRI) is
     * translated by rack_mm along the lateral axis (Y). The tie-rod LENGTH (L_TRO_sq)
     * is unchanged, so the shifted pivot forces the upright to steer. rack_mm == 0
     * returns an identical solver. Mirrors Python `_solve_py(rack_travel_mm=...)`.
     */
    KinematicsSolver with_rack_travel(double rack_mm) const;

private:
    HardpointSet hp_;

    // ── Internal solver primitives ────────────────────────────────────────

    /**
     * Evaluate the 5-element residual vector F(x) at current state.
     * x = [x_WC, y_WC, phi_x, phi_y, phi_z], z_WC is prescribed.
     */
    Eigen::Matrix<double,5,1> residual(
        const Eigen::Matrix<double,5,1>& x, double z_WC) const;

    /**
     * Build rotation matrix R = Rz(phi_z)·Ry(phi_y)·Rx(phi_x).
     */
    static Eigen::Matrix3d rotation(double phi_x, double phi_y, double phi_z);

    /**
     * Compute 5×5 numerical Jacobian via central finite differences.
     * Steps: h_pos = 1e-4 mm for x_WC, y_WC;
     *        h_ang = 1e-6 rad for phi_x, phi_y, phi_z.
     */
    Eigen::Matrix<double,5,5> jacobian(
        const Eigen::Matrix<double,5,1>& x, double z_WC) const;

    /**
     * Run Newton–Raphson from warm-start x0.
     * @param[in,out] x   State vector — updated in place.
     * @param z_WC        Prescribed wheel-centre Z.
     * @return true if ||F||₂ < 1e-8 mm² was achieved.
     */
    bool newton_solve(Eigen::Matrix<double,5,1>& x, double z_WC) const;

    // ── Output extraction ─────────────────────────────────────────────────

    KinematicPoint extract(
        const Eigen::Matrix<double,5,1>& x,
        double dz_mm,
        double pushrod_len_prev,   // for numerical MR derivative
        double dz_step,
        bool converged) const;

    /**
     * Compute geometric roll-centre height in the front-view (Y–Z) plane.
     * Returns NaN if lines are parallel (degenerate geometry).
     */
    double roll_center_height(
        const Eigen::Matrix3d& R,
        const Eigen::Vector3d& r_WC) const;

    /**
     * Compute scrub radius: Y offset of contact patch from steering-axis
     * intersection with the ground plane (Z = 0).
     */
    double scrub_radius(
        const Eigen::Matrix3d& R,
        const Eigen::Vector3d& r_WC) const;

    /**
     * Pushrod world length at current state (for MR computation).
     */
    double pushrod_length(
        const Eigen::Matrix3d& R,
        const Eigen::Vector3d& r_WC) const;
};

}  // namespace suspensionlab
