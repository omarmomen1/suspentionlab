import json
import urllib.request
import urllib.error

API_BASE = "https://suspensionlab-api.vercel.app"

def request(endpoint, method="GET", data=None, token=None):
    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except:
            return e.code, {"error": err_body}

def main():
    print("=== LIVE PRODUCTION VERIFICATION ===")
    
    # 0. Login
    print("\n--- 0. Authentication ---")
    status, login_res = request("/api/v1/auth/login", method="POST", data={
        "email": "testuser@suspensionlab.com",
        "password": "SuspensionLab2026!#"
    })
    print(f"Login status: {status}")
    token = login_res.get("token") or login_res.get("access_token")
    if not token:
        print(f"FAILED LOGIN: {login_res}")
        return
    print(f"Authenticated as testuser@suspensionlab.com. Token prefix: {token[:12]}...")

    # 1. Custom Track Architect (2,220m)
    print("\n--- 1. Custom Track Architect (2,220m) ---")
    # Default 6 segments from UI:
    # Straight 400m, Right Corner 300m (R=120m), Straight 500m, Left Corner 350m (R=150m), Straight 400m, Hairpin 270m (R=45m)
    # Total = 400 + 300 + 500 + 350 + 400 + 270 = 2,220m
    custom_segments = [
        {"type": "Straight", "length_m": 400, "radius_m": 0, "banking_deg": 0, "grade_pct": 0},
        {"type": "Right Corner", "length_m": 300, "radius_m": 120, "banking_deg": 0, "grade_pct": 0},
        {"type": "Straight", "length_m": 500, "radius_m": 0, "banking_deg": 0, "grade_pct": 0},
        {"type": "Left Corner", "length_m": 350, "radius_m": 150, "banking_deg": 0, "grade_pct": 0},
        {"type": "Straight", "length_m": 400, "radius_m": 0, "banking_deg": 0, "grade_pct": 0},
        {"type": "Hairpin", "length_m": 270, "radius_m": 45, "banking_deg": 0, "grade_pct": 0},
    ]
    gt3_vehicle = {
        "total_mass": 1285.0,
        "wheelbase": 2.45,
        "cog_dist_front": 1.37,
        "h_cog": 0.44,
        "max_power_kw": 395.0,
        "cl_base": 2.2,
        "cd_base": 0.72,
        "frontal_area": 2.1,
        "tire_mu": 1.65,
        "front_spring_rate": 140.0,
        "rear_spring_rate": 170.0,
        "front_arb": 45.0,
        "rear_arb": 30.0,
        "front_rc_height": 0.045,
        "rear_rc_height": 0.075,
        "static_rh_front_mm": 55.0,
        "static_rh_rear_mm": 70.0,
    }
    status, custom_res = request("/api/v1/lap-sim/simulate", method="POST", data={
        "mode": "custom",
        "segments": custom_segments,
        "is_closed": True,
        "vehicle": gt3_vehicle,
    }, token=token)
    print(f"Custom Track Sim status: {status}")
    if status == 200:
        print(f"  Lap Time: {custom_res.get('lap_time_s')} s")
        print(f"  Avg Speed: {custom_res.get('avg_speed_kmh')} km/h")
        print(f"  Max Speed: {custom_res.get('max_speed_kmh')} km/h")
        print(f"  Front LLTD: {custom_res.get('front_lltd_pct')} %")
    else:
        print(f"  ERROR: {custom_res}")

    # 2. MoTeC Telemetry CSV Opportunity Finder & Correlation
    print("\n--- 2. MoTeC Opportunity Finder & Correlation ---")
    # Generate realistic sample telemetry for Spa
    time_s = [round(i * 0.1, 2) for i in range(200)]
    # speed around 120-220 km/h with a corner at idx 50-80
    speed_ms = []
    lat_g = []
    for i in range(200):
        if 50 <= i <= 80:
            speed_ms.append(28.0) # ~100 km/h
            lat_g.append(1.8)
        elif 120 <= i <= 150:
            speed_ms.append(22.0) # ~80 km/h
            lat_g.append(2.1)
        else:
            speed_ms.append(55.0) # ~200 km/h
            lat_g.append(0.1)

    status, csv_res = request("/api/v1/lap-sim/simulate", method="POST", data={
        "mode": "csv",
        "telemetry": {
            "time_s": time_s,
            "speed_ms": speed_ms,
            "lat_g": lat_g,
        },
        "is_closed": True,
        "vehicle": gt3_vehicle,
    }, token=token)
    print(f"CSV Sim status: {status}")
    if status == 200:
        print(f"  Lap Time: {csv_res.get('lap_time_s')} s")
        print(f"  Corner Opportunities count: {len(csv_res.get('corner_opportunities', []))}")
        for op in csv_res.get('corner_opportunities', []):
            print(f"    Turn {op.get('corner_id')} ({op.get('s_start_m')}m-{op.get('s_end_m')}m): Sim Apex={op.get('v_sim_apex_kmh')} km/h, Driver Apex={op.get('v_driver_apex_kmh')} km/h, Time Loss={op.get('time_loss_s')}s, Bottleneck={op.get('bottleneck')}")
    else:
        print(f"  ERROR: {csv_res}")

    # Check /correlation compare-model
    status, corr_res = request("/api/v1/telemetry/compare-model", method="POST", data={
        "model_type": "quarter_car"
    }, token=token)
    print(f"Correlation compare-model status: {status}")
    if status == 200:
        print(f"  Overall R²: {corr_res.get('overall_correlation_r2')}")
        for ch in corr_res.get("channels", []):
            print(f"    Channel: {ch.get('channel_key')} ({ch.get('name')}): R²={ch.get('metrics', {}).get('r_squared')}, RMSE={ch.get('metrics', {}).get('rmse')} {ch.get('unit')}")
    else:
        print(f"  ERROR: {corr_res}")

    # 3. Plank Bottoming Torture Case
    print("\n--- 3. Plank Bottoming Torture Case (22mm RH, 50 N/mm Spring) ---")
    bottoming_vehicle = dict(gt3_vehicle)
    bottoming_vehicle["static_rh_front_mm"] = 22.0
    bottoming_vehicle["front_spring_rate"] = 50.0

    status, bot_res = request("/api/v1/lap-sim/simulate", method="POST", data={
        "track": "spa",
        "is_closed": True,
        "vehicle": bottoming_vehicle,
    }, token=token)
    print(f"Bottoming Sim status: {status}")
    if status == 200:
        print(f"  Lap Time: {bot_res.get('lap_time_s')} s")
        print(f"  Min Front RH: {bot_res.get('min_rh_front_mm')} mm")
        print(f"  Min Rear RH: {bot_res.get('min_rh_rear_mm')} mm")
        print(f"  Bottoming Events Count: {bot_res.get('bottoming_events_count')}")
        print(f"  Top Speed: {bot_res.get('max_speed_kmh')} km/h")
    else:
        print(f"  ERROR: {bot_res}")

    # 4. FSAE Auto-Preset (295 kg / 80 kW)
    print("\n--- 4. FSAE Auto-Preset (295 kg / 80 kW) ---")
    fsae_vehicle = {
        "total_mass": 295.0,
        "wheelbase": 1.55,
        "cog_dist_front": 0.82,
        "h_cog": 0.28,
        "max_power_kw": 80.0,
        "cl_base": 3.4,
        "cd_base": 1.15,
        "frontal_area": 1.05,
        "tire_mu": 1.75,
        "front_spring_rate": 45.0,
        "rear_spring_rate": 55.0,
        "front_arb": 12.0,
        "rear_arb": 15.0,
        "static_rh_front_mm": 35.0,
        "static_rh_rear_mm": 40.0,
    }
    status, fsae_res = request("/api/v1/lap-sim/simulate", method="POST", data={
        "track": "fsae_endurance",
        "is_closed": True,
        "vehicle": fsae_vehicle,
    }, token=token)
    print(f"FSAE Sim status: {status}")
    if status == 200:
        print(f"  Lap Time: {fsae_res.get('lap_time_s')} s")
        print(f"  Avg Speed: {fsae_res.get('avg_speed_kmh')} km/h")
        print(f"  Top Speed: {fsae_res.get('max_speed_kmh')} km/h")
        print(f"  Front LLTD: {fsae_res.get('front_lltd_pct')} %")
    else:
        print(f"  ERROR: {fsae_res}")

    # 5. AI Engineer Endpoint
    print("\n--- 5. AI Engineer Grounding & Reasoning ---")
    status, ai_res = request("/api/v1/ai/chat", method="POST", data={
        "problem": "Spa GT3 front understeer saturation and 13.9 mm front ride height drops through Kemmel, what setup changes solve this and what is predicted delta on lap time and fs?"
    }, token=token)
    print(f"AI Engineer Chat status: {status}")
    if status == 200:
        print(f"  Workflow: {ai_res.get('workflow')}")
        print(f"  Setup Summary: {ai_res.get('setup_summary')}")
        for p in ai_res.get("best_feasible", []):
            print(f"    Param Change: {p.get('parameter')}: {p.get('current_value')} -> {p.get('recommended_value')} ({p.get('change_pct')}%)")
        for eff in ai_res.get("predicted_effects", []):
            print(f"    Predicted Effect: {eff.get('metric')}: {eff.get('baseline')} -> {eff.get('predicted')} {eff.get('unit')}")
    else:
        print(f"  ERROR: {ai_res}")

if __name__ == "__main__":
    main()
