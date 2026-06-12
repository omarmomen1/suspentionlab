from fastapi.testclient import TestClient
from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import Base, engine
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.team import Team
from sqlalchemy.orm import sessionmaker
import uuid

client = TestClient(app)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_test_data():
    db = SessionLocal()
    # Mock user creation
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    # We will bypass the DB for testing, or just mock the dependency `verify_api_key`.
    db.close()
    return user_id, team_id

def test_features():
    user_id, team_id = uuid.uuid4(), uuid.uuid4()
    
    # Mocking the authentication dependencies
    app.dependency_overrides = {}
    from suspensionlab.backend.security.auth import verify_api_key, require_plan
    
    async def mock_require_plan():
        return {
            "user_id": str(user_id),
            "plan": "ENTERPRISE",
            "email": "test@enterprise.com",
            "team_id": str(team_id),
            "onboarding_complete": True
        }
        
    async def mock_verify_api_key():
        return {
            "user_id": str(user_id),
            "plan": "ENTERPRISE",
            "email": "test@enterprise.com",
            "team_id": str(team_id),
            "onboarding_complete": True
        }
        
    # We have to patch the factory return
    def mock_require_plan_factory(min_plan: str):
        return mock_require_plan
        
    app.dependency_overrides[verify_api_key] = mock_verify_api_key
    # Wait, require_plan is a factory. It is evaluated at startup.
    # So we must override the actual result of the factory if we want to mock it.
    # Alternatively, we can patch `verify_api_key` which is internally used by `require_plan`.
    # Let's see: `require_plan` does: `async def _check(user: dict = Depends(verify_api_key)):`
    # So if we override `verify_api_key`, `require_plan` will use the mocked `user` dictionary!
    app.dependency_overrides[verify_api_key] = mock_verify_api_key
    
    print("Testing /sessions/")
    response = client.post("/sessions/?name=TestSession")
    print("Sessions Create Status:", response.status_code)
    if response.status_code == 201:
        session_id = response.json()["session_id"]
        print("  Created session:", session_id)
        
        print(f"Testing /sessions/{session_id}")
        resp2 = client.get(f"/sessions/{session_id}")
        print("  Get Session Status:", resp2.status_code)
        
        print(f"Testing /sessions/{session_id}/join")
        resp3 = client.post(f"/sessions/{session_id}/join")
        print("  Join Session Status:", resp3.status_code)
    else:
        print("  Failed:", response.text)
        
    print("\nTesting /export/simulink")
    fc_payload = {
        "m_s": 1500.0, "I_x": 400.0, "I_y": 1500.0, "m_uf": 45.0, "m_ur": 45.0,
        "k_sf": 35000.0, "k_sr": 40000.0, "c_f": 3000.0, "c_r": 3500.0,
        "k_arb_f": 10000.0, "k_arb_r": 5000.0, "k_tf": 250000.0, "k_tr": 250000.0,
        "L": 2.7, "a": 1.2, "b": 1.5, "tw_f": 1.6, "tw_r": 1.6, "speed_mps": 20.0
    }
    resp_sim = client.post("/export/simulink", json=fc_payload)
    print("Simulink Export Status:", resp_sim.status_code)
    if resp_sim.status_code == 200:
        print("  Content starts with:", repr(resp_sim.text[:50]))
    else:
        print("  Failed:", resp_sim.text)
        
    print("\nTesting /export/adams")
    resp_adm = client.post("/export/adams", json=fc_payload)
    print("ADAMS Export Status:", resp_adm.status_code)
    if resp_adm.status_code == 200:
        print("  Content starts with:", repr(resp_adm.text[:50]))
    else:
        print("  Failed:", resp_adm.text)
        
    print("\nTesting /reports/iso2631")
    qc_payload = {
        "params": {
            "m_s": 350.0, "m_u": 45.0, "k_s": 25000.0, "c": 1500.0, "k_t": 200000.0,
            "MR": 0.85
        },
        "profile": {
            "profile_type": "step",
            "amplitude": 0.1,
            "duration": 5.0,
            "frequency": 2.0
        }
    }
    resp_iso = client.post("/reports/iso2631", json=qc_payload)
    print("ISO Report Status:", resp_iso.status_code)
    if resp_iso.status_code == 200:
        print("  Content starts with:", repr(resp_iso.text[:100]))
    else:
        print("  Failed:", resp_iso.text)
        
if __name__ == "__main__":
    test_features()
