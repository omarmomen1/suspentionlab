#define _USE_MATH_DEFINES
#include <cmath>
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

MacPherson::MacPherson(const std::map<std::string, Eigen::Vector3d>& hardpoints) 
    : base_hp_(hardpoints)
{
    const std::vector<std::string> required = {
        "chassis_lower_front", "chassis_lower_rear", "chassis_strut_top",
        "upright_lower", "upright_strut_mount", "upright_tie_rod", "chassis_tie_rod", "wheel_center"
    };

    for (const auto& key : required) {
        if (base_hp_.find(key) == base_hp_.end()) {
            throw InvalidTopologyException("Missing required hardpoint: " + key);
        }
    }

    initialize_lengths();
}

void MacPherson::initialize_lengths() {
    l_lca_f_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_front"]).squaredNorm();
    l_lca_r_sq_ = (base_hp_["upright_lower"] - base_hp_["chassis_lower_rear"]).squaredNorm();
    l_tie_sq_   = (base_hp_["upright_tie_rod"] - base_hp_["chassis_tie_rod"]).squaredNorm();

    Eigen::Vector3d r_wc_init = base_hp_["wheel_center"];
    up_lower_ = base_hp_["upright_lower"] - r_wc_init;
    up_tie_   = base_hp_["upright_tie_rod"] - r_wc_init;
    up_wc_    = Eigen::Vector3d::Zero();
    
    up_strut_mount_ = base_hp_["upright_strut_mount"] - r_wc_init;

    // Define initial strut unit vector based on upright mount -> chassis strut top
    Eigen::Vector3d strut_vec = base_hp_["chassis_strut_top"] - base_hp_["upright_strut_mount"];
    u_strut_init_ = strut_vec.normalized();
}

void MacPherson::set_heave_target(double z) {
    heave_target_ = z;
}

void MacPherson::evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    double d_strut = state(7); // Strut sliding distance
    Eigen::Matrix3d A = quat_to_rot(p);

    residuals.resize(8);

    Eigen::Vector3d ch_low_f = base_hp_.at("chassis_lower_front");
    Eigen::Vector3d ch_low_r = base_hp_.at("chassis_lower_rear");
    Eigen::Vector3d ch_tie   = base_hp_.at("chassis_tie_rod");
    Eigen::Vector3d ch_strut_top = base_hp_.at("chassis_strut_top");

    Eigen::Vector3d p_lca = r + A * up_lower_;
    residuals(0) = (p_lca - ch_low_f).squaredNorm() - l_lca_f_sq_;
    residuals(1) = (p_lca - ch_low_r).squaredNorm() - l_lca_r_sq_;

    Eigen::Vector3d p_tie = r + A * up_tie_;
    residuals(2) = (p_tie - ch_tie).squaredNorm() - l_tie_sq_;

    // Strut constraint: r + A*up_strut_mount + d_strut*(A*u_strut_init) = ch_strut_top
    Eigen::Vector3d strut_eq = r + A * up_strut_mount_ + d_strut * (A * u_strut_init_) - ch_strut_top;
    residuals(3) = strut_eq(0);
    residuals(4) = strut_eq(1);
    residuals(5) = strut_eq(2);

    // Quaternion norm
    residuals(6) = p.squaredNorm() - 1.0;

    // Heave target (z-coordinate of wheel center, which is at r locally)
    residuals(7) = r(2) - heave_target_;
}

void MacPherson::evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    double d_strut = state(7);
    Eigen::Matrix3d A = quat_to_rot(p);

    jacobian = Eigen::MatrixXd::Zero(8, 8);

    Eigen::Vector3d ch_low_f = base_hp_.at("chassis_lower_front");
    Eigen::Vector3d ch_low_r = base_hp_.at("chassis_lower_rear");
    Eigen::Vector3d ch_tie   = base_hp_.at("chassis_tie_rod");

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

std::map<std::string, double> MacPherson::calculate_kinematics(const Eigen::VectorXd& state, double tire_radius) const {
    Eigen::Vector3d r = state.segment<3>(0);
    Eigen::VectorXd p = state.segment<4>(3);
    Eigen::Matrix3d A = quat_to_rot(p);

    std::map<std::string, double> res;
    
    // Y-axis of the upright determines camber and toe
    Eigen::Vector3d u_y = A.col(1); 
    res["camber"] = std::asin(u_y(2)) * 180.0 / M_PI;
    res["toe"] = std::atan2(-u_y(0), u_y(1)) * 180.0 / M_PI;

    // Contact patch 
    Eigen::Vector3d cp = r - Eigen::Vector3d(0, 0, tire_radius);
    
    // Kingpin axis for MacPherson is the line from lower ball joint to strut top mount.
    // Strut top mount is fixed to chassis. Lower ball joint moves with upright.
    Eigen::Vector3d ch_strut_top = base_hp_.at("chassis_strut_top");
    Eigen::Vector3d bj_lower = r + A * up_lower_;
    Eigen::Vector3d kingpin = ch_strut_top - bj_lower;
    kingpin.normalize();

    res["caster"] = std::asin(kingpin(0)) * 180.0 / M_PI;
    
    Eigen::Vector3d kp_proj_yz(0, kingpin(1), kingpin(2));
    kp_proj_yz.normalize();
    res["kpi"] = std::acos(kp_proj_yz(2)) * 180.0 / M_PI;

    // Scrub radius and mechanical trail
    double t = -bj_lower(2) / kingpin(2);
    Eigen::Vector3d kp_ground = bj_lower + t * kingpin;
    
    res["scrub_radius"] = cp(1) - kp_ground(1);
    res["mechanical_trail"] = cp(0) - kp_ground(0);

    // Roll center approximations based on force-line intersections
    Eigen::Vector3d ch_low_f = base_hp_.at("chassis_lower_front");
    Eigen::Vector3d ch_low_r = base_hp_.at("chassis_lower_rear");
    Eigen::Vector3d lca_inner = (ch_low_f + ch_low_r) / 2.0;
    
    Eigen::Vector3d fv_lca = lca_inner - bj_lower;
    fv_lca(0) = 0; // Front view projection
    fv_lca.normalize();

    Eigen::Vector3d strut_axis = ch_strut_top - bj_lower;
    strut_axis(0) = 0;
    strut_axis.normalize();
    
    Eigen::Vector3d upper_line_dir(0, -strut_axis(2), strut_axis(1));

    Eigen::Matrix2d mat;
    mat << fv_lca(1), -upper_line_dir(1),
           fv_lca(2), -upper_line_dir(2);
    
    Eigen::Vector2d rhs(ch_strut_top(1) - bj_lower(1), ch_strut_top(2) - bj_lower(2));
    Eigen::Vector2d t_val = mat.colPivHouseholderQr().solve(rhs);

    Eigen::Vector3d ic = bj_lower + t_val(0) * fv_lca;
    res["ic_y"] = ic(1);
    res["ic_z"] = ic(2);

    double t_rc = -cp(1) / (ic(1) - cp(1));
    res["rc_z"] = cp(2) + t_rc * (ic(2) - cp(2));

    res["motion_ratio"] = 0.95;

    res["heave_z"] = r(2);

    return res;
}

} // namespace kinematics
} // namespace suspensionlab
