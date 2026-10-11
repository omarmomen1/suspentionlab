#pragma once
#include <Eigen/Dense>
#include <map>
#include <string>

namespace suspensionlab {
namespace kinematics {

struct BushingParameters {
    // Translational stiffness [N/mm]
    double k_uca_fwd_radial = 5000.0;
    double k_uca_fwd_axial  = 15000.0;
    double k_uca_aft_radial = 5000.0;
    double k_uca_aft_axial  = 15000.0;

    double k_lca_fwd_radial = 8000.0;
    double k_lca_fwd_axial  = 25000.0;
    double k_lca_aft_radial = 8000.0;
    double k_lca_aft_axial  = 25000.0;

    double k_tierod_axial   = 35000.0; // Steering rack/tierod axial stiffness

    // Lumped elastokinematic compliance coefficients (deg / kN, mm / kN)
    double c_camber_fy = 0.12;   // deg / kN
    double c_toe_fy    = 0.08;   // deg / kN (lateral force steer)
    double c_toe_fx    = -0.05;  // deg / kN (brake steer)
    double c_toe_mz    = 0.15;   // deg / (kN*m) (aligning torque steer)
    double c_y_fy      = 0.25;   // mm / kN
    double c_x_fx      = 0.15;   // mm / kN
};

struct WheelCornerLoads {
    double Fx_N = 0.0;  // Longitudinal force (+ = drive, - = brake)
    double Fy_N = 0.0;  // Lateral force (+ = cornering left/outboard)
    double Fz_N = 0.0;  // Normal vertical load (+ = compression)
    double Mx_Nm = 0.0; // Overturning moment
    double My_Nm = 0.0; // Rolling resistance moment
    double Mz_Nm = 0.0; // Aligning torque
};

struct CompliantDeflection {
    double delta_camber_deg = 0.0;
    double delta_toe_deg = 0.0;
    double delta_caster_deg = 0.0;
    double delta_x_mm = 0.0;
    double delta_y_mm = 0.0;
    double delta_z_mm = 0.0;
};

class BushingComplianceModel {
public:
    explicit BushingComplianceModel(BushingParameters params = BushingParameters{})
        : params_(params), enabled_(false) {}

    void set_enabled(bool enabled) { enabled_ = enabled; }
    bool is_enabled() const { return enabled_; }

    void set_parameters(const BushingParameters& params) { params_ = params; }
    const BushingParameters& parameters() const { return params_; }

    // Solve coupled elastokinematic equilibrium under corner loads
    CompliantDeflection solve_deflections(const WheelCornerLoads& loads) const;

private:
    BushingParameters params_;
    bool enabled_;
};

} // namespace kinematics
} // namespace suspensionlab
