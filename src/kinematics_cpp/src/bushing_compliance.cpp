#include "suspension_kinematics/bushing_compliance.hpp"

namespace suspensionlab {
namespace kinematics {

CompliantDeflection BushingComplianceModel::solve_deflections(const WheelCornerLoads& loads) const {
    CompliantDeflection def;
    if (!enabled_) {
        return def; // All zeroes in rigid mode
    }

    double fx_kn = loads.Fx_N / 1000.0;
    double fy_kn = loads.Fy_N / 1000.0;
    double fz_kn = loads.Fz_N / 1000.0;
    double mx_knm = loads.Mx_Nm / 1000.0;
    double mz_knm = loads.Mz_Nm / 1000.0;

    // Coupled elastokinematic deflection equations
    def.delta_camber_deg = params_.c_camber_fy * fy_kn + 0.05 * mx_knm;
    def.delta_toe_deg    = params_.c_toe_fy * fy_kn + params_.c_toe_fx * fx_kn + params_.c_toe_mz * mz_knm;
    def.delta_caster_deg = -0.02 * fx_kn;

    def.delta_x_mm = params_.c_x_fx * fx_kn;
    def.delta_y_mm = params_.c_y_fy * fy_kn;
    def.delta_z_mm = 0.05 * fz_kn;

    return def;
}

} // namespace kinematics
} // namespace suspensionlab
