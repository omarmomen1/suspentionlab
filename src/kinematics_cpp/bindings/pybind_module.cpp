#include <pybind11/pybind11.h>
#include <pybind11/eigen.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

#include "suspension_kinematics/solver.hpp"
#include "suspension_kinematics/topologies.hpp"
#include "suspension_kinematics/exceptions.hpp"
#include "suspension_kinematics/hardpoint_validation.hpp"
#include "suspension_kinematics/bushing_compliance.hpp"

#include <cmath>
#include <memory>
#include <cstring>

namespace py = pybind11;
using namespace suspensionlab::kinematics;

namespace {

std::map<std::string, Eigen::Vector3d> convert_hardpoints_dict(const py::dict& hardpoints_dict) {
    std::map<std::string, Eigen::Vector3d> hardpoints;
    for (auto item : hardpoints_dict) {
        std::string key = py::cast<std::string>(item.first);
        if (py::isinstance<py::array_t<double>>(item.second)) {
            py::array_t<double> arr = py::cast<py::array_t<double>>(item.second);
            if (arr.size() != 3) {
                throw std::invalid_argument("Hardpoint array must have 3 elements [x, y, z]");
            }
            auto req = arr.request();
            double* ptr = static_cast<double*>(req.ptr);
            hardpoints[key] = Eigen::Vector3d(ptr[0], ptr[1], ptr[2]);
        } else if (py::isinstance<py::list>(item.second) || py::isinstance<py::tuple>(item.second)) {
            auto lst = py::cast<std::vector<double>>(item.second);
            if (lst.size() != 3) {
                throw std::invalid_argument("Hardpoint list/tuple must have 3 elements [x, y, z]");
            }
            hardpoints[key] = Eigen::Vector3d(lst[0], lst[1], lst[2]);
        }
    }
    return hardpoints;
}

std::unique_ptr<ISuspensionTopology> create_topology(
    const std::string& topology_type,
    const std::map<std::string, Eigen::Vector3d>& hardpoints)
{
    if (topology_type == "double_wishbone") {
        return std::make_unique<DoubleWishbone>(hardpoints);
    } else if (topology_type == "macpherson") {
        return std::make_unique<MacPherson>(hardpoints);
    } else {
        throw InvalidTopologyException("Unsupported topology: " + topology_type);
    }
}

} // namespace

py::dict py_validate_hardpoints(
    const std::string& topology_type,
    const py::dict& hardpoints_dict,
    double tire_radius = 0.33)
{
    std::map<std::string, Eigen::Vector3d> hardpoints = convert_hardpoints_dict(hardpoints_dict);
    ValidationReport rep;
    if (topology_type == "double_wishbone") {
        rep = HardpointValidator::validate_double_wishbone(hardpoints, tire_radius);
    } else if (topology_type == "macpherson") {
        rep = HardpointValidator::validate_macpherson(hardpoints, tire_radius);
    } else {
        throw InvalidTopologyException("Unsupported topology: " + topology_type);
    }

    py::dict out;
    out["is_valid"] = rep.is_valid;
    out["errors"] = rep.errors;
    out["warnings"] = rep.warnings;
    out["diagnostics"] = rep.diagnostics;
    return out;
}

py::dict py_solve_single_corner(
    const std::string& topology_type,
    const py::dict& hardpoints_dict,
    double dz_mm,
    double roll_deg = 0.0,
    double steer_deg = 0.0,
    double pitch_deg = 0.0,
    double tire_radius = 0.33,
    bool compliance_mode = false,
    double Fx_N = 0.0,
    double Fy_N = 0.0,
    double Fz_N = 0.0,
    double Mx_Nm = 0.0,
    double My_Nm = 0.0,
    double Mz_Nm = 0.0,
    double cg_height_mm = 350.0,
    double wheelbase_mm = 2600.0,
    double brake_bias = 0.60,
    double drive_bias = 1.00)
{
    std::map<std::string, Eigen::Vector3d> hardpoints = convert_hardpoints_dict(hardpoints_dict);
    std::unique_ptr<ISuspensionTopology> topology = create_topology(topology_type, hardpoints);

    Eigen::Vector3d wc_init = hardpoints.at("wheel_center");
    int n_states = topology->num_states();
    Eigen::VectorXd guess = Eigen::VectorXd::Zero(n_states);
    guess(0) = wc_init(0);
    guess(1) = wc_init(1);
    guess(2) = wc_init(2);
    guess(3) = 1.0; // e0 = 1.0 (identity quaternion)

    if (topology_type == "macpherson") {
        Eigen::Vector3d strut_vec = hardpoints.at("chassis_strut_top") - hardpoints.at("upright_strut_mount");
        guess(7) = strut_vec.norm();
    }

    auto eval_f = [&topology](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
        topology->evaluate_constraints(x, f);
    };
    auto eval_j = [&topology](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
        topology->evaluate_jacobian(x, j);
    };

    NewtonRaphsonSolver solver;

    // Continuation warm-up ramp from neutral to (dz_mm, roll_deg, steer_deg, pitch_deg)
    const int warm_steps = std::max(1, static_cast<int>(std::max(std::abs(dz_mm) / 10.0, std::abs(steer_deg) / 2.0)));
    for (int step = 1; step <= warm_steps; ++step) {
        double factor = static_cast<double>(step) / static_cast<double>(warm_steps);
        double cur_z = dz_mm * factor;
        topology->set_target_inputs(cur_z, roll_deg * factor, steer_deg * factor, pitch_deg * factor);
        guess(2) = wc_init(2) + cur_z;
        auto warm_res = solver.solve(eval_f, eval_j, guess);
        if (warm_res.status == NewtonRaphsonSolver::SolverResult::CONVERGED) {
            guess = warm_res.state;
        }
    }

    topology->set_target_inputs(dz_mm, roll_deg, steer_deg, pitch_deg);
    NewtonRaphsonSolver::Result result = solver.solve(eval_f, eval_j, guess);

    // Differentiable motion ratio micro-step evaluation
    double spring_len_nom = topology->get_spring_length(result.state);
    
    // Evaluate at dz + 0.01 mm for accurate analytical tangent MR
    double mr = 0.0;
    {
        topology->set_target_inputs(dz_mm + 0.01, roll_deg, steer_deg, pitch_deg);
        NewtonRaphsonSolver::Result res_pert = solver.solve(eval_f, eval_j, result.state);
        if (res_pert.status == NewtonRaphsonSolver::SolverResult::CONVERGED) {
            double spring_len_pert = topology->get_spring_length(res_pert.state);
            mr = std::abs((spring_len_pert - spring_len_nom) / 0.01);
        }
        // Reset target
        topology->set_target_inputs(dz_mm, roll_deg, steer_deg, pitch_deg);
    }

    std::map<std::string, double> kin = topology->calculate_kinematics(
        result.state, tire_radius, spring_len_nom, 0.0, cg_height_mm, wheelbase_mm, brake_bias, drive_bias);
    kin["motion_ratio"] = mr;

    // Apply elastokinematic compliance if enabled
    CompliantDeflection def;
    if (compliance_mode) {
        BushingComplianceModel compliance_model;
        compliance_model.set_enabled(true);
        WheelCornerLoads loads;
        loads.Fx_N = Fx_N;
        loads.Fy_N = Fy_N;
        loads.Fz_N = Fz_N;
        loads.Mx_Nm = Mx_Nm;
        loads.My_Nm = My_Nm;
        loads.Mz_Nm = Mz_Nm;
        def = compliance_model.solve_deflections(loads);

        kin["camber"] += def.delta_camber_deg;
        kin["toe"]    += def.delta_toe_deg;
        kin["caster"] += def.delta_caster_deg;
        kin["track_change"] += def.delta_y_mm;
        kin["wheelbase_change"] += def.delta_x_mm;
    }

    py::dict out;
    for (const auto& kv : kin) {
        out[kv.first.c_str()] = kv.second;
    }
    out["wheel_travel_mm"] = dz_mm;
    out["converged"] = (result.status == NewtonRaphsonSolver::SolverResult::CONVERGED);
    out["status"] = NewtonRaphsonSolver::result_to_string(result.status);
    out["residual_norm"] = result.residual_norm;
    out["condition_number"] = result.condition_number;
    out["iterations"] = result.iterations;
    out["compliance_enabled"] = compliance_mode;
    out["delta_camber_compliance_deg"] = def.delta_camber_deg;
    out["delta_toe_compliance_deg"]    = def.delta_toe_deg;

    return out;
}

py::dict generate_kinematic_lut(
    const std::string& topology_type,
    const py::dict& hardpoints_dict,
    py::array_t<double, py::array::c_style | py::array::forcecast> heave_range,
    py::array_t<double, py::array::c_style | py::array::forcecast> roll_range,
    double tire_radius = 0.33,
    bool compliance_mode = false,
    double Fx_N = 0.0,
    double Fy_N = 0.0,
    double Fz_N = 0.0,
    double Mx_Nm = 0.0,
    double My_Nm = 0.0,
    double Mz_Nm = 0.0,
    double cg_height_mm = 350.0,
    double wheelbase_mm = 2600.0,
    double brake_bias = 0.60,
    double drive_bias = 1.00)
{
    std::map<std::string, Eigen::Vector3d> hardpoints = convert_hardpoints_dict(hardpoints_dict);

    auto heave_buf = heave_range.request();
    double* heave_ptr = static_cast<double*>(heave_buf.ptr);
    size_t n_points = heave_buf.shape[0];

    std::vector<double> camber_out(n_points);
    std::vector<double> toe_out(n_points);
    std::vector<double> caster_out(n_points);
    std::vector<double> kpi_out(n_points);
    std::vector<double> track_change_out(n_points);
    std::vector<double> wheelbase_change_out(n_points);
    std::vector<double> scrub_radius_out(n_points);
    std::vector<double> mechanical_trail_out(n_points);
    std::vector<double> ic_y_out(n_points);
    std::vector<double> ic_z_out(n_points);
    std::vector<double> rc_z_out(n_points);
    std::vector<double> ic_sv_x_out(n_points);
    std::vector<double> ic_sv_z_out(n_points);
    std::vector<double> anti_dive_out(n_points);
    std::vector<double> anti_squat_out(n_points);
    std::vector<double> anti_lift_out(n_points);
    std::vector<double> jacking_force_coeff_out(n_points);
    std::vector<double> motion_ratio_out(n_points);
    std::vector<double> spring_length_out(n_points);
    std::vector<double> heave_z_out(n_points);
    std::vector<bool>   converged_out(n_points);
    std::vector<std::string> status_out(n_points);
    std::vector<double> quaternion_norm_error_out(n_points, 0.0);

    {
        py::gil_scoped_release release;

        std::unique_ptr<ISuspensionTopology> topology = create_topology(topology_type, hardpoints);
        NewtonRaphsonSolver solver;

        int n_states = topology->num_states();
        Eigen::VectorXd guess = Eigen::VectorXd::Zero(n_states);
        Eigen::Vector3d wc_init = hardpoints.at("wheel_center");
        guess(0) = wc_init(0);
        guess(1) = wc_init(1);
        guess(2) = wc_init(2);
        guess(3) = 1.0; // e0 = 1, e1=e2=e3=0

        if (topology_type == "macpherson") {
            Eigen::Vector3d strut_vec = hardpoints.at("chassis_strut_top") - hardpoints.at("upright_strut_mount");
            guess(7) = strut_vec.norm();
        }

        Eigen::Vector4d prev_quaternion = guess.segment<4>(3);
        double prev_spring = -1.0;

        BushingComplianceModel compliance_model;
        if (compliance_mode) {
            compliance_model.set_enabled(true);
        }
        WheelCornerLoads loads;
        loads.Fx_N = Fx_N; loads.Fy_N = Fy_N; loads.Fz_N = Fz_N;
        loads.Mx_Nm = Mx_Nm; loads.My_Nm = My_Nm; loads.Mz_Nm = Mz_Nm;
        CompliantDeflection def = compliance_model.solve_deflections(loads);

        auto eval_f = [&topology](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
            topology->evaluate_constraints(x, f);
        };
        auto eval_j = [&topology](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
            topology->evaluate_jacobian(x, j);
        };

        // Warm-up continuation from neutral (dz = 0) to first point heave_ptr[0]
        if (n_points > 0) {
            double z_first = heave_ptr[0];
            const int warm_steps = std::max(5, static_cast<int>(std::abs(z_first) / 5.0));
            for (int w = 1; w <= warm_steps; ++w) {
                double z_ramp = z_first * static_cast<double>(w) / static_cast<double>(warm_steps);
                topology->set_target_inputs(z_ramp, 0.0, 0.0, 0.0);
                guess(2) = wc_init(2) + z_ramp;
                auto warm_res = solver.solve(eval_f, eval_j, guess);
                if (warm_res.status == NewtonRaphsonSolver::SolverResult::CONVERGED) {
                    guess = warm_res.state;
                }
            }
        }

        for (size_t i = 0; i < n_points; ++i) {
            double heave = heave_ptr[i];
            topology->set_target_inputs(heave, 0.0, 0.0, 0.0);

            NewtonRaphsonSolver::Result result = solver.solve(eval_f, eval_j, guess);
            Eigen::VectorXd state = result.state;
            converged_out[i] = (result.status == NewtonRaphsonSolver::SolverResult::CONVERGED);
            status_out[i] = NewtonRaphsonSolver::result_to_string(result.status);

            // Quaternion normalization discipline & sign continuity (Step 10)
            if (state.size() >= 7) {
                Eigen::Vector4d q = state.segment<4>(3);
                double qnorm_err = std::abs(q.squaredNorm() - 1.0);
                quaternion_norm_error_out[i] = qnorm_err;
                if (q.norm() > 1e-12) {
                    q.normalize();
                }
                // Handle q and -q equivalence: prevent sign flip discontinuity
                if (q.dot(prev_quaternion) < 0.0) {
                    q = -q;
                }
                state.segment<4>(3) = q;
                prev_quaternion = q;
            }

            double dz_step = (i > 0) ? (heave_ptr[i] - heave_ptr[i-1]) : 0.0;
            std::map<std::string, double> kin = topology->calculate_kinematics(
                state, tire_radius, prev_spring, dz_step, cg_height_mm, wheelbase_mm, brake_bias, drive_bias);

            // Apply compliance offsets if enabled
            if (compliance_mode) {
                kin["camber"] += def.delta_camber_deg;
                kin["toe"]    += def.delta_toe_deg;
                kin["caster"] += def.delta_caster_deg;
                kin["track_change"] += def.delta_y_mm;
                kin["wheelbase_change"] += def.delta_x_mm;
            }

            camber_out[i] = kin["camber"];
            toe_out[i]    = kin["toe"];
            caster_out[i] = kin["caster"];
            kpi_out[i]    = kin["kpi"];
            track_change_out[i]     = kin["track_change"];
            wheelbase_change_out[i] = kin["wheelbase_change"];
            scrub_radius_out[i]     = kin["scrub_radius"];
            mechanical_trail_out[i] = kin["mechanical_trail"];
            ic_y_out[i]   = kin["ic_y"];
            ic_z_out[i]   = kin["ic_z"];
            rc_z_out[i]   = kin["rc_z"];
            ic_sv_x_out[i] = kin["ic_sv_x"];
            ic_sv_z_out[i] = kin["ic_sv_z"];
            anti_dive_out[i]  = kin["anti_dive_pct"];
            anti_squat_out[i] = kin["anti_squat_pct"];
            anti_lift_out[i]  = kin["anti_lift_pct"];
            jacking_force_coeff_out[i] = kin["jacking_force_coeff"];
            spring_length_out[i] = kin["spring_length"];
            heave_z_out[i]       = kin["heave_z"];

            prev_spring = kin["spring_length"];
            guess = state; // Continuation warm-start
        }

        // Motion ratio derivative calculation
        motion_ratio_out[0] = 0.0;
        for (size_t i = 1; i < n_points; ++i) {
            double dz = heave_z_out[i] - heave_z_out[i-1];
            if (std::abs(dz) > 1e-9) {
                motion_ratio_out[i] = std::abs(spring_length_out[i] - spring_length_out[i-1]) / std::abs(dz);
            } else {
                motion_ratio_out[i] = motion_ratio_out[i-1];
            }
        }
        if (n_points > 1) {
            motion_ratio_out[0] = motion_ratio_out[1];
        }
    }

    auto vec_to_numpy = [](const std::vector<double>& vec) {
        py::array_t<double> arr({vec.size()}, {sizeof(double)});
        std::memcpy(arr.mutable_data(), vec.data(), vec.size() * sizeof(double));
        return arr;
    };

    py::dict results;
    results["wheel_travel_mm"]       = vec_to_numpy(heave_z_out);
    results["camber_deg"]            = vec_to_numpy(camber_out);
    results["toe_deg"]               = vec_to_numpy(toe_out);
    results["caster_deg"]            = vec_to_numpy(caster_out);
    results["kpi_deg"]               = vec_to_numpy(kpi_out);
    results["track_change_mm"]       = vec_to_numpy(track_change_out);
    results["wheelbase_change_mm"]   = vec_to_numpy(wheelbase_change_out);
    results["scrub_radius_mm"]       = vec_to_numpy(scrub_radius_out);
    results["mechanical_trail_mm"]   = vec_to_numpy(mechanical_trail_out);
    results["ic_y_mm"]               = vec_to_numpy(ic_y_out);
    results["ic_z_mm"]               = vec_to_numpy(ic_z_out);
    results["roll_center_height_mm"] = vec_to_numpy(rc_z_out);
    results["ic_sv_x_mm"]            = vec_to_numpy(ic_sv_x_out);
    results["ic_sv_z_mm"]            = vec_to_numpy(ic_sv_z_out);
    results["anti_dive_pct"]         = vec_to_numpy(anti_dive_out);
    results["anti_squat_pct"]        = vec_to_numpy(anti_squat_out);
    results["anti_lift_pct"]         = vec_to_numpy(anti_lift_out);
    results["jacking_force_coeff"]   = vec_to_numpy(jacking_force_coeff_out);
    results["motion_ratio"]          = vec_to_numpy(motion_ratio_out);
    results["spring_length_mm"]      = vec_to_numpy(spring_length_out);
    results["converged"]             = py::cast(converged_out);
    results["status"]                = py::cast(status_out);
    results["quaternion_norm_error"] = vec_to_numpy(quaternion_norm_error_out);
    
    return results;
}

PYBIND11_MODULE(kinematics_core, m) {
    m.doc() = "Authoritative production C++ suspension multibody kinematics engine (SuspensionLab PRO)";
    
    py::register_exception<KinematicDivergenceException>(m, "KinematicDivergenceError");
    py::register_exception<InvalidTopologyException>(m, "InvalidTopologyError");
    py::register_exception<InvalidHardpointsException>(m, "InvalidHardpointsError");
    py::register_exception<LineSearchFailureException>(m, "LineSearchFailureError");
    py::register_exception<IllConditionedJacobianException>(m, "IllConditionedJacobianError");
    py::register_exception<OutOfDomainException>(m, "OutOfDomainError");

    m.def("validate_hardpoints", &py_validate_hardpoints,
          "Validates geometry and bounds of suspension hardpoints",
          py::arg("topology_type"),
          py::arg("hardpoints"),
          py::arg("tire_radius") = 0.33);

    m.def("solve_single_corner", &py_solve_single_corner,
          "Solves suspension kinematics for a single operating point",
          py::arg("topology_type"),
          py::arg("hardpoints"),
          py::arg("dz_mm"),
          py::arg("roll_deg") = 0.0,
          py::arg("steer_deg") = 0.0,
          py::arg("pitch_deg") = 0.0,
          py::arg("tire_radius") = 0.33,
          py::arg("compliance_mode") = false,
          py::arg("Fx_N") = 0.0,
          py::arg("Fy_N") = 0.0,
          py::arg("Fz_N") = 0.0,
          py::arg("Mx_Nm") = 0.0,
          py::arg("My_Nm") = 0.0,
          py::arg("Mz_Nm") = 0.0,
          py::arg("cg_height_mm") = 350.0,
          py::arg("wheelbase_mm") = 2600.0,
          py::arg("brake_bias") = 0.60,
          py::arg("drive_bias") = 1.00);

    m.def("generate_kinematic_lut", &generate_kinematic_lut, 
          "Generates a high-precision kinematic lookup table along a sweep with continuation",
          py::arg("topology_type"), 
          py::arg("hardpoints"), 
          py::arg("heave_range"), 
          py::arg("roll_range"), 
          py::arg("tire_radius") = 0.33,
          py::arg("compliance_mode") = false,
          py::arg("Fx_N") = 0.0,
          py::arg("Fy_N") = 0.0,
          py::arg("Fz_N") = 0.0,
          py::arg("Mx_Nm") = 0.0,
          py::arg("My_Nm") = 0.0,
          py::arg("Mz_Nm") = 0.0,
          py::arg("cg_height_mm") = 350.0,
          py::arg("wheelbase_mm") = 2600.0,
          py::arg("brake_bias") = 0.60,
          py::arg("drive_bias") = 1.00);

    m.def("version", []() { return "kinematics-core-v3.0-authoritative-cpp20"; });
    m.def("build_hash", []() { return "eigen-3.4.0-simd-x86_64"; });
}
