import time
import json
import urllib.request
import urllib.error

def fetch_with_retry(req, max_retries=5, delay=2):
    for i in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception as e:
            print(f"Attempt {i+1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError("Failed after max retries")

# 1. Login
print("Testing Login...")
login_req = urllib.request.Request(
    'https://suspensionlab-api.vercel.app/api/v1/auth/login',
    data=json.dumps({'email': 'testuser@suspensionlab.com', 'password': 'SuspensionLab2026!#'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
status, data = fetch_with_retry(login_req)
print(f"Login response status: {status}")
token = data.get('token')
print(f"Token received: {token[:25]}...")

# 1b. Activate PRO License
print("\nActivating PRO License...")
pro_key = "SLPRO-PRO-eyJleHAiOjE4MjYxMjcxMzUsImp0aSI6ImIzOGQ0Mjg1MDdiZiIsIm1heF91c2VzIjoxLCJwbGFuIjoiUFJPIn0.UCy0a_VxvFPtNZ_5qNkP34CAXxCVbRCdHybcohRdlt0"
act_req = urllib.request.Request(
    'https://suspensionlab-api.vercel.app/api/v1/billing/verify-license',
    data=json.dumps({'license_key': pro_key}).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    method='POST'
)
act_status, act_data = fetch_with_retry(act_req)
print(f"License Activation status: {act_status}")
print(f"License Activation response: {act_data}")

# 2. Simulate Quarter-Car
print("\nTesting Simulate (Synchronous ODE on Vercel)...")
sim_payload = {
    'params': {
        'm_s': 250.0,
        'm_u': 45.0,
        'k_s': 35000.0,
        'c': 1500.0,
        'k_t': 190000.0,
        'MR': 1.0,
        'c_t': 0.0
    },
    'profile': {
        'profile_type': 'step',
        'amplitude': 0.05,
        'frequency': 1.5,
        'duration': 2.0
    }
}
sim_req = urllib.request.Request(
    'https://suspensionlab-api.vercel.app/api/v1/simulate',
    data=json.dumps(sim_payload).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    method='POST'
)
sim_status, sim_data = fetch_with_retry(sim_req)
print(f"Simulate response status: {sim_status}")
print(f"Simulate response body: {sim_data}")
print(f"Job Status: {sim_data.get('status')}")
has_result = 'result' in sim_data and sim_data['result'] is not None
print(f"Inline Result Present: {has_result}")
if has_result:
    r = sim_data['result']
    print(f"Computed f_n_s: {r.get('f_n_s')} Hz, zeta_s: {r.get('zeta_s')}, peak_susp_travel: {r.get('peak_susp_travel')} m")

# 3. AI Engineer Chat
print("\nTesting AI Engineer Chat (/api/v1/ai/chat)...")
ai_payload = {
    'problem': 'My car bounces excessively over apex curbs and takes too long to settle.',
    'params': {
        'm_s': 250.0,
        'm_u': 45.0,
        'k_s': 35000.0,
        'c': 1500.0,
        'k_t': 190000.0,
        'MR': 1.0,
    }
}
ai_req = urllib.request.Request(
    'https://suspensionlab-api.vercel.app/api/v1/ai/chat',
    data=json.dumps(ai_payload).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    method='POST'
)
ai_status, ai_data = fetch_with_retry(ai_req)
print(f"AI Chat response status: {ai_status}")
print(f"Diagnosis: {ai_data.get('diagnosis')}")
print(f"Setup summary: {ai_data.get('setup_summary')}")
print(f"Best feasible: {ai_data.get('best_feasible')}")
print(f"Predicted effects count: {len(ai_data.get('predicted_effects', []))}")
print(f"Citations count: {len(ai_data.get('citations', []))}")
