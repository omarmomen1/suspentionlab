from pydantic import BaseModel
import numpy as np

class Hardpoint3D(BaseModel):
    x: float
    y: float
    z: float

    def to_numpy(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=np.float64)

class DoubleWishboneHardpoints(BaseModel):
    chassis_upper_front: Hardpoint3D
    chassis_upper_rear: Hardpoint3D
    chassis_lower_front: Hardpoint3D
    chassis_lower_rear: Hardpoint3D
    upright_upper: Hardpoint3D
    upright_lower: Hardpoint3D
    upright_tie_rod: Hardpoint3D
    chassis_tie_rod: Hardpoint3D
    wheel_center: Hardpoint3D

    def to_dict_of_arrays(self) -> dict[str, np.ndarray]:
        # BaseModel.dict() is deprecated in pydantic 2.0, using model_dump()
        d = self.model_dump()
        return {k: np.array([v["x"], v["y"], v["z"]], dtype=np.float64) for k, v in d.items()}

class MacPhersonHardpoints(BaseModel):
    chassis_strut_top: Hardpoint3D
    chassis_lower_front: Hardpoint3D
    chassis_lower_rear: Hardpoint3D
    upright_lower: Hardpoint3D
    upright_strut_mount: Hardpoint3D
    upright_tie_rod: Hardpoint3D
    chassis_tie_rod: Hardpoint3D
    wheel_center: Hardpoint3D

    def to_dict_of_arrays(self) -> dict[str, np.ndarray]:
        d = self.model_dump()
        return {k: np.array([v["x"], v["y"], v["z"]], dtype=np.float64) for k, v in d.items()}

def validate_and_build_hardpoints(topology: str, raw_dict: dict) -> dict[str, np.ndarray]:
    """
    Validates a raw dictionary of [x, y, z] lists or arrays into strict 3D hardpoints,
    then returns a dictionary of numpy arrays suitable for the C++ Pybind11 layer.
    """
    # Convert lists/numpy arrays in raw_dict to dicts for Pydantic parsing
    parsed_dict = {}
    for k, v in raw_dict.items():
        if isinstance(v, (list, tuple, np.ndarray)):
            if len(v) != 3:
                raise ValueError(f"Hardpoint {k} must have exactly 3 coordinates.")
            parsed_dict[k] = {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}
        elif isinstance(v, dict):
            parsed_dict[k] = v
        else:
            raise ValueError(f"Unsupported format for hardpoint {k}")

    if topology == "double_wishbone":
        model = DoubleWishboneHardpoints(**parsed_dict)
        return model.to_dict_of_arrays()
    elif topology == "macpherson":
        model = MacPhersonHardpoints(**parsed_dict)
        return model.to_dict_of_arrays()
    else:
        raise ValueError(f"Unsupported topology for validation: {topology}")

def safe_generate_kinematic_lut(topology_type: str, hardpoints: dict, heave_range: np.ndarray, roll_range: np.ndarray) -> dict[str, np.ndarray]:
    """
    Validates hardpoints via Pydantic and then calls the native C++ kinematics engine.
    """
    import suspensionlab_kinematics as sk
    valid_hardpoints = validate_and_build_hardpoints(topology_type, hardpoints)
    return sk.generate_kinematic_lut(topology_type, valid_hardpoints, heave_range, roll_range)
