/**
 * kinematics_solver.cpp
 * =====================
 * SuspensionLab — Double-Wishbone Kinematic Solver (full implementation)
 *
 * See kinematics_solver.hpp for the mathematical formulation.
 */

// Ensure M_PI is defined (MSVC + MinGW-MSVCRT both need this)
#ifndef _USE_MATH_DEFINES
#  define _USE_MATH_DEFINES
#endif

#include "kinematics_solver.hpp"

#include <Eigen/Dense>
#include <cmath>
#include <stdexcept>

namespace suspensionlab {

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

static constexpr double PI         = M_PI;
static constexpr double RAD_TO_DEG = 180.0 / PI;
static constexpr double DEG_TO_RAD = PI / 180.0;

/// Newton–Raphson convergence tolerance [mm²] (sub-micron equivalent)
static constexpr double NR_TOL    = 1e-8;
/// Maximum Newton iterations per step
static constexpr int    NR_MAXITER = 60;
/// FD step for position variables [mm]
static constexpr double H_POS     = 1e-4;
/// FD step for angle variables [rad]
static constexpr double H_ANG     = 1e-6;


// ─────────────────────────────────────────────────────────────────────────────
// Construction
// ─────────────────────────────────────────────────────────────────────────────

KinematicsSolver::KinematicsSolver(const HardpointSet& hp)
    : hp_(hp)
{}


// ─────────────────────────────────────────────────────────────────────────────
// Rotation matrix  R = Rz(φz) · Ry(φy) · Rx(φx)
// ─────────────────────────────────────────────────────────────────────────────

Eigen::Matrix3d KinematicsSolver::rotation(double phi_x, double phi_y, double phi_z)
{
    const double cx = std::cos(phi_x), sx = std::sin(phi_x);
    const double cy = std::cos(phi_y), sy = std::sin(phi_y);
    const double cz = std::cos(phi_z), sz = std::sin(phi_z);

    // Rz · Ry · Rx  (intrinsic Z–Y–X, equivalent to extrinsic X–Y–Z)
    Eigen::Matrix3d R;
    R(0,0) =  cy * cz;
    R(0,1) =  cz * sx * sy - cx * sz;
    R(0,2) =  cx * cz * sy + sx * sz;

    R(1,0) =  cy * sz;
    R(1,1) =  cx * cz + sx * sy * sz;
    R(1,2) = -cz * sx + cx * sy * sz;

    R(2,0) = -sy;
    R(2,1) =  cy * sx;
    R(2,2) =  cx * cy;

    return R;
}


// ─────────────────────────────────────────────────────────────────────────────
// Residual  F(x) : ℝ⁵ → ℝ⁵
// x = [x_WC, y_WC, phi_x, phi_y, phi_z]
// ─────────────────────────────────────────────────────────────────────────────

Eigen::Matrix<double,5,1>
KinematicsSolver::residual(const Eigen::Matrix<double,5,1>& x, double z_WC) const
{
    const double x_WC  = x(0);
    const double y_WC  = x(1);
    const double phi_x = x(2);
    const double phi_y = x(3);
    const double phi_z = x(4);

    const Eigen::Matrix3d R = rotation(phi_x, phi_y, phi_z);
    const Eigen::Vector3d r_WC{x_WC, y_WC, z_WC};

    // World positions of upright-fixed outboard points
    const Eigen::Vector3d uwo = r_WC + R * hp_.d_UWO;
    const Eigen::Vector3d lwo = r_WC + R * hp_.d_LWO;
    const Eigen::Vector3d tro = r_WC + R * hp_.d_TRO;

    Eigen::Matrix<double,5,1> F;
    F(0) = (uwo - hp_.UWI_fwd).squaredNorm() - hp_.L_UWO_fwd_sq;
    F(1) = (uwo - hp_.UWI_aft).squaredNorm() - hp_.L_UWO_aft_sq;
    F(2) = (lwo - hp_.LWI_fwd).squaredNorm() - hp_.L_LWO_fwd_sq;
    F(3) = (lwo - hp_.LWI_aft).squaredNorm() - hp_.L_LWO_aft_sq;
    F(4) = (tro - hp_.TRI    ).squaredNorm() - hp_.L_TRO_sq;

    return F;
}


// ─────────────────────────────────────────────────────────────────────────────
// Jacobian  J = ∂F/∂x  via central finite differences
// ─────────────────────────────────────────────────────────────────────────────

Eigen::Matrix<double,5,5>
KinematicsSolver::jacobian(const Eigen::Matrix<double,5,1>& x, double z_WC) const
{
    // Step sizes: index 0,1 = positions [mm]; 2,3,4 = angles [rad]
    const double steps[5] = {H_POS, H_POS, H_ANG, H_ANG, H_ANG};

    Eigen::Matrix<double,5,5> J;
    Eigen::Matrix<double,5,1> xp = x, xm = x;

    for (int j = 0; j < 5; ++j) {
        const double h = steps[j];
        xp(j) = x(j) + h;
        xm(j) = x(j) - h;
        J.col(j) = (residual(xp, z_WC) - residual(xm, z_WC)) / (2.0 * h);
        xp(j) = x(j);
        xm(j) = x(j);
    }
    return J;
}


// ─────────────────────────────────────────────────────────────────────────────
// Newton–Raphson single step solver
// ─────────────────────────────────────────────────────────────────────────────

bool KinematicsSolver::newton_solve(Eigen::Matrix<double,5,1>& x, double z_WC) const
{
    for (int iter = 0; iter < NR_MAXITER; ++iter) {
        const auto F = residual(x, z_WC);
        if (F.norm() < NR_TOL) return true;

        const auto J  = jacobian(x, z_WC);
        const auto dx = J.colPivHouseholderQr().solve(-F);
        x += dx;

        if (dx.norm() < 1e-12) return true;  // step vanishingly small
    }
    // Final check — may have converged on last iteration
    return residual(x, z_WC).norm() < NR_TOL;
}


// ─────────────────────────────────────────────────────────────────────────────
// Geometric helpers
// ─────────────────────────────────────────────────────────────────────────────

double KinematicsSolver::pushrod_length(
    const Eigen::Matrix3d& R, const Eigen::Vector3d& r_WC) const
{
    const Eigen::Vector3d pro_world = r_WC + R * hp_.d_PRO;
    return (pro_world - hp_.PRI).norm();
}

/**
 * Roll-centre height via front-view (Y–Z plane) geometric construction.
 *
 * Procedure:
 *  1. Project midpoints of inboard pivots and world outboard points to Y–Z.
 *  2. Find the instant centre (IC) = intersection of upper and lower
 *     wishbone virtual swing arms.
 *  3. Find where the line IC → contact-patch crosses the vehicle centreline (Y=0).
 *  4. Z of that crossing = roll-centre height.
 */
double KinematicsSolver::roll_center_height(
    const Eigen::Matrix3d& R, const Eigen::Vector3d& r_WC) const
{
    // World positions of outboard points
    const Eigen::Vector3d uwo = r_WC + R * hp_.d_UWO;
    const Eigen::Vector3d lwo = r_WC + R * hp_.d_LWO;
    const Eigen::Vector3d cp  = r_WC + R * hp_.d_CP;

    // Y–Z projections (index 1 = Y, index 2 = Z)
    // Lower wishbone: from LWI midpoint → LWO
    const Eigen::Vector3d lwi_mid = 0.5 * (hp_.LWI_fwd + hp_.LWI_aft);
    const double p1y = lwi_mid(1), p1z = lwi_mid(2);
    const double d1y = lwo(1) - p1y,  d1z = lwo(2) - p1z;

    // Upper wishbone: from UWI midpoint → UWO
    const Eigen::Vector3d uwi_mid = 0.5 * (hp_.UWI_fwd + hp_.UWI_aft);
    const double p2y = uwi_mid(1), p2z = uwi_mid(2);
    const double d2y = uwo(1) - p2y,  d2z = uwo(2) - p2z;

    // Intersect line 1 (p1 + t1·d1) with line 2 (p2 + t2·d2) in Y–Z:
    // [d1y, -d2y] [t1]   [p2y - p1y]
    // [d1z, -d2z] [t2] = [p2z - p1z]
    const double det = d1y * (-d2z) - d1z * (-d2y);  // = d2y·d1z - d1y·d2z

    if (std::abs(det) < 1e-6) {
        // Wishbone arms parallel in front view → force-based RC at ground
        return 0.0;
    }

    const double rhs_y = p2y - p1y;
    const double rhs_z = p2z - p1z;
    const double t1 = (rhs_y * (-d2z) - rhs_z * (-d2y)) / det;

    const double ic_y = p1y + t1 * d1y;
    const double ic_z = p1z + t1 * d1z;

    // Line 3: from contact-patch (cp_y, cp_z=0) toward IC (ic_y, ic_z)
    // At Y = 0 (vehicle centreline):
    //   cp_y + t3 * (ic_y - cp_y) = 0  →  t3 = -cp_y / (ic_y - cp_y)
    const double cp_y = cp(1);
    const double denom = ic_y - cp_y;

    if (std::abs(denom) < 1e-6) {
        // IC is on the centreline — RC = IC height
        return ic_z;
    }

    const double t3   = -cp_y / denom;
    const double rc_z = 0.0 + t3 * ic_z;   // cp_z = 0 (ground)

    return rc_z;
}

/**
 * Scrub radius = Y distance from contact-patch to the point where the
 * steering (kingpin) axis pierces the ground plane (Z = 0).
 *
 * Positive = contact-patch is outboard of the steering-axis ground point.
 */
double KinematicsSolver::scrub_radius(
    const Eigen::Matrix3d& R, const Eigen::Vector3d& r_WC) const
{
    // World positions of ball joints and contact patch
    const Eigen::Vector3d uwo = r_WC + R * hp_.d_UWO;
    const Eigen::Vector3d lwo = r_WC + R * hp_.d_LWO;
    const Eigen::Vector3d cp  = r_WC + R * hp_.d_CP;

    // Kingpin axis direction (from lower to upper BJ)
    const Eigen::Vector3d kp_dir = (uwo - lwo).normalized();

    if (std::abs(kp_dir(2)) < 1e-9) {
        // Kingpin axis is horizontal — undefined scrub; return 0
        return 0.0;
    }

    // Parametric line from LWO along kp_dir to Z = 0:
    //   lwo(2) + t * kp_dir(2) = 0  →  t = -lwo(2) / kp_dir(2)
    const double t     = -lwo(2) / kp_dir(2);
    const double sa_y  = lwo(1) + t * kp_dir(1);   // steering-axis Y at ground

    return cp(1) - sa_y;   // positive = cp outboard of SA
}


// ─────────────────────────────────────────────────────────────────────────────
// Output extraction from solution state
// ─────────────────────────────────────────────────────────────────────────────

KinematicPoint KinematicsSolver::extract(
    const Eigen::Matrix<double,5,1>& x,
    double dz_mm,
    double pushrod_len_prev,
    double dz_step,
    bool converged) const
{
    const double x_WC  = x(0);
    const double y_WC  = x(1);
    const double phi_x = x(2);
    const double phi_y = x(3);
    const double phi_z = x(4);
    const double z_WC  = hp_.WC0(2) + dz_mm;

    const Eigen::Matrix3d R = rotation(phi_x, phi_y, phi_z);
    const Eigen::Vector3d r_WC{x_WC, y_WC, z_WC};

    // ── Camber ───────────────────────────────────────────────────────────
    // Wheel spin axis in world frame = second column of R (local Y → world)
    // Camber = angle of spin axis from world-Y axis measured in Y–Z plane.
    //   camber_deg = atan2(spin_z, spin_y) * RAD_TO_DEG
    // Positive = top of wheel tilts outboard (+Y convention).
    const double spin_y = R(1,1);
    const double spin_z = R(2,1);
    const double camber_deg = std::atan2(spin_z, spin_y) * RAD_TO_DEG;

    // ── Toe ──────────────────────────────────────────────────────────────
    // Angle of spin axis projected to X–Y plane from world-Y.
    // toe = atan2(spin_x, spin_y) * RAD_TO_DEG
    // Positive = nose of wheel points in +X direction (toe-out for Y-outboard convention)
    const double spin_x = R(0,1);
    const double toe_deg = std::atan2(spin_x, spin_y) * RAD_TO_DEG;

    // ── Kingpin axis ──────────────────────────────────────────────────────
    const Eigen::Vector3d uwo = r_WC + R * hp_.d_UWO;
    const Eigen::Vector3d lwo = r_WC + R * hp_.d_LWO;
    const Eigen::Vector3d kp  = (uwo - lwo).normalized();

    // KPI: angle of kingpin from vertical (Z) in front view (Y–Z plane)
    //   kpi_deg = atan2(kp_y, kp_z) in the Y–Z plane
    //   (front-view inclination from Z-axis)
    const double kpi_deg = std::atan2(kp(1), kp(2)) * RAD_TO_DEG;

    // Caster: angle of kingpin from vertical in side view (X–Z plane)
    //   positive caster = kingpin tilts rearward at top (+X negative at top)
    //   caster_deg = atan2(-kp_x, kp_z)
    const double caster_deg = std::atan2(-kp(0), kp(2)) * RAD_TO_DEG;

    // ── Track and wheelbase changes ───────────────────────────────────────
    const double track_change_mm     = y_WC - hp_.WC0(1);   // outboard = positive
    const double wheelbase_change_mm = x_WC - hp_.WC0(0);   // forward  = positive

    // ── Roll-centre height ────────────────────────────────────────────────
    const double rc_height_mm = roll_center_height(R, r_WC);

    // ── Motion ratio  (numerical derivative: Δpushrod_len / Δwheel_travel)
    // dz_step is the wheel-travel increment between steps.
    // On the first step or if dz_step is zero, we return NaN / 0.
    const double pr_len = pushrod_length(R, r_WC);
    double mr = 0.0;
    if (std::abs(dz_step) > 1e-9 && pushrod_len_prev >= 0.0) {
        mr = std::abs((pr_len - pushrod_len_prev) / dz_step);
    }

    // ── Scrub radius ──────────────────────────────────────────────────────
    const double scrub_mm = scrub_radius(R, r_WC);

    KinematicPoint pt;
    pt.wheel_travel_mm       = dz_mm;
    pt.camber_deg            = camber_deg;
    pt.toe_deg               = toe_deg;
    pt.caster_deg            = caster_deg;
    pt.kpi_deg               = kpi_deg;
    pt.track_change_mm       = track_change_mm;
    pt.wheelbase_change_mm   = wheelbase_change_mm;
    pt.roll_center_height_mm = rc_height_mm;
    pt.motion_ratio          = mr;
    pt.scrub_radius_mm       = scrub_mm;
    pt.converged             = converged;
    return pt;
}


// ─────────────────────────────────────────────────────────────────────────────
// Public interface: solve single step
// ─────────────────────────────────────────────────────────────────────────────

KinematicPoint KinematicsSolver::solve_single(double dz_mm) const
{
    Eigen::Matrix<double,5,1> x;
    x << hp_.WC0(0), hp_.WC0(1), 0.0, 0.0, 0.0;   // neutral warm-start

    const double z_WC = hp_.WC0(2) + dz_mm;
    const bool ok = newton_solve(x, z_WC);

    // For single-step calls, MR is returned as 0 (needs two steps to compute)
    return extract(x, dz_mm, -1.0, 0.0, ok);
}


// ─────────────────────────────────────────────────────────────────────────────
// Public interface: full sweep
// ─────────────────────────────────────────────────────────────────────────────

KinematicsCurves KinematicsSolver::solve(
    double z_min_mm, double z_max_mm, int n_steps) const
{
    if (n_steps < 2)
        throw std::invalid_argument("n_steps must be >= 2");

    KinematicsCurves curves;
    curves.points.reserve(static_cast<size_t>(n_steps));

    const double dz_total = z_max_mm - z_min_mm;
    const double dz_step  = dz_total / static_cast<double>(n_steps - 1);

    // Warm-start: begin at neutral (dz=0) then march toward z_min, then sweep
    // For a single forward pass from z_min to z_max, warm-start each step
    // from the previous solution.

    // Initialise x at the neutral position
    Eigen::Matrix<double,5,1> x;
    x << hp_.WC0(0), hp_.WC0(1), 0.0, 0.0, 0.0;

    // Warm-start from neutral by solving intermediate steps to z_min
    // (handles large droop where starting at neutral + jump can diverge)
    {
        // Warm-up: march from neutral to z_min in warm_steps increments
        const int warm_steps = std::max(5, n_steps / 4);
        double z_cur = hp_.WC0(2);
        const double z_target = hp_.WC0(2) + z_min_mm;
        const double wstep = (z_target - z_cur) / warm_steps;
        for (int i = 0; i < warm_steps; ++i) {
            z_cur += wstep;
            newton_solve(x, z_cur);   // discard convergence flag during warm-up
        }
    }

    double prev_pr_len = pushrod_length(rotation(x(2), x(3), x(4)),
                                        {x(0), x(1), hp_.WC0(2) + z_min_mm});

    for (int i = 0; i < n_steps; ++i) {
        const double dz    = z_min_mm + i * dz_step;
        const double z_WC  = hp_.WC0(2) + dz;

        const bool ok = newton_solve(x, z_WC);

        KinematicPoint pt = extract(x, dz, prev_pr_len, dz_step, ok);

        // Update previous pushrod length for next MR derivative
        const Eigen::Matrix3d R_cur = rotation(x(2), x(3), x(4));
        const Eigen::Vector3d r_cur{x(0), x(1), z_WC};
        prev_pr_len = pushrod_length(R_cur, r_cur);

        curves.points.push_back(std::move(pt));
    }

    return curves;
}

}  // namespace suspensionlab
