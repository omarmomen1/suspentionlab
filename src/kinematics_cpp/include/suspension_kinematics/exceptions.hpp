#pragma once
#include <stdexcept>
#include <string>

namespace suspensionlab {
namespace kinematics {

class KinematicDivergenceException : public std::runtime_error {
public:
    explicit KinematicDivergenceException(const std::string& message)
        : std::runtime_error(message) {}
};

class InvalidTopologyException : public std::runtime_error {
public:
    explicit InvalidTopologyException(const std::string& message)
        : std::runtime_error(message) {}
};

} // namespace kinematics
} // namespace suspensionlab
