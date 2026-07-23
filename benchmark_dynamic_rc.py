import numpy as np
import matplotlib.pyplot as plt
import time
from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver, SuspensionLUT
import suspensionlab_kinematics as sk

def create_f1_front_suspension():
    return {
        "chassis_upper_front": np.array([0.2, 0.4, 0.3]),
        "chassis_upper_rear": np.array([-0.2, 0.4, 0.28]),
        "chassis_lower_front": np.array([0.2, 0.2, 0.1]),
        "chassis_lower_rear": np.array([-0.2, 0.2, 0.12]),
        "upright_upper": np.array([0.0, 0.75, 0.35]),
        "upright_lower": np.array([0.0, 0.72, 0.15]),
        "upright_tie_rod": np.array([0.1, 0.72, 0.25]),
        "chassis_tie_rod": np.array([0.1, 0.2, 0.25]),
        "wheel_center": np.array([0.0, 0.8, 0.3])
    }

def create_f1_rear_suspension():
    return {
        "chassis_upper_front": np.array([0.2, 0.4, 0.3]),
        "chassis_upper_rear": np.array([-0.2, 0.4, 0.28]),
        "chassis_lower_front": np.array([0.2, 0.2, 0.1]),
        "chassis_lower_rear": np.array([-0.2, 0.2, 0.12]),
        "upright_upper": np.array([0.0, 0.75, 0.35]),
        "upright_lower": np.array([0.0, 0.72, 0.15]),
        "upright_tie_rod": np.array([-0.1, 0.72, 0.25]),
        "chassis_tie_rod": np.array([-0.1, 0.2, 0.25]),
        "wheel_center": np.array([0.0, 0.8, 0.3])
    }

def run_benchmark():
    print("Generating Kinematic LUTs...")
    heave_range = np.linspace(-0.1, 0.1, 50)
    rack_range = np.linspace(-0.0, 0.0, 1) # unused
    
    t0 = time.time()
    lut_f_dict = sk.generate_kinematic_lut("double_wishbone", create_f1_front_suspension(), heave_range, rack_range)
    lut_r_dict = sk.generate_kinematic_lut("double_wishbone", create_f1_rear_suspension(), heave_range, rack_range)
    print(f"LUT Generation Time: {(time.time() - t0)*1000:.2f} ms")
    
    lut_f = SuspensionLUT(lut_f_dict)
    lut_r = SuspensionLUT(lut_r_dict)
    
    # Dynamic 3D RC Model (Strict Path)
    p_dynamic = HandlingParams(
        m_s=1000.0,
        m_uf=100.0,
        m_ur=100.0,
        kinematics_lut_f=lut_f,
        kinematics_lut_r=lut_r,
        K_spring_f=60000.0,
        K_spring_r=80000.0,
        K_arb_f=30000.0,
        K_arb_r=15000.0
    )
    
    # Step Steer Maneuver
    def step_steer(t):
        if t < 1.0:
            return 0.0
        return np.clip((t - 1.0) * 0.1, 0.0, 0.05)
        
    def throttle(t): return 0.2
    def brake(t): return 0.0
    
    
    print("Running Dynamic RC Model...")
    t2 = time.time()
    res_dynamic = simulate_maneuver(p_dynamic, 30.0, step_steer, throttle, brake, duration=5.0)
    print(f"Dynamic Model Time: {(time.time() - t2)*1000:.2f} ms")
    
    # Plotting
    plt.plot(res_dynamic["time"], res_dynamic["v_y"], label="Dynamic RC")
    plt.title("Lateral Velocity (m/s)")
    plt.legend()
    plt.grid()
    
    plt.tight_layout()
    plt.savefig("benchmark_results.png")
    print("Benchmark complete. Results saved to benchmark_results.png")

if __name__ == "__main__":
    run_benchmark()
