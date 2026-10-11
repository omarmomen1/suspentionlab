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

class InvalidHardpointsException : public std::invalid_argument {
public:
    explicit InvalidHardpointsException(const std::string& message)
        : std::invalid_argument(message) {}
};

class LineSearchFailureException : public std::runtime_error {
public:
    explicit LineSearchFailureException(const std::string& message)
        : std::runtime_error(message) {}
};

class IllConditionedJacobianException : public std::runtime_error {
public:
    explicit IllConditionedJacobianException(const std::string& message)
        : std::runtime_error(message) {}
};

class OutOfDomainException : public std::out_of_range {
public:
    explicit OutOfDomainException(const std::string& message)
        : std::out_of_range(message) {}
};

} // namespace kinematics
} // namespace suspensionlab
