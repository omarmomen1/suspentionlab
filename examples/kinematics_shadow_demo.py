import numpy as np
try:
    import suspensionlab_kinematics as sk
except ImportError:
    print("Error: suspensionlab_kinematics not installed. Run 'pip install ./src/kinematics_cpp'")
    exit(1)

def main():
    print("--- SuspensionLab Kinematics Shadow Mode Demo ---")
    
    # Generic double wishbone hardpoints (F1/LMP style)
    # Units in meters
    hardpoints = {
        "chassis_upper_front": np.array([ 0.2, 0.4, 0.4]),
        "chassis_upper_rear":  np.array([-0.2, 0.4, 0.4]),
        "chassis_lower_front": np.array([ 0.2, 0.2, 0.2]),
        "chassis_lower_rear":  np.array([-0.2, 0.2, 0.2]),
        "upright_upper":       np.array([ 0.0, 0.7, 0.45]),
        "upright_lower":       np.array([ 0.0, 0.7, 0.15]),
        "upright_tie_rod":     np.array([ 0.1, 0.7, 0.25]),
        "chassis_tie_rod":     np.array([ 0.1, 0.3, 0.25]),
        "wheel_center":        np.array([ 0.0, 0.75, 0.3])
    }

    # Sweep from -50mm to +50mm heave in 100 steps
    heave_range = np.linspace(-0.05, 0.05, 100)
    roll_range = np.zeros_like(heave_range) # Ignored in Phase 1

    print("Generating High-Resolution Look-Up Table (LUT)...")
    try:
        lut = sk.generate_kinematic_lut("double_wishbone", hardpoints, heave_range, roll_range)
        
        print("\nLUT Generated Successfully!")
        print(f"Evaluated {len(heave_range)} points.")
        print(f"Camber at -50mm Heave: {lut['camber'][0]:.3f} deg")
        print(f"Camber at   0mm Heave: {lut['camber'][50]:.3f} deg")
        print(f"Camber at +50mm Heave: {lut['camber'][-1]:.3f} deg")
        
    except Exception as e:
        print(f"Kinematics solver failed: {e}")

if __name__ == "__main__":
    main()
