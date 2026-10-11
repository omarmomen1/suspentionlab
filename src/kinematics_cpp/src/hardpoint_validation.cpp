#include "suspension_kinematics/hardpoint_validation.hpp"
#include <cmath>

namespace suspensionlab {
namespace kinematics {

ValidationReport HardpointValidator::validate_double_wishbone(
    const std::map<std::string, Eigen::Vector3d>& hardpoints,
    double tire_radius)
{
    ValidationReport report;

    const std::vector<std::string> required = {
        "chassis_upper_front", "chassis_upper_rear", "chassis_lower_front", "chassis_lower_rear",
        "upright_upper", "upright_lower", "upright_tie_rod", "chassis_tie_rod", "wheel_center"
    };

    for (const auto& key : required) {
        if (hardpoints.find(key) == hardpoints.end()) {
            report.is_valid = false;
            report.errors.push_back("Missing required hardpoint: " + key);
        }
    }

    if (!report.is_valid) {
        return report;
    }

    const auto& uwi_f = hardpoints.at("chassis_upper_front");
    const auto& uwi_r = hardpoints.at("chassis_upper_rear");
    const auto& lwi_f = hardpoints.at("chassis_lower_front");
    const auto& lwi_r = hardpoints.at("chassis_lower_rear");
    const auto& uwo   = hardpoints.at("upright_upper");
    const auto& lwo   = hardpoints.at("upright_lower");
    const auto& tri   = hardpoints.at("chassis_tie_rod");
    const auto& tro   = hardpoints.at("upright_tie_rod");
    const auto& wc    = hardpoints.at("wheel_center");

    // 1. Tire radius check (m to mm)
    double r_tire_mm = tire_radius * 1000.0;
    if (r_tire_mm < 150.0 || r_tire_mm > 600.0) {
        report.warnings.push_back("Tire radius outside typical automotive range [150mm, 600mm]: " + std::to_string(r_tire_mm) + " mm");
    }
    if (tire_radius <= 0.0) {
        report.is_valid = false;
        report.errors.push_back("Tire radius must be strictly positive");
    }

    // 2. Inboard base separation
    double uwi_base = (uwi_f - uwi_r).norm();
    double lwi_base = (lwi_f - lwi_r).norm();
    report.diagnostics["uwi_inboard_base_mm"] = uwi_base;
    report.diagnostics["lwi_inboard_base_mm"] = lwi_base;

    if (uwi_base < 30.0) {
        report.is_valid = false;
        report.errors.push_back("Upper wishbone inboard pivot separation too small (< 30 mm): " + std::to_string(uwi_base));
    }
    if (lwi_base < 30.0) {
        report.is_valid = false;
        report.errors.push_back("Lower wishbone inboard pivot separation too small (< 30 mm): " + std::to_string(lwi_base));
    }

    // 3. Vertical wishbone separation (inboard and outboard)
    double inboard_v_sep = ((uwi_f + uwi_r) * 0.5 - (lwi_f + lwi_r) * 0.5).norm();
    double upright_kingpin_length = (uwo - lwo).norm();
    report.diagnostics["inboard_wishbone_separation_mm"] = inboard_v_sep;
    report.diagnostics["upright_kingpin_length_mm"] = upright_kingpin_length;

    if (inboard_v_sep < 30.0) {
        report.is_valid = false;
        report.errors.push_back("Inboard vertical separation between upper and lower wishbone too small (< 30 mm): " + std::to_string(inboard_v_sep));
    }
    if (upright_kingpin_length < 50.0) {
        report.is_valid = false;
        report.errors.push_back("Upright ball joint separation (kingpin span) too small (< 50 mm): " + std::to_string(upright_kingpin_length));
    }

    // 4. Member lengths
    double l_uca_f = (uwo - uwi_f).norm();
    double l_uca_r = (uwo - uwi_r).norm();
    double l_lca_f = (lwo - lwi_f).norm();
    double l_lca_r = (lwo - lwi_r).norm();
    double l_tie   = (tro - tri).norm();

    report.diagnostics["l_uca_fwd_mm"] = l_uca_f;
    report.diagnostics["l_uca_aft_mm"] = l_uca_r;
    report.diagnostics["l_lca_fwd_mm"] = l_lca_f;
    report.diagnostics["l_lca_aft_mm"] = l_lca_r;
    report.diagnostics["l_tierod_mm"]  = l_tie;

    auto check_len = [&](const std::string& name, double len) {
        if (len < 50.0 || len > 1500.0) {
            report.is_valid = false;
            report.errors.push_back(name + " length outside valid physical bounds [50mm, 1500mm]: " + std::to_string(len));
        }
    };
    check_len("Upper wishbone front leg", l_uca_f);
    check_len("Upper wishbone rear leg", l_uca_r);
    check_len("Lower wishbone front leg", l_lca_f);
    check_len("Lower wishbone rear leg", l_lca_r);
    check_len("Tie rod", l_tie);

    // 5. Track width / lateral offset sanity
    double half_track = std::abs(wc(1));
    report.diagnostics["half_track_mm"] = half_track;
    if (half_track < 300.0 || half_track > 1500.0) {
        report.warnings.push_back("Half track width outside typical automotive envelope [300mm, 1500mm]: " + std::to_string(half_track));
    }

    // 6. Upright triangle non-collinearity
    Eigen::Vector3d v_up = uwo - lwo;
    Eigen::Vector3d v_tie = tro - lwo;
    Eigen::Vector3d cross = v_up.cross(v_tie);
    if (cross.norm() < 100.0) { // area of triangle < 50 mm^2
        report.warnings.push_back("Steering arm / upright geometry nearly collinear with kingpin axis");
    }

    return report;
}

ValidationReport HardpointValidator::validate_macpherson(
    const std::map<std::string, Eigen::Vector3d>& hardpoints,
    double tire_radius)
{
    ValidationReport report;

    const std::vector<std::string> required = {
        "chassis_lower_front", "chassis_lower_rear", "chassis_strut_top",
        "upright_lower", "upright_strut_mount", "upright_tie_rod", "chassis_tie_rod", "wheel_center"
    };

    for (const auto& key : required) {
        if (hardpoints.find(key) == hardpoints.end()) {
            report.is_valid = false;
            report.errors.push_back("Missing required hardpoint: " + key);
        }
    }

    if (!report.is_valid) {
        return report;
    }

    const auto& lwi_f = hardpoints.at("chassis_lower_front");
    const auto& lwi_r = hardpoints.at("chassis_lower_rear");
    const auto& strut_top = hardpoints.at("chassis_strut_top");
    const auto& lwo   = hardpoints.at("upright_lower");
    const auto& strut_mount = hardpoints.at("upright_strut_mount");
    const auto& tri   = hardpoints.at("chassis_tie_rod");
    const auto& tro   = hardpoints.at("upright_tie_rod");
    const auto& wc    = hardpoints.at("wheel_center");

    if (tire_radius <= 0.0) {
        report.is_valid = false;
        report.errors.push_back("Tire radius must be strictly positive");
    }

    double lwi_base = (lwi_f - lwi_r).norm();
    report.diagnostics["lwi_inboard_base_mm"] = lwi_base;
    if (lwi_base < 30.0) {
        report.is_valid = false;
        report.errors.push_back("Lower control arm inboard pivot separation too small (< 30 mm): " + std::to_string(lwi_base));
    }

    double strut_length = (strut_top - strut_mount).norm();
    report.diagnostics["nominal_strut_length_mm"] = strut_length;
    if (strut_length < 150.0 || strut_length > 1200.0) {
        report.is_valid = false;
        report.errors.push_back("MacPherson strut length outside valid bounds [150mm, 1200mm]: " + std::to_string(strut_length));
    }

    double l_lca_f = (lwo - lwi_f).norm();
    double l_lca_r = (lwo - lwi_r).norm();
    double l_tie   = (tro - tri).norm();
    report.diagnostics["l_lca_fwd_mm"] = l_lca_f;
    report.diagnostics["l_lca_aft_mm"] = l_lca_r;
    report.diagnostics["l_tierod_mm"]  = l_tie;

    if (l_lca_f < 50.0 || l_lca_f > 1500.0 || l_lca_r < 50.0 || l_lca_r > 1500.0) {
        report.is_valid = false;
        report.errors.push_back("Lower control arm length outside physical bounds [50mm, 1500mm]");
    }
    if (l_tie < 50.0 || l_tie > 1500.0) {
        report.is_valid = false;
        report.errors.push_back("Tie rod length outside physical bounds [50mm, 1500mm]");
    }

    return report;
}

} // namespace kinematics
} // namespace suspensionlab
