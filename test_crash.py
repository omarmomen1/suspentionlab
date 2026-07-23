import numpy as np
import suspensionlab_kinematics as sk
import sys

print('Loaded module', flush=True)

hardpoints = {
    'chassis_upper_front': np.array([ 0.2, 0.4, 0.4]),
    'chassis_upper_rear':  np.array([-0.2, 0.4, 0.4]),
    'chassis_lower_front': np.array([ 0.2, 0.2, 0.2]),
    'chassis_lower_rear':  np.array([-0.2, 0.2, 0.2]),
    'upright_upper':       np.array([ 0.0, 0.7, 0.45]),
    'upright_lower':       np.array([ 0.0, 0.7, 0.15]),
    'upright_tie_rod':     np.array([ 0.1, 0.7, 0.25]),
    'chassis_tie_rod':     np.array([ 0.1, 0.3, 0.25]),
    'wheel_center':        np.array([ 0.0, 0.75, 0.3])
}

print('Calling function...', flush=True)
try:
    lut = sk.generate_kinematic_lut('double_wishbone', hardpoints, np.array([0.0]), np.array([0.0]))
    print('SUCCESS 0mm', flush=True)
except Exception as e:
    print('FAILED:', e, flush=True)
