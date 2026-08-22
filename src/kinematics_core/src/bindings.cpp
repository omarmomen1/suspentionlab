/**
 * bindings.cpp
 * ============
 * SuspensionLab — pybind11 Python bindings for kinematics_core.
 *
 * Exposes:
 *   kinematics_core.HardpointSet      — from_raw() + from_dict()
 *   kinematics_core.KinematicPoint    — named-field output struct
 *   kinematics_core.KinematicsCurves  — list of KinematicPoint
 *   kinematics_core.KinematicsSolver  — .solve() / .solve_single()
 *
 * Python usage:
 *   import kinematics_core as kc
 *
 *   hp = kc.HardpointSet.from_dict({
 *       "UWI_fwd": [-50, 80, 300], "UWI_aft": [50, 80, 300],
 *       "UWO":     [  0, 650, 295],
 *       "LWI_fwd": [-80, 80, 155], "LWI_aft": [80, 80, 155],
 *       "LWO":     [  0, 720, 145],
 *       "TRI":     [  0, 150, 220], "TRO": [-15, 710, 205],
 *       "WC":      [  0, 760, 220], "CP":  [  0, 760,   0],
 *       "PRI":     [-20, 300, 390], "PRO": [-15, 690, 250],
 *   })
 *   solver = kc.KinematicsSolver(hp)
 *   curves = solver.solve(-80.0, 80.0, 33)
 *   for pt in curves.points:
 *       print(pt.wheel_travel_mm, pt.camber_deg, pt.roll_center_height_mm)
 */

#include "hardpoints.hpp"
#include "kinematics_solver.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/eigen.h>

namespace py = pybind11;
using namespace suspensionlab;

// Helper: extract a 3-element list/tuple from a py::object into Eigen::Vector3d
static Eigen::Vector3d to_vec3(const py::object& obj) {
    auto lst = obj.cast<std::vector<double>>();
    if (lst.size() != 3)
        throw std::invalid_argument("Each hardpoint must be a list/tuple of 3 floats [x, y, z].");
    return Eigen::Vector3d{lst[0], lst[1], lst[2]};
}

PYBIND11_MODULE(kinematics_core, m) {
    m.doc() = R"pbdoc(
        kinematics_core
        ---------------
        C++ kinematic constraint solver for double-wishbone suspension.

        Uses Newton–Raphson on 5 rigid-link distance constraints to propagate
        the full corner kinematics (camber, toe, RC height, MR, …) as a function
        of wheel travel.

        Coordinate system
        -----------------
          X : forward  (positive toward front of car)
          Y : outboard (positive away from vehicle centreline)
          Z : up       (positive upward)

        Units
        -----
          Hardpoint inputs : mm
          Angle outputs    : degrees
          Length outputs   : mm
    )pbdoc";

    // ── HardpointSet ──────────────────────────────────────────────────────
    py::class_<HardpointSet>(m, "HardpointSet", R"pbdoc(
        Container for all hardpoint coordinates defining one suspension corner.
        Use HardpointSet.from_dict() to construct from a Python dictionary.
    )pbdoc")
        .def_static("from_raw",
            [](py::object UWI_fwd, py::object UWI_aft, py::object UWO,
               py::object LWI_fwd, py::object LWI_aft, py::object LWO,
               py::object TRI,     py::object TRO,
               py::object WC,      py::object CP,
               py::object PRI,     py::object PRO) {
                return HardpointSet::from_raw(
                    to_vec3(UWI_fwd), to_vec3(UWI_aft), to_vec3(UWO),
                    to_vec3(LWI_fwd), to_vec3(LWI_aft), to_vec3(LWO),
                    to_vec3(TRI),     to_vec3(TRO),
                    to_vec3(WC),      to_vec3(CP),
                    to_vec3(PRI),     to_vec3(PRO)
                );
            },
            py::arg("UWI_fwd"), py::arg("UWI_aft"), py::arg("UWO"),
            py::arg("LWI_fwd"), py::arg("LWI_aft"), py::arg("LWO"),
            py::arg("TRI"),     py::arg("TRO"),
            py::arg("WC"),      py::arg("CP"),
            py::arg("PRI"),     py::arg("PRO"),
            R"pbdoc(
                Construct from individual hardpoint lists.
                Each argument is a 3-element list [x, y, z] in mm.
            )pbdoc")

        .def_static("from_dict",
            [](py::dict d) {
                auto get = [&](const char* key) -> Eigen::Vector3d {
                    if (!d.contains(key))
                        throw std::invalid_argument(
                            std::string("Missing hardpoint key: ") + key);
                    return to_vec3(d[key]);
                };
                return HardpointSet::from_raw(
                    get("UWI_fwd"), get("UWI_aft"), get("UWO"),
                    get("LWI_fwd"), get("LWI_aft"), get("LWO"),
                    get("TRI"),     get("TRO"),
                    get("WC"),      get("CP"),
                    get("PRI"),     get("PRO")
                );
            },
            py::arg("hardpoints"),
            R"pbdoc(
                Construct from a dictionary of hardpoint coordinates.
                Required keys: UWI_fwd, UWI_aft, UWO, LWI_fwd, LWI_aft, LWO,
                               TRI, TRO, WC, CP, PRI, PRO.
                Each value is a list [x, y, z] in mm.
            )pbdoc")

        // Expose neutral wheel centre for reference
        .def_property_readonly("wheel_center_neutral",
            [](const HardpointSet& hp) {
                return std::vector<double>{hp.WC0(0), hp.WC0(1), hp.WC0(2)};
            },
            "Neutral wheel centre [x, y, z] in mm.");

    // ── KinematicPoint ────────────────────────────────────────────────────
    py::class_<KinematicPoint>(m, "KinematicPoint", R"pbdoc(
        Kinematic outputs at one wheel-travel position.
    )pbdoc")
        .def_readonly("wheel_travel_mm",
            &KinematicPoint::wheel_travel_mm,
            "Wheel travel from neutral [mm]. Positive = bump.")
        .def_readonly("camber_deg",
            &KinematicPoint::camber_deg,
            "Camber angle [deg]. Positive = top of wheel tilts outboard.")
        .def_readonly("toe_deg",
            &KinematicPoint::toe_deg,
            "Toe angle [deg]. Positive = toe-out.")
        .def_readonly("caster_deg",
            &KinematicPoint::caster_deg,
            "Caster angle from kingpin axis in side view [deg]. Positive = rearward tilt.")
        .def_readonly("kpi_deg",
            &KinematicPoint::kpi_deg,
            "Kingpin inclination (KPI) in front view [deg]. Positive = top inboard.")
        .def_readonly("track_change_mm",
            &KinematicPoint::track_change_mm,
            "Change in track width (Y position of WC) from neutral [mm].")
        .def_readonly("wheelbase_change_mm",
            &KinematicPoint::wheelbase_change_mm,
            "Change in wheelbase (X position of WC) from neutral [mm].")
        .def_readonly("roll_center_height_mm",
            &KinematicPoint::roll_center_height_mm,
            "Geometric roll-centre height above ground [mm].")
        .def_readonly("motion_ratio",
            &KinematicPoint::motion_ratio,
            "Motion ratio = |Δspring| / |Δwheel| [-]. Zero on first step.")
        .def_readonly("scrub_radius_mm",
            &KinematicPoint::scrub_radius_mm,
            "Scrub radius: lateral offset of CP from steering-axis ground point [mm].")
        .def_readonly("converged",
            &KinematicPoint::converged,
            "True if Newton–Raphson converged to tolerance < 1e-8 mm².")
        .def("__repr__", [](const KinematicPoint& pt) {
            return "<KinematicPoint dz=" + std::to_string(pt.wheel_travel_mm)
                 + " mm camber=" + std::to_string(pt.camber_deg)
                 + " deg RC=" + std::to_string(pt.roll_center_height_mm) + " mm>";
        });

    // ── KinematicsCurves ──────────────────────────────────────────────────
    py::class_<KinematicsCurves>(m, "KinematicsCurves", R"pbdoc(
        Collection of KinematicPoint objects from a wheel-travel sweep.
        Access individual points via .points.
    )pbdoc")
        .def_readonly("points", &KinematicsCurves::points,
            "List of KinematicPoint, one per wheel-travel step.")
        .def("__len__", [](const KinematicsCurves& c) { return c.points.size(); })
        .def("to_dict", [](const KinematicsCurves& c) {
            // Build per-channel lists for convenient numpy conversion
            std::vector<double> dz, camber, toe, caster, kpi, track,
                                wb, rc, mr, scrub;
            std::vector<bool> conv;
            for (const auto& p : c.points) {
                dz.push_back(p.wheel_travel_mm);
                camber.push_back(p.camber_deg);
                toe.push_back(p.toe_deg);
                caster.push_back(p.caster_deg);
                kpi.push_back(p.kpi_deg);
                track.push_back(p.track_change_mm);
                wb.push_back(p.wheelbase_change_mm);
                rc.push_back(p.roll_center_height_mm);
                mr.push_back(p.motion_ratio);
                scrub.push_back(p.scrub_radius_mm);
                conv.push_back(p.converged);
            }
            py::dict out;
            out["wheel_travel_mm"]       = dz;
            out["camber_deg"]            = camber;
            out["toe_deg"]               = toe;
            out["caster_deg"]            = caster;
            out["kpi_deg"]               = kpi;
            out["track_change_mm"]       = track;
            out["wheelbase_change_mm"]   = wb;
            out["roll_center_height_mm"] = rc;
            out["motion_ratio"]          = mr;
            out["scrub_radius_mm"]       = scrub;
            out["converged"]             = conv;
            return out;
        }, "Convert to a dict of lists keyed by channel name.");

    // ── KinematicsSolver ─────────────────────────────────────────────────
    py::class_<KinematicsSolver>(m, "KinematicsSolver", R"pbdoc(
        Double-wishbone kinematic constraint solver.

        Solves 5 rigid-link distance equations via Newton–Raphson with
        central-FD Jacobian and ColPivHouseholderQR linear solve.
        Warm-starts each step from the previous solution.
    )pbdoc")
        .def(py::init<const HardpointSet&>(), py::arg("hardpoints"),
             "Construct the solver for a given corner.")

        .def("solve", &KinematicsSolver::solve,
             py::arg("z_min_mm"), py::arg("z_max_mm"), py::arg("n_steps") = 33,
             R"pbdoc(
                Sweep wheel travel and return kinematic curves.

                Parameters
                ----------
                z_min_mm : float  Droop limit (negative, e.g. -80.0) [mm]
                z_max_mm : float  Bump  limit (positive, e.g.  80.0) [mm]
                n_steps  : int    Number of evaluation points (default 33)

                Returns
                -------
                KinematicsCurves
             )pbdoc")

        .def("solve_single", &KinematicsSolver::solve_single,
             py::arg("dz_mm"),
             R"pbdoc(
                Solve at a single wheel-travel value.

                Parameters
                ----------
                dz_mm : float  Wheel travel from neutral [mm]

                Returns
                -------
                KinematicPoint  (motion_ratio will be 0 — use solve() for MR)
             )pbdoc");
}
