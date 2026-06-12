import re
import difflib

def generate_diff():
    path = "src/suspensionlab/visualization/telemetry_plots.py"
    with open(path, "r", encoding="utf-8") as f:
        fixed_text = f.read()

    # Revert np.asarray(result.FIELD) * NUMBER -> result.FIELD * NUMBER
    unfixed_text = fixed_text
    fields = [
        "z_r", "z_s", "z_u", "dz_s", "dz_u", "ddz_s", "susp_travel", "tire_defl",
        "tire_load_var", "transmissibility_body", "transmissibility_wheel",
        "bode_magnitude_db", "bode_phase_deg", "z_rf", "z_rr"
    ]
    for field in fields:
        # result.z_s * 1e3
        unfixed_text = re.sub(
            rf'np\.asarray\((result\.{field})\)',
            r'\1',
            unfixed_text
        )
        # float(np.max(result.z_r)) -> result.z_r.max()
        unfixed_text = re.sub(
            rf'float\(np\.max\((result\.{field})\)\)',
            rf'\1.max()',
            unfixed_text
        )
        # float(np.min(result.tire_load_var)) -> result.tire_load_var.min()
        unfixed_text = re.sub(
            rf'float\(np\.min\((result\.{field})\)\)',
            rf'\1.min()',
            unfixed_text
        )

    # Now generate unified diff
    fixed_lines = fixed_text.splitlines(keepends=True)
    unfixed_lines = unfixed_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        unfixed_lines,
        fixed_lines,
        fromfile="telemetry_plots.py",
        tofile="telemetry_plots.py",
        n=3
    )
    
    with open("my_diff.diff", "w", encoding="utf-8") as f:
        f.writelines(diff)

generate_diff()
