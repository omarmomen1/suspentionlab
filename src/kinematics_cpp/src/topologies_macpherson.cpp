#define _USE_MATH_DEFINES
#include <cmath>
#include "suspension_kinematics/topologies.hpp"
#include "suspension_kinematics/exceptions.hpp"

namespace suspensionlab {
namespace kinematics {

namespace {

// Computes 3x3 rotation matrix A from quaternion p = [e0, e1, e2, e3]^T
Eigen::Matrix3d quat_to_rot(const Eigen::VectorXd& p) {
    double e0 = p(0), e1 = p(1), e2 = p(2), e3 = p(3);
    Eigen::Matrix3d A;
    A(0,0) = 2.0 * (e0*e0 + e1*e1) - 1.0;
    A(0,1) = 2.0 * (e1*e2 - e0*e3);
    A(0,2) = 2.0 * (e1*e3 + e0*e2);
    
    A(1,0) = 2.0 * (e1*e2 + e0*e3);
    A(1,1) = 2.0 * (e0*e0 + e2*e2) - 1.0;
    A(1,2) = 2.0 * (e2*e3 - e0*e1);
    
    A(2,0) = 2.0 * (e1*e3 - e0*e2);
    A(2,1) = 2.0 * (e2*e3 + e0*e1);
    A(2,2) = 2.0 * (e0*e0 + e3*e3) - 1.0;
    return A;
}

// Derivative of A(p)*s w.r.t p. Returns a 3x4 matrix.
Eigen::Matrix<double, 3, 4> d_A_s_dp(const Eigen::VectorXd& p, const Eigen::Vector3d& s) {
    double e0 = p(0), e1 = p(1), e2 = p(2), e3 = p(3);
    double x = s(0), y = s(1), z = s(2);
    
    Eigen::Matrix<double, 3, 4> D;
    
    // col 0 (w.r.t e0)
    D(0,0) =  4.0*e0*x - 2.0*e3*y + 2.0*e2*z;
    D(1,0) =  2.0*e3*x + 4.0*e0*y - 2.0*e1*z;
    D(2,0) = -2.0*e2*x + 2.0*e1*y + 4.0*e0*z;
    
    // col 1 (w.r.t e1)
    D(0,1) =  4.0*e1*x + 2.0*e2*y + 2.0*e3*z;
    D(1,1) =  2.0*e2*x            - 2.0*e0*z;
    D(2,1) =  2.0*e3*x + 2.0*e0*y;
    
    // col 2 (w.r.t e2)
    D(0,2) =             2.0*e1*y + 2.0*e0*z;
    D(1,2) =  2.0*e1*x + 4.0*e2*y + 2.0*e3*z;
    D(2,2) = -2.0*e0*x + 2.0*e3*y;
    
    // col 3 (w.r.t e3)
    D(0,3) =           - 2.0*e0*y + 2.0*e1*z;
    D(1,3) =  2.0*e0*x            + 2.0*e2*z;
    D(2,3) =  2.0*e1*x + 2.0*e2*y + 4.0*e3*z;
    
    return D;
}

} // namespace

MacPherson::MacPherson(const std::map<std::string, Eigen::Vector3d>& hardpoints) 
    : base_hp_(hardpoints)
{
    ValidationReport rep = HardpointValidator::validate_macpherson(hardpoints);
    if (!rep.is_valid) {
        throw InvalidTopologyException("Invalid MacPherson hardpoints: " + rep.to_string());
    }

    initialize_geometry();
}

void MacPherson::initialize_geometry() {
    l_lca_f_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_front"]).squaredNorm();
    l_lca_r_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_rear"]).squaredNorm();
    l_tie_sq_   = (base_hp_["upright_tie_rod"] - base_hp_["chassis_tie_rod"]).squaredNorm();

    Eigen::Vector3d r_wc_init = base_hp_["wheel_center"];
    up_lower_ = base_hp_["upright_lower"] - r_wc_init;
    up_tie_   = base_hp_["upright_tie_rod"] - r_wc_init;
    up_wc_    = Eigen::Vector3d::Zero();
    
    up_strut_mount_ = base_hp_["upright_strut_mount"] - r_wc_init;

    Eigen::Vector3d strut_vec = base_hp_["chassis_strut_top"] - base_hp_["upright_strut_mount"];
    u_strut_init_ = strut_vec.normalized();

    heave_target_z_ = r_wc_init(2);
}

void MacPherson::set_target_inputs(double heave_mm, double roll_deg, double steer_deg, double pitch_deg) {
    Eigen::Vector3d wc_init = base_hp_.at("wheel_center");
    heave_target_z_ = wc_init(2) + heave_mm;
    roll_input_deg_ = roll_deg;
    steer_target_deg_ = steer_deg;
    pitch_input_deg_ = pitch_deg;
}

void MacPherson::set_heave_target(double z_world_mm) {
    heave_target_z_ = z_world_mm;
}

void MacPherson::set_steer_target_deg(double steer_deg) {
    steer_target_deg_ = steer_deg;
}

ValidationReport MacPherson::validate(double tire_radius) const {
    return HardpointValidator::validate_macpherson(base_hp_, tire_radius);
}

double MacPherson::get_spring_length(const Eigen::VectorXd& state) const {
    return state(7); // Strut sliding extension
}

void MacPherson::evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    double d_strut    = state(7);
    Eigen::Matrix3d A = quat_to_rot(p);

    residuals.resize(8);

    double rack_dy = steer_target_deg_ * 1.2;
    Eigen::Vector3d ch_tie = base_hp_.at("chassis_tie_rod") + Eigen::Vector3d(0.0, rack_dy, 0.0);

    Eigen::Vector3d ch_low_f     = base_hp_.at("chassis_lower_front");
    Eigen::Vector3d ch_low_r     = base_hp_.at("chassis_lower_rear");
    Eigen::Vector3d ch_strut_top = base_hp_.at("chassis_strut_top");

    // 1-2. LCA front and rear link distances
    Eigen::Vector3d p_lca = r + A * up_lower_;
    residuals(0) = (p_lca - ch_low_f).squaredNorm() - l_lca_f_sq_;
    residuals(1) = (p_lca - ch_low_r).squaredNorm() - l_lca_r_sq_;

    // 3. Tie rod link distance
    Eigen::Vector3d p_tie = r + A * up_tie_;
    residuals(2) = (p_tie - ch_tie).squaredNorm() - l_tie_sq_;

    // 4-6. Strut sliding vector constraint: r + A*up_strut_mount + d_strut*(A*u_strut_init) = ch_strut_top
    Eigen::Vector3d strut_eq = r + A * up_strut_mount_ + d_strut * (A * u_strut_init_) - ch_strut_top;
    residuals(3) = strut_eq(0);
    residuals(4) = strut_eq(1);
    residuals(5) = strut_eq(2);

    // 7. Quaternion normalization
    residuals(6) = p.squaredNorm() - 1.0;

    // 8. Heave target
    residuals(7) = r(2) - heave_target_z_;
}

void MacPherson::evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    double d_strut    = state(7);
    Eigen::Matrix3d A = quat_to_rot(p);

    jacobian = Eigen::MatrixXd::Zero(8, 8);

    double rack_dy = steer_target_deg_ * 1.2;
    Eigen::Vector3d ch_tie = base_hp_.at("chassis_tie_rod") + Eigen::Vector3d(0.0, rack_dy, 0.0);

    Eigen::Vector3d ch_low_f = base_hp_.at("chassis_lower_front");
    Eigen::Vector3d ch_low_r = base_hp_.at("chassis_lower_rear");

    Eigen::Vector3d p_lca = r + A * up_lower_;
    Eigen::Vector3d v_low_f = p_lca - ch_low_f;
    Eigen::Vector3d v_low_r = p_lca - ch_low_r;

    Eigen::Vector3d p_tie = r + A * up_tie_;
    Eigen::Vector3d v_tie = p_tie - ch_tie;

    // Dr/Dr is 2 * (v)^T
    jacobian.block<1,3>(0, 0) = 2.0 * v_low_f.transpose();
    jacobian.block<1,3>(1, 0) = 2.0 * v_low_r.transpose();
    jacobian.block<1,3>(2, 0) = 2.0 * v_tie.transpose();

    // Dr/Dp is 2 * (v)^T * d_A_s_dp
    jacobian.block<1,4>(0, 3) = 2.0 * v_low_f.transpose() * d_A_s_dp(p, up_lower_);
    jacobian.block<1,4>(1, 3) = 2.0 * v_low_r.transpose() * d_A_s_dp(p, up_lower_);
    jacobian.block<1,4>(2, 3) = 2.0 * v_tie.transpose() * d_A_s_dp(p, up_tie_);

    // Strut constraint derivatives
    // r + A*up_strut_mount + d_strut*(A*u_strut_init) - ch_strut_top = 0
    jacobian.block<3,3>(3, 0) = Eigen::Matrix3d::Identity(); // w.r.t r
    jacobian.block<3,4>(3, 3) = d_A_s_dp(p, up_strut_mount_) + d_strut * d_A_s_dp(p, u_strut_init_); // w.r.t p
    jacobian.block<3,1>(3, 7) = A * u_strut_init_; // w.r.t d_strut

    // Quaternion norm
    jacobian(6, 3) = 2.0 * p(0);
    jacobian(6, 4) = 2.0 * p(1);
    jacobian(6, 5) = 2.0 * p(2);
    jacobian(6, 6) = 2.0 * p(3);

    // Heave target
    jacobian(7, 2) = 1.0;
}

std::map<std::string, double> MacPherson::calculate_kinematics(
    const Eigen::VectorXd& state, 
    double tire_radius,
    double prev_spring_len,
    double dz_step,
    double cg_height_mm,
    double wheelbase_mm,
    double brake_bias,
    double drive_bias) const 
{
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    double d_strut    = state(7);
    Eigen::Matrix3d A = quat_to_rot(p);

    std::map<std::string, double> res;
    
    Eigen::Vector3d spin = A.col(1); // Local Y axis
    res["camber"] = std::atan2(-spin(2), spin(1)) * 180.0 / M_PI;
    res["toe"]    = std::atan2(spin(0), spin(1)) * 180.0 / M_PI;

    // Contact patch
    double r_tire_mm = tire_radius * 1000.0;
    Eigen::Vector3d cp = r - Eigen::Vector3d(0.0, 0.0, r_tire_mm);
    
    // Steering axis for MacPherson: line from lower ball joint to strut top mount
    Eigen::Vector3d ch_strut_top = base_hp_.at("chassis_strut_top");
    Eigen::Vector3d bj_lower = r + A * up_lower_;
    Eigen::Vector3d kingpin = ch_strut_top - bj_lower;
    double kp_norm = kingpin.norm();
    if (kp_norm > 1e-6) {
        kingpin /= kp_norm;
    } else {
        kingpin = Eigen::Vector3d::UnitZ();
    }

    res["caster"] = std::atan2(-kingpin(0), kingpin(2)) * 180.0 / M_PI;
    res["kpi"]    = std::atan2(-kingpin(1), kingpin(2)) * 180.0 / M_PI;

    // Scrub radius and mechanical trail
    if (std::abs(kingpin(2)) > 1e-6) {
        double t_ground = (cp(2) - bj_lower(2)) / kingpin(2);
        Eigen::Vector3d kp_ground = bj_lower + t_ground * kingpin;
        res["scrub_radius"]     = cp(1) - kp_ground(1);
        res["mechanical_trail"] = cp(0) - kp_ground(0);
    } else {
        res["scrub_radius"] = 0.0;
        res["mechanical_trail"] = 0.0;
    }

    // Track and wheelbase changes
    Eigen::Vector3d wc_init = base_hp_.at("wheel_center");
    res["track_change"]     = r(1) - wc_init(1);
    res["wheelbase_change"] = r(0) - wc_init(0);

    // Front View Instant Center & Roll Center
    Eigen::Vector3d ch_low_f = base_hp_.at("chassis_lower_front");
    Eigen::Vector3d ch_low_r = base_hp_.at("chassis_lower_rear");
    Eigen::Vector3d lca_inner = (ch_low_f + ch_low_r) * 0.5;
    
    Eigen::Vector3d fv_lca = bj_lower - lca_inner;
    fv_lca(0) = 0.0; // Project to Y-Z
    double lca_mag = fv_lca.norm();
    if (lca_mag > 1e-6) fv_lca /= lca_mag;

    Eigen::Vector3d strut_axis = ch_strut_top - bj_lower;
    strut_axis(0) = 0.0;
    double sa_mag = strut_axis.norm();
    if (sa_mag > 1e-6) strut_axis /= sa_mag;
    
    // Perpendicular to strut axis in front view
    Eigen::Vector3d upper_line_dir(0.0, -strut_axis(2), strut_axis(1));

    Eigen::Matrix2d mat;
    mat << fv_lca(1), -upper_line_dir(1),
           fv_lca(2), -upper_line_dir(2);
    
    Eigen::Vector2d rhs(ch_strut_top(1) - lca_inner(1), ch_strut_top(2) - lca_inner(2));
    double det_fv = mat.determinant();

    if (std::abs(det_fv) > 1e-6) {
        Eigen::Vector2d t_val = mat.colPivHouseholderQr().solve(rhs);
        Eigen::Vector3d ic = lca_inner + t_val(0) * fv_lca;
        res["ic_y"] = ic(1);
        res["ic_z"] = ic(2);

        double denom_rc = ic(1) - cp(1);
        if (std::abs(denom_rc) > 1e-6) {
            double t_rc = -cp(1) / denom_rc;
            res["rc_z"] = cp(2) + t_rc * (ic(2) - cp(2));
        } else {
            res["rc_z"] = ic(2);
        }
    } else {
        res["ic_y"] = 0.0;
        res["ic_z"] = 0.0;
        res["rc_z"] = 0.0;
    }

    // Side View Instant Center (Anti-Dive, Anti-Lift)
    Eigen::Vector3d sv_lca = bj_lower - lca_inner;
    sv_lca(1) = 0.0; // Project to X-Z
    double sv_lca_mag = sv_lca.norm();
    if (sv_lca_mag > 1e-6) sv_lca /= sv_lca_mag;

    Eigen::Vector3d sv_strut = ch_strut_top - bj_lower;
    sv_strut(1) = 0.0;
    double sv_strut_mag = sv_strut.norm();
    if (sv_strut_mag > 1e-6) sv_strut /= sv_strut_mag;

    Eigen::Vector3d sv_upper_perp(-sv_strut(2), 0.0, sv_strut(0));

    Eigen::Matrix2d mat_sv;
    mat_sv << sv_lca(0), -sv_upper_perp(0),
              sv_lca(2), -sv_upper_perp(2);
    
    Eigen::Vector2d rhs_sv(ch_strut_top(0) - lca_inner(0), ch_strut_top(2) - lca_inner(2));
    double det_sv = mat_sv.determinant();

    if (std::abs(det_sv) > 1e-6) {
        Eigen::Vector2d t_sv = mat_sv.colPivHouseholderQr().solve(rhs_sv);
        Eigen::Vector3d ic_sv = lca_inner + t_sv(0) * sv_lca;
        res["ic_sv_x"] = ic_sv(0);
        res["ic_sv_z"] = ic_sv(2);

        double sv_dx = ic_sv(0) - cp(0);
        if (std::abs(sv_dx) > 10.0 && wheelbase_mm > 0.0 && cg_height_mm > 0.0) {
            double tan_anti = (ic_sv(2) - cp(2)) / sv_dx;
            double h_over_L = cg_height_mm / wheelbase_mm;
            res["anti_dive_pct"] = (tan_anti / h_over_L) * brake_bias * 100.0;
            res["anti_squat_pct"] = (tan_anti / h_over_L) * drive_bias * 100.0;
            res["anti_lift_pct"] = res["anti_dive_pct"];
        } else {
            res["anti_dive_pct"] = 0.0;
            res["anti_squat_pct"] = 0.0;
            res["anti_lift_pct"] = 0.0;
        }
    } else {
        res["ic_sv_x"] = 0.0;
        res["ic_sv_z"] = 0.0;
        res["anti_dive_pct"] = 0.0;
        res["anti_squat_pct"] = 0.0;
        res["anti_lift_pct"] = 0.0;
    }

    // Jacking force coeff
    double half_track = std::abs(r(1));
    res["jacking_force_coeff"] = (half_track > 10.0) ? (res["rc_z"] / half_track) : 0.0;

    res["strut_extension"] = d_strut;
    res["spring_length"]   = d_strut;
    res["spring_proxy"]    = d_strut;
    res["heave_z"]         = r(2) - wc_init(2);

    double mr = 0.0;
    if (std::abs(dz_step) > 1e-9 && prev_spring_len >= 0.0) {
        mr = std::abs((d_strut - prev_spring_len) / dz_step);
    }
    res["motion_ratio"] = mr;

    return res;
}

} // namespace kinematics
} // namespace suspensionlab
