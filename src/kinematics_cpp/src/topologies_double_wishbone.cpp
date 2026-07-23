#include "suspension_kinematics/topologies.hpp"
#include "suspension_kinematics/exceptions.hpp"
#include <stdexcept>

namespace suspensionlab {
namespace kinematics {

namespace {

// Computes 3x3 rotation matrix A from quaternion p = [e0, e1, e2, e3]^T
Eigen::Matrix3d quat_to_rot(const Eigen::VectorXd& p) {
    double e0 = p(0), e1 = p(1), e2 = p(2), e3 = p(3);
    Eigen::Matrix3d A;
    A(0,0) = 2*(e0*e0 + e1*e1) - 1;
    A(0,1) = 2*(e1*e2 - e0*e3);
    A(0,2) = 2*(e1*e3 + e0*e2);
    
    A(1,0) = 2*(e1*e2 + e0*e3);
    A(1,1) = 2*(e0*e0 + e2*e2) - 1;
    A(1,2) = 2*(e2*e3 - e0*e1);
    
    A(2,0) = 2*(e1*e3 - e0*e2);
    A(2,1) = 2*(e2*e3 + e0*e1);
    A(2,2) = 2*(e0*e0 + e3*e3) - 1;
    return A;
}

// Derivative of A(p)*s w.r.t p. Returns a 3x4 matrix.
Eigen::Matrix<double, 3, 4> d_A_s_dp(const Eigen::VectorXd& p, const Eigen::Vector3d& s) {
    double e0 = p(0), e1 = p(1), e2 = p(2), e3 = p(3);
    double x = s(0), y = s(1), z = s(2);
    
    Eigen::Matrix<double, 3, 4> D;
    
    // col 0 (w.r.t e0)
    D(0,0) =  4*e0*x - 2*e3*y + 2*e2*z;
    D(1,0) =  2*e3*x + 4*e0*y - 2*e1*z;
    D(2,0) = -2*e2*x + 2*e1*y + 4*e0*z;
    
    // col 1 (w.r.t e1)
    D(0,1) =  4*e1*x + 2*e2*y + 2*e3*z;
    D(1,1) =  2*e2*x          - 2*e0*z;
    D(2,1) =  2*e3*x + 2*e0*y;
    
    // col 2 (w.r.t e2)
    D(0,2) =           2*e1*y + 2*e0*z;
    D(1,2) =  2*e1*x + 4*e2*y + 2*e3*z;
    D(2,2) = -2*e0*x + 2*e3*y;
    
    // col 3 (w.r.t e3)
    D(0,3) =         - 2*e0*y + 2*e1*z;
    D(1,3) =  2*e0*x          + 2*e2*z;
    D(2,3) =  2*e1*x + 2*e2*y + 4*e3*z;
    
    return D;
}

} // namespace

DoubleWishbone::DoubleWishbone(const std::map<std::string, Eigen::Vector3d>& hardpoints) 
    : base_hp_(hardpoints)
{
    const std::vector<std::string> required = {
        "chassis_upper_front", "chassis_upper_rear", "chassis_lower_front", "chassis_lower_rear",
        "upright_upper", "upright_lower", "upright_tie_rod", "chassis_tie_rod", "wheel_center"
    };

    for (const auto& key : required) {
        if (base_hp_.find(key) == base_hp_.end()) {
            throw InvalidTopologyException("Missing required hardpoint: " + key);
        }
    }

    initialize_lengths();
}

void DoubleWishbone::initialize_lengths() {
    // Initial lengths squared
    l_uca_f_sq_ = (base_hp_["upright_upper"] - base_hp_["chassis_upper_front"]).squaredNorm();
    l_uca_r_sq_ = (base_hp_["upright_upper"] - base_hp_["chassis_upper_rear"]).squaredNorm();
    l_lca_f_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_front"]).squaredNorm();
    l_lca_r_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_rear"]).squaredNorm();
    l_tie_sq_   = (base_hp_["upright_tie_rod"] - base_hp_["chassis_tie_rod"]).squaredNorm();

    // Store local upright coordinates assuming the initial wheel_center is the origin (0,0,0) in local space
    // Let's define the upright origin as the wheel center.
    Eigen::Vector3d r_wc_init = base_hp_["wheel_center"];
    up_upper_ = base_hp_["upright_upper"] - r_wc_init;
    up_lower_ = base_hp_["upright_lower"] - r_wc_init;
    up_tie_   = base_hp_["upright_tie_rod"] - r_wc_init;
    up_wc_    = Eigen::Vector3d::Zero();
}

void DoubleWishbone::set_heave_target(double z) {
    heave_target_ = z;
}

void DoubleWishbone::evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    
    Eigen::Matrix3d A = quat_to_rot(p);

    Eigen::Vector3d pos_upper = r + A * up_upper_;
    Eigen::Vector3d pos_lower = r + A * up_lower_;
    Eigen::Vector3d pos_tie   = r + A * up_tie_;

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
    residuals(4) = (pos_tie - base_hp_.at("chassis_tie_rod")).squaredNorm() - l_tie_sq_;
    // 6. Heave Constraint (Z of wheel center = target)
    Eigen::Vector3d pos_wc = r + A * up_wc_; // up_wc_ is Zero, so pos_wc = r.
    residuals(5) = pos_wc(2) - heave_target_;
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

    jacobian = Eigen::MatrixXd::Zero(7, 7);

    // Helpers
    auto add_distance_jac = [&](int row, const Eigen::Vector3d& pos_P, const Eigen::Vector3d& pos_C, const Eigen::Vector3d& s_prime) {
        Eigen::Vector3d diff = pos_P - pos_C;
        // w.r.t r (cols 0, 1, 2)
        jacobian.block<1, 3>(row, 0) = 2.0 * diff.transpose();
        // w.r.t p (cols 3, 4, 5, 6)
        jacobian.block<1, 4>(row, 3) = 2.0 * diff.transpose() * d_A_s_dp(p, s_prime);
    };

    // 1-5. Distance constraints
    add_distance_jac(0, pos_upper, base_hp_.at("chassis_upper_front"), up_upper_);
    add_distance_jac(1, pos_upper, base_hp_.at("chassis_upper_rear"), up_upper_);
    add_distance_jac(2, pos_lower, base_hp_.at("chassis_lower_front"), up_lower_);
    add_distance_jac(3, pos_lower, base_hp_.at("chassis_lower_rear"), up_lower_);
    add_distance_jac(4, pos_tie,   base_hp_.at("chassis_tie_rod"),     up_tie_);

    // 6. Heave Constraint: r_z = heave_target_ -> dr_z / d(x,y,z,e0,e1,e2,e3)
    jacobian(5, 2) = 1.0; // derivative w.r.t z
    // if up_wc_ was non-zero, we'd add derivative w.r.t p here too, but up_wc_ is exactly [0,0,0].

    // 7. Quaternion normalization: e0^2 + e1^2 + e2^2 + e3^2 - 1 = 0
    jacobian(6, 3) = 2.0 * p(0);
    jacobian(6, 4) = 2.0 * p(1);
    jacobian(6, 5) = 2.0 * p(2);
    jacobian(6, 6) = 2.0 * p(3);
}

std::map<std::string, double> DoubleWishbone::calculate_kinematics(const Eigen::VectorXd& state, double tire_radius) const {
    std::map<std::string, double> res;
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    Eigen::Matrix3d A = quat_to_rot(p);

    Eigen::Vector3d pos_upper = r + A * up_upper_;
    Eigen::Vector3d pos_lower = r + A * up_lower_;
    Eigen::Vector3d pos_wc = r;

    Eigen::Vector3d v_up = A * Eigen::Vector3d(0, 0, 1);
    Eigen::Vector3d v_fwd = A * Eigen::Vector3d(1, 0, 0);

    // 1. Camber
    res["camber"] = std::atan2(-v_up.y(), v_up.z()) * 180.0 / 3.14159265358979323846;

    // 2. Toe
    res["toe"] = std::atan2(v_fwd.y(), v_fwd.x()) * 180.0 / 3.14159265358979323846;

    // Steering axis (Kingpin)
    Eigen::Vector3d kingpin_vec = pos_upper - pos_lower;
    kingpin_vec.normalize();

    // 3. Caster (angle in X-Z plane)
    res["caster"] = std::atan2(-kingpin_vec.x(), kingpin_vec.z()) * 180.0 / 3.14159265358979323846;

    // 4. KPI (angle in Y-Z plane)
    res["kpi"] = std::atan2(kingpin_vec.y(), kingpin_vec.z()) * 180.0 / 3.14159265358979323846;

    // 5. Scrub radius & Mechanical Trail
    double t_ground = (pos_wc.z() - tire_radius - pos_lower.z()) / kingpin_vec.z();
    Eigen::Vector3d kp_ground = pos_lower + t_ground * kingpin_vec;
    res["scrub_radius"] = kp_ground.y() - pos_wc.y();
    res["mechanical_trail"] = pos_wc.x() - kp_ground.x();

    // 7. Instant Center & Roll Center (Front View)
    Eigen::Vector3d inner_upper = 0.5 * (base_hp_.at("chassis_upper_front") + base_hp_.at("chassis_upper_rear"));
    Eigen::Vector3d inner_lower = 0.5 * (base_hp_.at("chassis_lower_front") + base_hp_.at("chassis_lower_rear"));

    double y1 = inner_upper.y(), z1 = inner_upper.z();
    double y2 = pos_upper.y(), z2 = pos_upper.z();
    double y3 = inner_lower.y(), z3 = inner_lower.z();
    double y4 = pos_lower.y(), z4 = pos_lower.z();

    double denom = (y1 - y2) * (z3 - z4) - (z1 - z2) * (y3 - y4);
    double cp_y = pos_wc.y();
    double cp_z = pos_wc.z() - tire_radius;

    if (std::abs(denom) > 1e-6) {
        double t_num = (y1 - y3) * (z3 - z4) - (z1 - z3) * (y3 - y4);
        double t = t_num / denom;
        double ic_y = y1 + t * (y2 - y1);
        double ic_z = z1 + t * (z2 - z1);
        res["ic_y"] = ic_y;
        res["ic_z"] = ic_z;

        double rc_denom = cp_y - ic_y;
        if (std::abs(rc_denom) > 1e-6) {
            double rc_z = cp_z - cp_y * (cp_z - ic_z) / rc_denom;
            res["rc_z"] = rc_z;
        } else {
            res["rc_z"] = cp_z;
        }
    } else {
        res["ic_y"] = 0.0;
        res["ic_z"] = 0.0;
        double slope = (z2 - z1) / (y2 - y1);
        double rc_z = cp_z - slope * cp_y;
        res["rc_z"] = rc_z;
    }

    res["motion_ratio"] = 1.0; 
    res["heave_z"] = pos_wc.z() - base_hp_.at("wheel_center").z();

    return res;
}

} // namespace kinematics
} // namespace suspensionlab

