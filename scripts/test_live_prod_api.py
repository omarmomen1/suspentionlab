import os
import sys
import json
import hashlib
import requests

API_BASE = "https://suspensionlab-api.vercel.app"

def run_probe():
    session = requests.Session()
    # Login to get JWT
    login_url = f"{API_BASE}/api/v1/auth/login"
    login_resp = session.post(login_url, json={"email": "testuser@suspensionlab.com", "password": "SuspensionLab2026!#"}, timeout=30)
    token = None
    if login_resp.status_code == 200:
        data = login_resp.json()
        token = data.get("token") or data.get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}

    print("================================================================================", flush=True)
    print("LIVE PRODUCTION API AUDIT PROBE: https://suspensionlab-api.vercel.app", flush=True)
    print(f"Auth Token: {'ACQUIRED' if token else 'NONE'}", flush=True)
    print("================================================================================\n", flush=True)

    # -------------------------------------------------------------------------
    # CHECK A: Custom Track (2,220m)
    # -------------------------------------------------------------------------
    print("--- CHECK A: Custom Track (2,220m, 6 Segments, Closed Circuit) ---", flush=True)
    payload_a = {
        "mode": "custom",
        "track": "custom",
        "is_closed": True,
        "segments": [
            {"type": "straight", "length_m": 800, "radius_m": 0, "banking_deg": 0, "grade_pct": 0},
            {"type": "corner", "length_m": 220, "radius_m": 140, "banking_deg": 0, "grade_pct": 0},
            {"type": "straight", "length_m": 450, "radius_m": 0, "banking_deg": 0, "grade_pct": 0},
            {"type": "corner", "length_m": 150, "radius_m": 75, "banking_deg": 0, "grade_pct": 0},
            {"type": "straight", "length_m": 350, "radius_m": 0, "banking_deg": 0, "grade_pct": 0},
            {"type": "corner", "length_m": 250, "radius_m": 110, "banking_deg": 0, "grade_pct": 0}
        ]
    }
    resp_a = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_a, headers=headers, timeout=60)
    print(f"Status Code: {resp_a.status_code}", flush=True)
    if resp_a.status_code == 200:
        data_a = resp_a.json()
        print(f"lap_time_s: {data_a.get('lap_time_s')}", flush=True)
        print(f"avg_speed_kmh: {data_a.get('avg_speed_kmh')}", flush=True)
        print(f"max_speed_kmh: {data_a.get('max_speed_kmh')}", flush=True)
        print(f"sector_times: {json.dumps(data_a.get('sector_times', []))}", flush=True)
    else:
        print(f"Error: {resp_a.text}", flush=True)
    print(flush=True)

    # -------------------------------------------------------------------------
    # CHECK B: CSV Fast vs Slow Driver Trap
    # -------------------------------------------------------------------------
    print("--- CHECK B: CSV Telemetry Corner Opportunities (Fast vs Slow Driver Trap) ---", flush=True)
    t_arr = [round(i * 0.2, 2) for i in range(35)]
    lat_g_arr = [0.0]*10 + [1.8]*15 + [0.0]*10
    v_fast = [48.0]*8 + [42.0, 38.0] + [36.0]*15 + [40.0, 45.0] + [48.0]*8
    v_slow = [48.0]*8 + [38.0, 30.0] + [24.0]*15 + [32.0, 40.0] + [48.0]*8

    payload_b_fast = {
        "mode": "csv",
        "telemetry": {
            "time_s": t_arr,
            "speed_ms": v_fast,
            "lat_g": lat_g_arr
        }
    }
    payload_b_slow = {
        "mode": "csv",
        "telemetry": {
            "time_s": t_arr,
            "speed_ms": v_slow,
            "lat_g": lat_g_arr
        }
    }

    resp_b_fast = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_b_fast, headers=headers, timeout=60)
    resp_b_slow = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_b_slow, headers=headers, timeout=60)

    print(f"Fast Driver Status: {resp_b_fast.status_code}", flush=True)
    if resp_b_fast.status_code == 200:
        opps_fast = resp_b_fast.json().get("corner_opportunities", [])
        print("Fast Driver corner_opportunities:", flush=True)
        print(json.dumps(opps_fast, indent=2), flush=True)
    else:
        print(f"Fast Driver Error: {resp_b_fast.text}", flush=True)

    print(f"Slow Driver Status: {resp_b_slow.status_code}", flush=True)
    if resp_b_slow.status_code == 200:
        opps_slow = resp_b_slow.json().get("corner_opportunities", [])
        print("Slow Driver corner_opportunities:", flush=True)
        print(json.dumps(opps_slow, indent=2), flush=True)
    else:
        print(f"Slow Driver Error: {resp_b_slow.text}", flush=True)
    print(flush=True)

    # -------------------------------------------------------------------------
    # CHECK C: Plank Bottoming (Baseline vs Soft/Low)
    # -------------------------------------------------------------------------
    print("--- CHECK C: Aero Ride Height & Plank Bottoming Sensitivity ---", flush=True)
    payload_c_base = {
        "track": "spa",
        "vehicle": {
            "static_rh_front_mm": 55.0,
            "static_rh_rear_mm": 70.0,
            "k_spring_front_n_m": 140000.0,
            "k_spring_rear_n_m": 160000.0
        }
    }
    payload_c_soft = {
        "track": "spa",
        "vehicle": {
            "static_rh_front_mm": 22.0,
            "static_rh_rear_mm": 30.0,
            "k_spring_front_n_m": 50000.0,
            "k_spring_rear_n_m": 60000.0
        }
    }
    resp_c_base = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_c_base, headers=headers, timeout=60)
    resp_c_soft = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_c_soft, headers=headers, timeout=60)

    print("Baseline Setup (55mm RH, 140 N/mm Spring):", flush=True)
    if resp_c_base.status_code == 200:
        d = resp_c_base.json()
        print(f"  lap_time_s: {d.get('lap_time_s')}", flush=True)
        print(f"  max_speed_kmh: {d.get('max_speed_kmh')}", flush=True)
        print(f"  min_rh_front_mm: {d.get('min_rh_front_mm')}", flush=True)
        print(f"  bottoming_events_count: {d.get('bottoming_events_count')}", flush=True)
    else:
        print(f"  Error: {resp_c_base.text}", flush=True)

    print("Soft/Low Setup (22mm RH, 50 N/mm Spring):", flush=True)
    if resp_c_soft.status_code == 200:
        d = resp_c_soft.json()
        print(f"  lap_time_s: {d.get('lap_time_s')}", flush=True)
        print(f"  max_speed_kmh: {d.get('max_speed_kmh')}", flush=True)
        print(f"  min_rh_front_mm: {d.get('min_rh_front_mm')}", flush=True)
        print(f"  bottoming_events_count: {d.get('bottoming_events_count')}", flush=True)
    else:
        print(f"  Error: {resp_c_soft.text}", flush=True)
    print(flush=True)

    # -------------------------------------------------------------------------
    # CHECK D: FSAE EV on fsae_endurance
    # -------------------------------------------------------------------------
    print("--- CHECK D: Formula SAE EV Preset (295 kg, 80 kW, fsae_endurance) ---", flush=True)
    payload_d = {
        "track": "fsae_endurance",
        "vehicle": {
            "mass_kg": 295.0,
            "max_power_kw": 80.0,
            "wheelbase_m": 1.55,
            "track_front_m": 1.20,
            "track_rear_m": 1.18,
            "cl_total": 2.8,
            "cd_total": 0.85,
            "frontal_area_m2": 1.1,
            "k_spring_front_n_m": 35000.0,
            "k_spring_rear_n_m": 40000.0,
            "k_arb_front_nm_rad": 8000.0,
            "k_arb_rear_nm_rad": 6000.0,
            "mu_0": 1.65,
            "fz_nom_n": 1200.0
        }
    }
    resp_d = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_d, headers=headers, timeout=60)
    print(f"Status Code: {resp_d.status_code}", flush=True)
    if resp_d.status_code == 200:
        d = resp_d.json()
        print(f"lap_time_s: {d.get('lap_time_s')}", flush=True)
        print(f"max_speed_kmh: {d.get('max_speed_kmh')}", flush=True)
        print(f"max_lat_g: {d.get('max_lat_g')}", flush=True)
        print(f"front_lltd_pct: {d.get('front_lltd_pct')}", flush=True)
    else:
        print(f"Error: {resp_d.text}", flush=True)
    print(flush=True)

    # -------------------------------------------------------------------------
    # CHECK E: Spa Front ARB & Monza Brake Bias Sensitivities
    # -------------------------------------------------------------------------
    print("--- CHECK E: Spa Front ARB (10, 42, 95 N/mm) & Monza Brake Bias (45%, 58%, 78%) ---", flush=True)
    print("Spa ARB Sweep:", flush=True)
    for arb in [10000.0, 42000.0, 95000.0]:
        payload_e_arb = {
            "track": "spa",
            "vehicle": {
                "k_arb_front_nm_rad": arb
            }
        }
        resp = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_e_arb, headers=headers, timeout=60)
        if resp.status_code == 200:
            d = resp.json()
            print(f"  Front ARB {arb/1000.0:.0f} kN*m/rad -> lap_time_s: {d.get('lap_time_s')}, front_lltd_pct: {d.get('front_lltd_pct')}%, max_roll_deg: {d.get('max_roll_deg')} deg", flush=True)
        else:
            print(f"  Front ARB {arb} Error: {resp.text}", flush=True)

    print("Monza Brake Bias Sweep:", flush=True)
    for bb in [0.45, 0.58, 0.78]:
        payload_e_bb = {
            "track": "monza",
            "vehicle": {
                "brake_bias_front": bb
            }
        }
        resp = session.post(f"{API_BASE}/api/v1/lap-sim/simulate", json=payload_e_bb, headers=headers, timeout=60)
        if resp.status_code == 200:
            d = resp.json()
            print(f"  Brake Bias {bb*100.0:.0f}% -> lap_time_s: {d.get('lap_time_s')}, max_braking_g: {d.get('max_braking_g')} g", flush=True)
        else:
            print(f"  Brake Bias {bb} Error: {resp.text}", flush=True)
    print(flush=True)

    # -------------------------------------------------------------------------
    # CHECK F: Zero-Cheat Grep & SHA-256 Verification
    # -------------------------------------------------------------------------
    print("--- CHECK F: Zero-Cheat Grep Audit & Tree SHA-256 Parity ---", flush=True)
    lap_sim_src = "src/suspensionlab/physics/lap_sim.py"
    banned_patterns = ["0.0015", "0.085", "c_v_apex - 4.5"]
    with open(lap_sim_src, "r", encoding="utf-8") as f:
        src_code = f.read()

    found_cheats = {}
    for p in banned_patterns:
        count = src_code.count(p)
        found_cheats[p] = count
    print(f"Grep Banned Patterns in {lap_sim_src}:", flush=True)
    for pat, count in found_cheats.items():
        print(f"  Pattern '{pat}': {count} occurrences (Expected: 0)", flush=True)

    files_to_hash = [
        "physics/lap_sim.py",
        "backend/api/routes/lap_sim_routes.py"
    ]
    print("SHA-256 Parity Verification:", flush=True)
    for rel in files_to_hash:
        p1 = os.path.join("src", "suspensionlab", rel)
        p2 = os.path.join("backend_vercel", "src", "suspensionlab", rel)
        h1 = hashlib.sha256(open(p1, "rb").read()).hexdigest()
        h2 = hashlib.sha256(open(p2, "rb").read()).hexdigest()
        match = (h1 == h2)
        print(f"  {rel}:", flush=True)
        print(f"    src/            : {h1}", flush=True)
        print(f"    backend_vercel/ : {h2}", flush=True)
        print(f"    Match           : {match}", flush=True)

    print("\n================================================================================", flush=True)
    print("LIVE PRODUCTION API AUDIT PROBE COMPLETED", flush=True)
    print("================================================================================", flush=True)

if __name__ == "__main__":
    run_probe()
