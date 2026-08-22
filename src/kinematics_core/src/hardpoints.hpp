/**
 * hardpoints.hpp
 * ==============
 * SuspensionLab — Double-Wishbone Kinematic Solver
 * Hardpoint data structures.
 *
 * Coordinate System (right-front corner, SAE-like)
 * -------------------------------------------------
 *   X : forward  (positive = toward front of car)
 *   Y : outboard (positive = away from vehicle centreline)
 *   Z : up       (positive = upward)
 *
 * All dimensions in millimetres [mm].
 * Angles in degrees [deg] in all Python-facing outputs.
 * Internally the solver uses radians and mm.
 *
 * Assumptions
 * -----------
 *   - Double wishbone (SLA) with parallel inboard wishbone pivots
 *   - Pushrod inboard connects to a chassis-fixed rocker pivot point;
 *     the spring/damper acts on the same point (1:1 rocker assumed for MR).
 *     For non-trivial rockers, override motion_ratio from the pushrod length derivative.
 *   - Tierod connects chassis-fixed steering rack point to upright steering arm.
 */

#pragma once

#include <Eigen/Dense>

namespace suspensionlab {

/// All chassis-fixed (world-frame) pivot points and upright-frame offsets.
/// Constructed via HardpointSet::from_raw().
struct HardpointSet {
    // ── Chassis-fixed points (don't move with wheel) ─────────────────────
    Eigen::Vector3d UWI_fwd;   ///< Upper wishbone inboard pivot — forward [mm]
    Eigen::Vector3d UWI_aft;   ///< Upper wishbone inboard pivot — aft    [mm]
    Eigen::Vector3d LWI_fwd;   ///< Lower wishbone inboard pivot — forward [mm]
    Eigen::Vector3d LWI_aft;   ///< Lower wishbone inboard pivot — aft    [mm]
    Eigen::Vector3d TRI;        ///< Tierod inboard (rack end)             [mm]
    Eigen::Vector3d PRI;        ///< Pushrod inboard (rocker pivot)        [mm]

    // ── Neutral wheel-centre position (world frame) ───────────────────────
    Eigen::Vector3d WC0;        ///< Wheel centre at neutral (dz = 0)      [mm]

    // ── Upright-frame offsets (WC0 as origin, in upright body frame) ─────
    // For any upright-fixed point P:  P_world = r_WC + R * d_P
    Eigen::Vector3d d_UWO;     ///< Upper wishbone outboard (upper BJ)     [mm]
    Eigen::Vector3d d_LWO;     ///< Lower wishbone outboard (lower BJ)     [mm]
    Eigen::Vector3d d_TRO;     ///< Tierod outboard (steering arm)         [mm]
    Eigen::Vector3d d_CP;      ///< Contact patch  (d_CP = [0,0,-r_wheel]) [mm]
    Eigen::Vector3d d_PRO;     ///< Pushrod outboard attachment on upright  [mm]

    // ── Precomputed squared reference distances ───────────────────────────
    double L_UWO_fwd_sq;       ///< |UWO0 - UWI_fwd|² [mm²]
    double L_UWO_aft_sq;       ///< |UWO0 - UWI_aft|² [mm²]
    double L_LWO_fwd_sq;       ///< |LWO0 - LWI_fwd|² [mm²]
    double L_LWO_aft_sq;       ///< |LWO0 - LWI_aft|² [mm²]
    double L_TRO_sq;           ///< |TRO0 - TRI|²       [mm²]

    /**
     * Construct a HardpointSet from raw world-frame neutral coordinates.
     *
     * @param UWI_fwd  Upper wishbone inboard forward pivot [mm]
     * @param UWI_aft  Upper wishbone inboard aft pivot     [mm]
     * @param UWO      Upper wishbone outboard (upper BJ)   [mm]
     * @param LWI_fwd  Lower wishbone inboard forward pivot [mm]
     * @param LWI_aft  Lower wishbone inboard aft pivot     [mm]
     * @param LWO      Lower wishbone outboard (lower BJ)   [mm]
     * @param TRI      Tierod inboard (rack)                [mm]
     * @param TRO      Tierod outboard (steering arm)       [mm]
     * @param WC       Wheel centre (neutral)               [mm]
     * @param CP       Contact patch (neutral)              [mm]
     * @param PRI      Pushrod inboard / rocker pivot       [mm]
     * @param PRO      Pushrod outboard on upright          [mm]
     */
    static HardpointSet from_raw(
        Eigen::Vector3d UWI_fwd, Eigen::Vector3d UWI_aft, Eigen::Vector3d UWO,
        Eigen::Vector3d LWI_fwd, Eigen::Vector3d LWI_aft, Eigen::Vector3d LWO,
        Eigen::Vector3d TRI,     Eigen::Vector3d TRO,
        Eigen::Vector3d WC,      Eigen::Vector3d CP,
        Eigen::Vector3d PRI,     Eigen::Vector3d PRO
    ) {
        HardpointSet hp;
        hp.UWI_fwd = UWI_fwd;
        hp.UWI_aft = UWI_aft;
        hp.LWI_fwd = LWI_fwd;
        hp.LWI_aft = LWI_aft;
        hp.TRI     = TRI;
        hp.PRI     = PRI;
        hp.WC0     = WC;

        // Upright-frame offset vectors (from WC origin in neutral upright frame)
        hp.d_UWO = UWO - WC;
        hp.d_LWO = LWO - WC;
        hp.d_TRO = TRO - WC;
        hp.d_CP  = CP  - WC;
        hp.d_PRO = PRO - WC;

        // Squared reference distances — verified at neutral (F = 0 exactly)
        hp.L_UWO_fwd_sq = (UWO - UWI_fwd).squaredNorm();
        hp.L_UWO_aft_sq = (UWO - UWI_aft).squaredNorm();
        hp.L_LWO_fwd_sq = (LWO - LWI_fwd).squaredNorm();
        hp.L_LWO_aft_sq = (LWO - LWI_aft).squaredNorm();
        hp.L_TRO_sq     = (TRO - TRI    ).squaredNorm();

        return hp;
    }
};

/// All computed kinematic outputs for one corner at one wheel-travel step.
struct KinematicPoint {
    double wheel_travel_mm;       ///< Prescribed z_WC - z_WC0 [mm]
    double camber_deg;            ///< Camber angle; + = top outboard [deg]
    double toe_deg;               ///< Toe angle;   + = toe-out       [deg]
    double caster_deg;            ///< Caster angle from kingpin axis  [deg]
    double kpi_deg;               ///< Kingpin inclination (front view) [deg]
    double track_change_mm;       ///< Lateral WC displacement from neutral [mm]
    double wheelbase_change_mm;   ///< Longitudinal WC displacement      [mm]
    double roll_center_height_mm; ///< Geometric RC height above ground  [mm]
    double motion_ratio;          ///< |Δpushrod| / |Δwheel|  (numerical) [-]
    double scrub_radius_mm;       ///< CP Y offset from steering axis [mm]
    bool   converged;             ///< Newton–Raphson convergence flag
};

/// Complete output curves for a sweep of wheel travel.
struct KinematicsCurves {
    std::vector<KinematicPoint> points;
};

}  // namespace suspensionlab
