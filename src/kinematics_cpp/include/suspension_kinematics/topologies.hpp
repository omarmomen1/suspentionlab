#pragma once
#include <Eigen/Dense>
#include <map>
#include <string>
#include <vector>
#include "suspension_kinematics/exceptions.hpp"
#include "suspension_kinematics/hardpoint_validation.hpp"
#include "suspension_kinematics/bushing_compliance.hpp"

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

    // Set multidimensional inputs
    virtual void set_target_inputs(double heave_mm, double roll_deg = 0.0, double steer_deg = 0.0, double pitch_deg = 0.0) = 0;

    // Calculates all kinematic parameters
    virtual std::map<std::string, double> calculate_kinematics(
        const Eigen::VectorXd& state, 
        double tire_radius = 0.33,
        double prev_spring_len = -1.0,
        double dz_step = 0.0,
        double cg_height_mm = 350.0,
        double wheelbase_mm = 2600.0,
        double brake_bias = 0.60,
        double drive_bias = 1.00) const = 0;

    // Computes instantaneous spring/damper length
    virtual double get_spring_length(const Eigen::VectorXd& state) const = 0;

    // Validates topology hardpoint geometry
    virtual ValidationReport validate(double tire_radius = 0.33) const = 0;
};

class DoubleWishbone : public ISuspensionTopology {
public:
    explicit DoubleWishbone(const std::map<std::string, Eigen::Vector3d>& hardpoints);

    void evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const override;
    void evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const override;
    int num_states() const override { return 7; } // x, y, z, e0, e1, e2, e3
    
    void set_target_inputs(double heave_mm, double roll_deg = 0.0, double steer_deg = 0.0, double pitch_deg = 0.0) override;
    void set_heave_target(double z_world_mm);
    void set_steer_target_deg(double steer_deg);

    std::map<std::string, double> calculate_kinematics(
        const Eigen::VectorXd& state, 
        double tire_radius = 0.33,
        double prev_spring_len = -1.0,
        double dz_step = 0.0,
        double cg_height_mm = 350.0,
        double wheelbase_mm = 2600.0,
        double brake_bias = 0.60,
        double drive_bias = 1.00) const override;

    double get_spring_length(const Eigen::VectorXd& state) const override;
    ValidationReport validate(double tire_radius = 0.33) const override;

    const std::map<std::string, Eigen::Vector3d>& base_hardpoints() const { return base_hp_; }

private:
    std::map<std::string, Eigen::Vector3d> base_hp_;
    double heave_target_z_ = 0.0;
    double steer_target_deg_ = 0.0;
    double roll_input_deg_ = 0.0;
    double pitch_input_deg_ = 0.0;

    // Reference link lengths squared
    double l_uca_f_sq_ = 0.0, l_uca_r_sq_ = 0.0;
    double l_lca_f_sq_ = 0.0, l_lca_r_sq_ = 0.0;
    double l_tie_sq_   = 0.0;

    // Upright local coordinates of the ball joints
    Eigen::Vector3d up_upper_, up_lower_, up_tie_, up_pushrod_, up_wc_;

    // Inboard rocker/pushrod chassis pivot
    Eigen::Vector3d pri_chassis_;
    bool has_pushrod_ = false;

    void initialize_geometry();
};

class MacPherson : public ISuspensionTopology {
public:
    explicit MacPherson(const std::map<std::string, Eigen::Vector3d>& hardpoints);

    void evaluate_constraints(const Eigen::VectorXd& state, Eigen::VectorXd& residuals) const override;
    void evaluate_jacobian(const Eigen::VectorXd& state, Eigen::MatrixXd& jacobian) const override;
    int num_states() const override { return 8; } // x, y, z, e0, e1, e2, e3, d_strut
    
    void set_target_inputs(double heave_mm, double roll_deg = 0.0, double steer_deg = 0.0, double pitch_deg = 0.0) override;
    void set_heave_target(double z_world_mm);
    void set_steer_target_deg(double steer_deg);

    std::map<std::string, double> calculate_kinematics(
        const Eigen::VectorXd& state, 
        double tire_radius = 0.33,
        double prev_spring_len = -1.0,
        double dz_step = 0.0,
        double cg_height_mm = 350.0,
        double wheelbase_mm = 2600.0,
        double brake_bias = 0.60,
        double drive_bias = 1.00) const override;

    double get_spring_length(const Eigen::VectorXd& state) const override;
    ValidationReport validate(double tire_radius = 0.33) const override;

    const std::map<std::string, Eigen::Vector3d>& base_hardpoints() const { return base_hp_; }

private:
    std::map<std::string, Eigen::Vector3d> base_hp_;
    double heave_target_z_ = 0.0;
    double steer_target_deg_ = 0.0;
    double roll_input_deg_ = 0.0;
    double pitch_input_deg_ = 0.0;

    double l_lca_f_sq_ = 0.0, l_lca_r_sq_ = 0.0;
    double l_tie_sq_   = 0.0;

    Eigen::Vector3d up_lower_, up_tie_, up_wc_, up_strut_mount_;
    Eigen::Vector3d u_strut_init_;

    void initialize_geometry();
};

} // namespace kinematics
} // namespace suspensionlab
