#include <gtest/gtest.h>
#include "suspension_kinematics/solver.hpp"
#include "suspension_kinematics/topologies.hpp"
#include "suspension_kinematics/hardpoint_validation.hpp"
#include "suspension_kinematics/bushing_compliance.hpp"
#include "suspension_kinematics/exceptions.hpp"

#include <cmath>
#include <map>

using namespace suspensionlab::kinematics;

// Helper: standard right-front corner double wishbone hardpoints
std::map<std::string, Eigen::Vector3d> create_default_dw_hardpoints() {
    std::map<std::string, Eigen::Vector3d> hp;
    hp["chassis_upper_front"] = Eigen::Vector3d(-50.0,  80.0, 300.0);
    hp["chassis_upper_rear"]  = Eigen::Vector3d( 50.0,  80.0, 300.0);
    hp["upright_upper"]       = Eigen::Vector3d(  0.0, 650.0, 295.0);

    hp["chassis_lower_front"] = Eigen::Vector3d(-80.0,  80.0, 155.0);
    hp["chassis_lower_rear"]  = Eigen::Vector3d( 80.0,  80.0, 155.0);
    hp["upright_lower"]       = Eigen::Vector3d(  0.0, 720.0, 145.0);

    hp["chassis_tie_rod"]     = Eigen::Vector3d(  0.0, 150.0, 220.0);
    hp["upright_tie_rod"]     = Eigen::Vector3d(-15.0, 710.0, 205.0);

    hp["wheel_center"]        = Eigen::Vector3d(  0.0, 760.0, 220.0);
    hp["pushrod_chassis"]     = Eigen::Vector3d(-20.0, 300.0, 390.0);
    hp["pushrod_upright"]     = Eigen::Vector3d(-15.0, 690.0, 250.0);
    return hp;
}

std::map<std::string, Eigen::Vector3d> create_default_mp_hardpoints() {
    std::map<std::string, Eigen::Vector3d> hp;
    hp["chassis_lower_front"]  = Eigen::Vector3d(-80.0,  80.0, 155.0);
    hp["chassis_lower_rear"]   = Eigen::Vector3d( 80.0,  80.0, 155.0);
    hp["chassis_strut_top"]    = Eigen::Vector3d(  0.0, 550.0, 650.0);
    hp["upright_lower"]        = Eigen::Vector3d(  0.0, 720.0, 145.0);
    hp["upright_strut_mount"]  = Eigen::Vector3d(  0.0, 620.0, 350.0);
    hp["chassis_tie_rod"]      = Eigen::Vector3d(  0.0, 150.0, 220.0);
    hp["upright_tie_rod"]      = Eigen::Vector3d(-15.0, 710.0, 205.0);
    hp["wheel_center"]         = Eigen::Vector3d(  0.0, 760.0, 220.0);
    return hp;
}

// ── 1. Solver Fundamentals ───────────────────────────────────────────────────

TEST(NewtonRaphsonTest, SimpleQuadratic) {
    NewtonRaphsonSolver solver;
    
    // Solve x^2 - 4 = 0. Roots at x=2, x=-2
    auto eval_f = [](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
        f.resize(1);
        f(0) = x(0) * x(0) - 4.0;
    };
    
    auto eval_j = [](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
        j.resize(1, 1);
        j(0, 0) = 2.0 * x(0);
    };
    
    Eigen::VectorXd guess(1);
    guess(0) = 3.0;
    
    NewtonRaphsonSolver::Result res = solver.solve(eval_f, eval_j, guess);
    EXPECT_EQ(res.status, NewtonRaphsonSolver::SolverResult::CONVERGED);
    EXPECT_NEAR(res.state(0), 2.0, 1e-6);
}

TEST(NewtonRaphsonTest, DivergenceDetection) {
    NewtonRaphsonSolver solver;
    
    // Solve e^x = -1 (no real solution)
    auto eval_f = [](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
        f.resize(1);
        f(0) = std::exp(x(0)) + 1.0;
    };
    
    auto eval_j = [](const Eigen::VectorXd& x, Eigen::MatrixXd& j) {
        j.resize(1, 1);
        j(0, 0) = std::exp(x(0));
    };
    
    Eigen::VectorXd guess(1);
    guess(0) = 0.0;
    
    NewtonRaphsonSolver::Result res = solver.solve(eval_f, eval_j, guess);
    EXPECT_NE(res.status, NewtonRaphsonSolver::SolverResult::CONVERGED);
}

TEST(NewtonRaphsonTest, SingularJacobianDetection) {
    NewtonRaphsonSolver solver;

    // Singular 2x2 system
    auto eval_f = [](const Eigen::VectorXd& x, Eigen::VectorXd& f) {
        f.resize(2);
        f(0) = x(0) + x(1) - 2.0;
        f(1) = 2.0 * x(0) + 2.0 * x(1) - 4.0;
    };

    auto eval_j = [](const Eigen::VectorXd&, Eigen::MatrixXd& j) {
        j.resize(2, 2);
        j << 1.0, 1.0,
             2.0, 2.0; // Rank 1
    };

    Eigen::VectorXd guess(2);
    guess << 0.0, 0.0;

    NewtonRaphsonSolver::Result res = solver.solve(eval_f, eval_j, guess);
    EXPECT_EQ(res.status, NewtonRaphsonSolver::SolverResult::SINGULAR_JACOBIAN);
}

// ── 2. Hardpoint Validation ──────────────────────────────────────────────────

TEST(HardpointValidationTest, DoubleWishboneValid) {
    auto hp = create_default_dw_hardpoints();
    ValidationReport rep = HardpointValidator::validate_double_wishbone(hp, 0.33);
    EXPECT_TRUE(rep.is_valid);
    EXPECT_TRUE(rep.errors.empty());
}

TEST(HardpointValidationTest, DoubleWishboneInvalidSeparation) {
    auto hp = create_default_dw_hardpoints();
    // Collapse upper wishbone inboard pivots to same point (degenerate)
    hp["chassis_upper_rear"] = hp["chassis_upper_front"];
    ValidationReport rep = HardpointValidator::validate_double_wishbone(hp, 0.33);
    EXPECT_FALSE(rep.is_valid);
    EXPECT_FALSE(rep.errors.empty());
}

// ── 3. Double Wishbone Kinematics ─────────────────────────────────────────────

TEST(DoubleWishboneTest, NeutralStateKinematics) {
    auto hp = create_default_dw_hardpoints();
    DoubleWishbone dw(hp);
    
    // Initial guess at neutral
    Eigen::VectorXd guess(7);
    guess << 0.0, 760.0, 220.0, 1.0, 0.0, 0.0, 0.0;

    auto eval_f = [&dw](const Eigen::VectorXd& x, Eigen::VectorXd& f) { dw.evaluate_constraints(x, f); };
    auto eval_j = [&dw](const Eigen::VectorXd& x, Eigen::MatrixXd& j) { dw.evaluate_jacobian(x, j); };

    NewtonRaphsonSolver solver;
    NewtonRaphsonSolver::Result res = solver.solve(eval_f, eval_j, guess);
    EXPECT_EQ(res.status, NewtonRaphsonSolver::SolverResult::CONVERGED);

    std::map<std::string, double> kin = dw.calculate_kinematics(res.state, 0.33);
    
    // At neutral, camber and toe should be near nominal (within 1 deg)
    EXPECT_NEAR(kin["camber"], 0.0, 2.0);
    EXPECT_NEAR(kin["toe"], 0.0, 2.0);
    EXPECT_GT(kin["rc_z"], -100.0);
    EXPECT_LT(kin["rc_z"], 200.0);
}

TEST(DoubleWishboneTest, MotionRatioDifferentiability) {
    auto hp = create_default_dw_hardpoints();
    DoubleWishbone dw(hp);

    Eigen::VectorXd guess(7);
    guess << 0.0, 760.0, 220.0, 1.0, 0.0, 0.0, 0.0;
    NewtonRaphsonSolver solver;
    auto eval_f = [&dw](const Eigen::VectorXd& x, Eigen::VectorXd& f) { dw.evaluate_constraints(x, f); };
    auto eval_j = [&dw](const Eigen::VectorXd& x, Eigen::MatrixXd& j) { dw.evaluate_jacobian(x, j); };

    // Solve at nominal dz = 0
    dw.set_heave_target(220.0);
    NewtonRaphsonSolver::Result r0 = solver.solve(eval_f, eval_j, guess);
    double s0 = dw.get_spring_length(r0.state);

    // Perturbations: dz = 0.5, 0.1, 0.01 mm
    dw.set_heave_target(220.0 + 0.5);
    NewtonRaphsonSolver::Result r_050 = solver.solve(eval_f, eval_j, r0.state);
    double mr_050 = std::abs(dw.get_spring_length(r_050.state) - s0) / 0.5;

    dw.set_heave_target(220.0 + 0.1);
    NewtonRaphsonSolver::Result r_010 = solver.solve(eval_f, eval_j, r0.state);
    double mr_010 = std::abs(dw.get_spring_length(r_010.state) - s0) / 0.1;

    dw.set_heave_target(220.0 + 0.01);
    NewtonRaphsonSolver::Result r_001 = solver.solve(eval_f, eval_j, r0.state);
    double mr_001 = std::abs(dw.get_spring_length(r_001.state) - s0) / 0.01;

    // Motion ratio derivative convergence verification (Step 7)
    EXPECT_NEAR(mr_010, mr_001, 0.01);
    EXPECT_NEAR(mr_050, mr_010, 0.05);
    EXPECT_GT(mr_001, 0.2);
    EXPECT_LT(mr_001, 1.5);
}

// ── 4. Bushing Compliance Coupled ─────────────────────────────────────────────

TEST(BushingComplianceTest, CoupledEquilibrium) {
    BushingComplianceModel model;
    EXPECT_FALSE(model.is_enabled());

    WheelCornerLoads loads;
    loads.Fy_N = 3000.0; // 3 kN lateral force
    loads.Fx_N = -2000.0; // 2 kN braking force
    loads.Mz_Nm = 50.0;  // 50 Nm aligning torque

    CompliantDeflection def_rigid = model.solve_deflections(loads);
    EXPECT_DOUBLE_EQ(def_rigid.delta_camber_deg, 0.0);
    EXPECT_DOUBLE_EQ(def_rigid.delta_toe_deg, 0.0);

    model.set_enabled(true);
    CompliantDeflection def_comp = model.solve_deflections(loads);
    EXPECT_GT(def_comp.delta_camber_deg, 0.1);
    EXPECT_NE(def_comp.delta_toe_deg, 0.0);
    EXPECT_GT(def_comp.delta_y_mm, 0.0);
}

// ── 5. MacPherson Strut Kinematics ────────────────────────────────────────────

TEST(MacPhersonTest, NominalSolve) {
    auto hp = create_default_mp_hardpoints();
    MacPherson mp(hp);

    Eigen::VectorXd guess(8);
    guess << 0.0, 760.0, 220.0, 1.0, 0.0, 0.0, 0.0, 350.0;

    auto eval_f = [&mp](const Eigen::VectorXd& x, Eigen::VectorXd& f) { mp.evaluate_constraints(x, f); };
    auto eval_j = [&mp](const Eigen::VectorXd& x, Eigen::MatrixXd& j) { mp.evaluate_jacobian(x, j); };

    NewtonRaphsonSolver solver;
    NewtonRaphsonSolver::Result res = solver.solve(eval_f, eval_j, guess);
    EXPECT_EQ(res.status, NewtonRaphsonSolver::SolverResult::CONVERGED);

    std::map<std::string, double> kin = mp.calculate_kinematics(res.state, 0.33);
    EXPECT_NEAR(kin["camber"], 0.0, 3.0);
    EXPECT_GT(kin["strut_extension"], 100.0);
}
