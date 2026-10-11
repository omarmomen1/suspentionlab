#define _USE_MATH_DEFINES
#include <cmath>
#include "suspension_kinematics/topologies.hpp"
#include "suspension_kinematics/exceptions.hpp"

namespace suspensionlab {
namespace kinematics {

namespace {

// Computes 3x3 rotation matrix A from quaternion p = [e0, e1, e2, e3]^T (Euler parameters: e0 = scalar, e1,e2,e3 = vector)
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

DoubleWishbone::DoubleWishbone(const std::map<std::string, Eigen::Vector3d>& hardpoints) 
    : base_hp_(hardpoints)
{
    ValidationReport rep = HardpointValidator::validate_double_wishbone(hardpoints);
    if (!rep.is_valid) {
        throw InvalidTopologyException("Invalid double wishbone hardpoints: " + rep.to_string());
    }

    initialize_geometry();
}

void DoubleWishbone::initialize_geometry() {
    l_uca_f_sq_ = (base_hp_["upright_upper"] - base_hp_["chassis_upper_front"]).squaredNorm();
    l_uca_r_sq_ = (base_hp_["upright_upper"] - base_hp_["chassis_upper_rear"]).squaredNorm();
    l_lca_f_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_front"]).squaredNorm();
    l_lca_r_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_rear"]).squaredNorm();
    l_tie_sq_   = (base_hp_["upright_tie_rod"] - base_hp_["chassis_tie_rod"]).squaredNorm();

    Eigen::Vector3d r_wc_init = base_hp_["wheel_center"];
    up_upper_ = base_hp_["upright_upper"] - r_wc_init;
    up_lower_ = base_hp_["upright_lower"] - r_wc_init;
    up_tie_   = base_hp_["upright_tie_rod"] - r_wc_init;
    up_wc_    = Eigen::Vector3d::Zero();

    if (base_hp_.find("pushrod_upright") != base_hp_.end() && base_hp_.find("pushrod_chassis") != base_hp_.end()) {
        up_pushrod_  = base_hp_["pushrod_upright"] - r_wc_init;
        pri_chassis_ = base_hp_["pushrod_chassis"];
        has_pushrod_ = true;
    } else if (base_hp_.find("PRO") != base_hp_.end() && base_hp_.find("PRI") != base_hp_.end()) {
        up_pushrod_  = base_hp_["PRO"] - r_wc_init;
        pri_chassis_ = base_hp_["PRI"];
        has_pushrod_ = true;
    } else {
        // Fallback default pushrod attachment on lower control arm / upright
        up_pushrod_  = up_lower_ + Eigen::Vector3d(0.0, -30.0, 50.0);
        pri_chassis_ = base_hp_["chassis_lower_front"] + Eigen::Vector3d(0.0, 100.0, 200.0);
        has_pushrod_ = true;
    }

    heave_target_z_ = r_wc_init(2);
}

void DoubleWishbone::set_target_inputs(double heave_mm, double roll_deg, double steer_deg, double pitch_deg) {
    Eigen::Vector3d wc_init = base_hp_.at("wheel_center");
    heave_target_z_ = wc_init(2) + heave_mm;
    roll_input_deg_ = roll_deg;
    steer_target_deg_ = steer_deg;
    pitch_input_deg_ = pitch_deg;
}

void DoubleWishbone::set_heave_target(double z_world_mm) {
    heave_target_z_ = z_world_mm;
}

void DoubleWishbone::set_steer_target_deg(double steer_deg) {
    steer_target_deg_ = steer_deg;
}

ValidationReport DoubleWishbone::validate(double tire_radius) const {
    return HardpointValidator::validate_double_wishbone(base_hp_, tire_radius);
}

double DoubleWishbone::get_spring_length(const Eigen::VectorXd& state) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    Eigen::Matrix3d A = quat_to_rot(p);
    Eigen::Vector3d pro_world = r + A * up_pushrod_;
    return (pro_world - pri_chassis_).norm();
}

void DoubleWishbone::evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    
    Eigen::Matrix3d A = quat_to_rot(p);

    Eigen::Vector3d pos_upper = r + A * up_upper_;
    Eigen::Vector3d pos_lower = r + A * up_lower_;
    Eigen::Vector3d pos_tie   = r + A * up_tie_;

    // Rack steer displacement model: steer target translates the inboard tie rod laterally
    // For 1 degree of steer, rack displacement ~ 1.2 mm
    double rack_dy = steer_target_deg_ * 1.2;
    Eigen::Vector3d ch_tie = base_hp_.at("chassis_tie_rod") + Eigen::Vector3d(0.0, rack_dy, 0.0);

    residuals.resize(7);
    
    // 1. UCA Front
    residuals(0) = (pos_upper - base_hp_.at("chassis_upper_front")).squaredNorm() - l_uca_f_sq_;
    // 2. UCA Rear
    residuals(1) = (pos_upper - base_hp_.at("chassis_upper_rear")).squaredNorm() - l_uca_r_sq_;
    // 3. LCA Front
    residuals(2) = (pos_lower - base_hp_.at("chassis_lower_front")).squaredNorm() - l_lca_f_sq_;
    // 4. LCA Rear
    residuals(3) = (pos_lower - base_hp_.at("chassis_lower_rear")).squaredNorm() - l_lca_r_sq_;
    // 5. Tie Rod
    residuals(4) = (pos_tie - ch_tie).squaredNorm() - l_tie_sq_;
    // 6. Heave Constraint (Z of wheel center = target)
    Eigen::Vector3d pos_wc = r + A * up_wc_; // pos_wc = r
    residuals(5) = pos_wc(2) - heave_target_z_;
    // 7. Quaternion normalization
    residuals(6) = p.squaredNorm() - 1.0;
}

void DoubleWishbone::evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    
    Eigen::Matrix3d A = quat_to_rot(p);

    Eigen::Vector3d pos_upper = r + A * up_upper_;
    Eigen::Vector3d pos_lower = r + A * up_lower_;
    Eigen::Vector3d pos_tie   = r + A * up_tie_;

    double rack_dy = steer_target_deg_ * 1.2;
    Eigen::Vector3d ch_tie = base_hp_.at("chassis_tie_rod") + Eigen::Vector3d(0.0, rack_dy, 0.0);

    jacobian = Eigen::MatrixXd::Zero(7, 7);

    auto add_distance_jac = [&](int row, const Eigen::Vector3d& pos_P, const Eigen::Vector3d& pos_C, const Eigen::Vector3d& s_prime) {
        Eigen::Vector3d diff = pos_P - pos_C;
        // w.r.t r (cols 0, 1, 2)
        jacobian.block<1, 3>(row, 0) = 2.0 * diff.transpose();
        // w.r.t p (cols 3, 4, 5, 6)
        jacobian.block<1, 4>(row, 3) = 2.0 * diff.transpose() * d_A_s_dp(p, s_prime);
    };

    // 1-5. Distance constraints
    add_distance_jac(0, pos_upper, base_hp_.at("chassis_upper_front"), up_upper_);
    add_distance_jac(1, pos_upper, base_hp_.at("chassis_upper_rear"),  up_upper_);
    add_distance_jac(2, pos_lower, base_hp_.at("chassis_lower_front"), up_lower_);
    add_distance_jac(3, pos_lower, base_hp_.at("chassis_lower_rear"),  up_lower_);
    add_distance_jac(4, pos_tie,   ch_tie,                             up_tie_);

    // 6. Heave Constraint: dr_z / d(x,y,z,e0..e3)
    jacobian(5, 2) = 1.0;

    // 7. Quaternion normalization: 2*e0, 2*e1, 2*e2, 2*e3
    jacobian(6, 3) = 2.0 * p(0);
    jacobian(6, 4) = 2.0 * p(1);
    jacobian(6, 5) = 2.0 * p(2);
    jacobian(6, 6) = 2.0 * p(3);
}

std::map<std::string, double> DoubleWishbone::calculate_kinematics(
    const Eigen::VectorXd& state, 
    double tire_radius,
    double prev_spring_len,
    double dz_step,
    double cg_height_mm,
    double wheelbase_mm,
    double brake_bias,
    double drive_bias) const 
{
    std::map<std::string, double> res;
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    Eigen::Matrix3d A = quat_to_rot(p);

    Eigen::Vector3d pos_upper = r + A * up_upper_;
    Eigen::Vector3d pos_lower = r + A * up_lower_;
    Eigen::Vector3d pos_wc    = r;
    Eigen::Vector3d pos_pro   = r + A * up_pushrod_;

    // Wheel spin axis in world coordinates (local Y axis)
    Eigen::Vector3d spin = A.col(1);

    // 1. Camber angle (+ = top of wheel tilts outboard)
    res["camber"] = std::atan2(spin(2), spin(1)) * 180.0 / M_PI;

    // 2. Toe angle (+ = toe-out)
    res["toe"] = std::atan2(spin(0), spin(1)) * 180.0 / M_PI;

    // Steering axis (Kingpin vector from lower to upper ball joint)
    Eigen::Vector3d kp = pos_upper - pos_lower;
    double kp_norm = kp.norm();
    if (kp_norm > 1e-6) {
        kp /= kp_norm;
    } else {
        kp = Eigen::Vector3d::UnitZ();
    }

    // 3. Caster angle in X-Z plane (+ = rearward inclination at top)
    res["caster"] = std::atan2(-kp(0), kp(2)) * 180.0 / M_PI;

    // 4. Kingpin Inclination (KPI) in Y-Z plane (+ = top inboard)
    res["kpi"] = std::atan2(kp(1), kp(2)) * 180.0 / M_PI;

    // Contact patch location in world coordinates (Z = 0 at design ground)
    double r_tire_mm = tire_radius * 1000.0;
    Eigen::Vector3d cp = pos_wc - Eigen::Vector3d(0.0, 0.0, r_tire_mm);

    // 5. Scrub radius and Mechanical Trail (ground intersection of kingpin axis)
    if (std::abs(kp(2)) > 1e-6) {
        double t_ground = (cp(2) - pos_lower(2)) / kp(2);
        Eigen::Vector3d kp_ground = pos_lower + t_ground * kp;
        res["scrub_radius"] = cp(1) - kp_ground(1);
        res["mechanical_trail"] = cp(0) - kp_ground(0);
    } else {
        res["scrub_radius"] = 0.0;
        res["mechanical_trail"] = 0.0;
    }

    // 6. Track change and Wheelbase change
    Eigen::Vector3d wc_init = base_hp_.at("wheel_center");
    res["track_change"] = pos_wc(1) - wc_init(1);
    res["wheelbase_change"] = pos_wc(0) - wc_init(0);

    // 7. Front-View Instant Center & Roll Center Height
    Eigen::Vector3d uwi_mid = 0.5 * (base_hp_.at("chassis_upper_front") + base_hp_.at("chassis_upper_rear"));
    Eigen::Vector3d lwi_mid = 0.5 * (base_hp_.at("chassis_lower_front") + base_hp_.at("chassis_lower_rear"));

    double p1y = lwi_mid(1), p1z = lwi_mid(2);
    double d1y = pos_lower(1) - p1y, d1z = pos_lower(2) - p1z;
    double p2y = uwi_mid(1), p2z = uwi_mid(2);
    double d2y = pos_upper(1) - p2y, d2z = pos_upper(2) - p2z;

    double det_fv = d1y * (-d2z) - d1z * (-d2y);
    if (std::abs(det_fv) > 1e-6) {
        double t1 = ((p2y - p1y) * (-d2z) - (p2z - p1z) * (-d2y)) / det_fv;
        double ic_y = p1y + t1 * d1y;
        double ic_z = p1z + t1 * d1z;
        res["ic_y"] = ic_y;
        res["ic_z"] = ic_z;

        double cp_denom = ic_y - cp(1);
        if (std::abs(cp_denom) > 1e-6) {
            double t_rc = -cp(1) / cp_denom;
            res["rc_z"] = cp(2) + t_rc * (ic_z - cp(2));
        } else {
            res["rc_z"] = ic_z;
        }
    } else {
        res["ic_y"] = 0.0;
        res["ic_z"] = 0.0;
        res["rc_z"] = 0.0;
    }

    // 8. Side-View Instant Center for Anti-Dive / Anti-Squat
    double p1x_sv = lwi_mid(0), p1z_sv = lwi_mid(2);
    double d1x_sv = pos_lower(0) - p1x_sv, d1z_sv = pos_lower(2) - p1z_sv;
    double p2x_sv = uwi_mid(0), p2z_sv = uwi_mid(2);
    double d2x_sv = pos_upper(0) - p2x_sv, d2z_sv = pos_upper(2) - p2z_sv;

    double det_sv = d1x_sv * (-d2z_sv) - d1z_sv * (-d2x_sv);
    if (std::abs(det_sv) > 1e-6) {
        double t_sv = ((p2x_sv - p1x_sv) * (-d2z_sv) - (p2z_sv - p1z_sv) * (-d2x_sv)) / det_sv;
        double ic_sv_x = p1x_sv + t_sv * d1x_sv;
        double ic_sv_z = p1z_sv + t_sv * d1z_sv;
        res["ic_sv_x"] = ic_sv_x;
        res["ic_sv_z"] = ic_sv_z;

        // Anti-geometry angles relative to contact patch
        double sv_dx = ic_sv_x - cp(0);
        if (std::abs(sv_dx) > 10.0 && wheelbase_mm > 0.0 && cg_height_mm > 0.0) {
            double tan_anti = (ic_sv_z - cp(2)) / sv_dx;
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

    // 9. Jacking force coefficient
    double half_track = std::abs(pos_wc(1));
    res["jacking_force_coeff"] = (half_track > 10.0) ? (res["rc_z"] / half_track) : 0.0;

    // 10. Spring / pushrod length & motion ratio
    double cur_spring_len = (pos_pro - pri_chassis_).norm();
    res["spring_length"] = cur_spring_len;
    res["spring_proxy"]  = cur_spring_len;
    res["heave_z"]       = pos_wc(2) - wc_init(2);

    double mr = 0.0;
    if (std::abs(dz_step) > 1e-9 && prev_spring_len >= 0.0) {
        mr = std::abs((cur_spring_len - prev_spring_len) / dz_step);
    }
    res["motion_ratio"] = mr;

    return res;
}

} // namespace kinematics
} // namespace suspensionlab
