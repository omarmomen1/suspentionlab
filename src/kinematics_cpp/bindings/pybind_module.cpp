#include <pybind11/pybind11.h>
#include <pybind11/eigen.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <iostream>

#include "suspension_kinematics/solver.hpp"
#include "suspension_kinematics/topologies.hpp"
#include "suspension_kinematics/exceptions.hpp"

namespace py = pybind11;
using namespace suspensionlab::kinematics;

std::map<std::string, py::array_t<double>> generate_kinematic_lut(
    const std::string& topology_type,
    const py::dict& hardpoints_dict,
    py::array_t<double, py::array::c_style | py::array::forcecast> heave_range,
    py::array_t<double, py::array::c_style | py::array::forcecast> roll_range) 
{
    // Manual conversion
    std::map<std::string, Eigen::Vector3d> hardpoints;
    for (auto item : hardpoints_dict) {
        std::string key = py::cast<std::string>(item.first);
        py::array_t<double> arr = py::cast<py::array_t<double>>(item.second);
        if (arr.size() != 3) {
            throw std::runtime_error("Hardpoint array must have 3 elements");
        }
        auto req = arr.request();
        double* ptr = static_cast<double*>(req.ptr);
        hardpoints[key] = Eigen::Vector3d(ptr[0], ptr[1], ptr[2]);
    }

    // Input arrays
    auto heave_buf = heave_range.request();
    double* heave_ptr = static_cast<double*>(heave_buf.ptr);
    size_t n_points = heave_buf.shape[0];

    // Initialize output vectors
    std::vector<double> camber_out(n_points);
    std::vector<double> z_out(n_points);
    std::vector<double> toe_out(n_points);
    std::vector<double> caster_out(n_points);
    std::vector<double> kpi_out(n_points);
    std::vector<double> scrub_radius_out(n_points);
    std::vector<double> mechanical_trail_out(n_points);
    std::vector<double> ic_y_out(n_points);
    std::vector<double> ic_z_out(n_points);
    std::vector<double> rc_z_out(n_points);
    std::vector<double> motion_ratio_out(n_points);

    {
        // RAII Release GIL
        py::gil_scoped_release release;

        try {
            std::unique_ptr<ISuspensionTopology> topology;
            if (topology_type == "double_wishbone") {
                topology = std::make_unique<DoubleWishbone>(hardpoints);
            } else if (topology_type == "macpherson") {
                topology = std::make_unique<MacPherson>(hardpoints);
            } else {
                throw InvalidTopologyException("Unsupported topology: " + topology_type);
            }

            NewtonRaphsonSolver solver;

            // Initial guess: x,y,z from wheel center, quaternion = identity
            int n_states = topology->num_states();
            Eigen::VectorXd guess = Eigen::VectorXd::Zero(n_states);
            Eigen::Vector3d wc_init = hardpoints.at("wheel_center");
            guess(0) = wc_init(0);
            guess(1) = wc_init(1);
            guess(2) = wc_init(2);
            guess(3) = 1.0; // e0 = 1, e1=e2=e3=0
            
            // For MacPherson, d_strut initial guess is length of strut tube
            if (topology_type == "macpherson") {
                Eigen::Vector3d strut_vec = hardpoints.at("chassis_strut_top") - hardpoints.at("upright_strut_mount");
                guess(7) = strut_vec.norm();
            }

            for (size_t i = 0; i < n_points; ++i) {
                double heave = heave_ptr[i];
                
                // Update target
                if (auto* dw = dynamic_cast<DoubleWishbone*>(topology.get())) {
                    dw->set_heave_target(wc_init(2) + heave);
                } else if (auto* mp = dynamic_cast<MacPherson*>(topology.get())) {
                    mp->set_heave_target(wc_init(2) + heave);
                }

                // Bind evaluation functions
                auto eval_f = [&topology](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
                    topology->evaluate_constraints(x, f);
                };
                auto eval_j = [&topology](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
                    topology->evaluate_jacobian(x, j);
                };

                // Solve
                Eigen::VectorXd state = solver.solve(eval_f, eval_j, guess);
                
                // Extract kinematics
                double tire_radius = 0.3; // Can be parameterized later
                std::map<std::string, double> kin = topology->calculate_kinematics(state, tire_radius);

                camber_out[i] = kin["camber"];
                toe_out[i] = kin["toe"];
                caster_out[i] = kin["caster"];
                kpi_out[i] = kin["kpi"];
                scrub_radius_out[i] = kin["scrub_radius"];
                mechanical_trail_out[i] = kin["mechanical_trail"];
                ic_y_out[i] = kin["ic_y"];
                ic_z_out[i] = kin["ic_z"];
                rc_z_out[i] = kin["rc_z"];
                motion_ratio_out[i] = kin["motion_ratio"];
                z_out[i] = kin["heave_z"];

                // Update guess for next iteration (warm start)
                guess = state;
            }
        } catch (const std::exception& e) {
            std::cerr << "C++ EXCEPTION CAUGHT: " << e.what() << std::endl;
            throw; // Rethrow to let Pybind handle it
        } catch (...) {
            std::cerr << "UNKNOWN C++ EXCEPTION CAUGHT" << std::endl;
            throw;
        }
    }
    
    // Copy vectors to py::array_t
    auto vec_to_numpy = [](const std::vector<double>& vec) {
        py::array_t<double> arr({vec.size()}, {sizeof(double)});
        std::memcpy(arr.mutable_data(), vec.data(), vec.size() * sizeof(double));
        return arr;
    };

    std::map<std::string, py::array_t<double>> results;
    results["camber"] = vec_to_numpy(camber_out);
    results["toe"] = vec_to_numpy(toe_out);
    results["caster"] = vec_to_numpy(caster_out);
    results["kpi"] = vec_to_numpy(kpi_out);
    results["scrub_radius"] = vec_to_numpy(scrub_radius_out);
    results["mechanical_trail"] = vec_to_numpy(mechanical_trail_out);
    results["ic_y"] = vec_to_numpy(ic_y_out);
    results["ic_z"] = vec_to_numpy(ic_z_out);
    results["rc_z"] = vec_to_numpy(rc_z_out);
    results["motion_ratio"] = vec_to_numpy(motion_ratio_out);
    results["heave_z"] = vec_to_numpy(z_out);
    
    return results;
}

PYBIND11_MODULE(suspensionlab_kinematics, m) {
    m.doc() = "Native C++ suspension kinematics engine";
    
    py::register_exception<KinematicDivergenceException>(m, "KinematicDivergenceError");
    py::register_exception<InvalidTopologyException>(m, "InvalidTopologyError");

    m.def("generate_kinematic_lut", &generate_kinematic_lut, 
          "Generates a kinematic lookup table for a given suspension topology",
          py::arg("topology_type"), py::arg("hardpoints"), py::arg("heave_range"), py::arg("roll_range"));
}
