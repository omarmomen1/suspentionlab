#pragma once
#include <Eigen/Dense>
#include <map>
#include <string>

namespace suspensionlab {
namespace kinematics {

class ISuspensionTopology {
public:
    virtual ~ISuspensionTopology() = default;

    // Evaluates the geometric constraints. Residuals must be sized appropriately.
    virtual void evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const = 0;

    // Evaluates the analytic Jacobian of the constraints.
    virtual void evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const = 0;

    // Returns the number of DOFs (size of state vector)
    virtual int num_states() const = 0;

    // Calculates all kinematic parameters
    virtual std::map<std::string, double> calculate_kinematics(const Eigen::VectorXd& state, double tire_radius = 0.3) const = 0;
};

class DoubleWishbone : public ISuspensionTopology {
public:
    // Hardpoints expected:
    // chassis_upper_front, chassis_upper_rear, chassis_lower_front, chassis_lower_rear,
    // upright_upper, upright_lower, upright_tie_rod, chassis_tie_rod (or rack)
    DoubleWishbone(const std::map<std::string, Eigen::Vector3d>& hardpoints);

    void evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const override;
    void evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const override;
    int num_states() const override { return 7; } // x, y, z, e0, e1, e2, e3
    
    std::map<std::string, double> calculate_kinematics(const Eigen::VectorXd& state, double tire_radius = 0.3) const override;

    // Update the heave target or rack displacement
    void set_heave_target(double z);
    
private:
    std::map<std::string, Eigen::Vector3d> base_hp_;
    double heave_target_ = 0.0;

    // Link lengths (squared for efficiency)
    double l_uca_f_sq_, l_uca_r_sq_;
    double l_lca_f_sq_, l_lca_r_sq_;
    double l_tie_sq_;

    // Upright local coordinates of the ball joints
    Eigen::Vector3d up_upper_, up_lower_, up_tie_, up_wc_;

    // Initialization helper
    void initialize_lengths();
};

class MacPherson : public ISuspensionTopology {
public:
    MacPherson(const std::map<std::string, Eigen::Vector3d>& hardpoints);

    void evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const override;
    void evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const override;
    int num_states() const override { return 8; } // x, y, z, e0, e1, e2, e3, d_strut
    
    std::map<std::string, double> calculate_kinematics(const Eigen::VectorXd& state, double tire_radius = 0.3) const override;

    void set_heave_target(double z);
    
private:
    std::map<std::string, Eigen::Vector3d> base_hp_;
    double heave_target_ = 0.0;

    double l_lca_f_sq_, l_lca_r_sq_;
    double l_tie_sq_;

    Eigen::Vector3d up_lower_, up_tie_, up_wc_, up_strut_mount_;
    Eigen::Vector3d u_strut_init_;

    void initialize_lengths();
};

} // namespace kinematics
} // namespace suspensionlab
