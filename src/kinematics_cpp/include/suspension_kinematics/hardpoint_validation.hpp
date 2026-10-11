#pragma once
#include <Eigen/Dense>
#include <map>
#include <string>
#include <vector>

namespace suspensionlab {
namespace kinematics {

struct ValidationReport {
    bool is_valid = true;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    std::map<std::string, double> diagnostics;

    std::string to_string() const {
        std::string s = is_valid ? "VALID\n" : "INVALID\n";
        for (const auto& err : errors) {
            s += "  [ERROR] " + err + "\n";
        }
        for (const auto& w : warnings) {
            s += "  [WARN]  " + w + "\n";
        }
        return s;
    }
};

class HardpointValidator {
public:
    static ValidationReport validate_double_wishbone(
        const std::map<std::string, Eigen::Vector3d>& hardpoints,
        double tire_radius = 0.33);

    static ValidationReport validate_macpherson(
        const std::map<std::string, Eigen::Vector3d>& hardpoints,
        double tire_radius = 0.33);
};

} // namespace kinematics
} // namespace suspensionlab
