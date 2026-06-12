# SuspensionLab PRO API Reference

## Overview

Welcome to the SuspensionLab PRO API. Our API allows motorsport engineers and developers to programmatically interface with our quarter-car kinematics and dynamics solver. 

- **Base URL:** `https://api.suspensionlab.pro`
- **Authentication:** Provide your API key via the `X-API-Key` HTTP header. Example: `X-API-Key: sl_live_xxxxxxxx`
- **Error Format:** All API errors are returned as JSON in the following standard format:
  ```json
  {
    "error": "error_code",
    "message": "Human-readable description.",
    "request_id": "req_123456789"
  }
  ```

---

## Rate Limits
Rate limits are strictly enforced dynamically per route using sliding windows.
- **POST `/optimize`**: 10 requests / minute
- **POST `/simulate`**: 30 requests / minute

Hitting a rate limit will immediately result in an HTTP 429 response. 

## Endpoints

### Health Check
`GET /health`
Returns the operational status of the backend API.
- **Auth Required:** No
- **Response Format:** `{"status": "ok"}`
- **Example cURL:**
  ```bash
  curl -X GET https://api.suspensionlab.pro/health
  ```

### Current User
`GET /me`
Returns details and subscription tier for the authenticated API key. Tiers dictate concurrency limits: FREE (1 job), PRO (4 jobs), MAX (16 jobs).
- **Auth Required:** Yes
- **Response Format:** `{"user_id": "usr_...", "tier": "PRO"}`
- **Example cURL:**
  ```bash
  curl -X GET https://api.suspensionlab.pro/me \
    -H "X-API-Key: YOUR_API_KEY"
  ```

### Complete Onboarding
`PATCH /users/me/onboarding`
Marks the current user's onboarding tutorial flow as complete.
- **Auth Required:** Yes
- **Response Format:** HTTP 200 OK
- **Example cURL:**
  ```bash
  curl -X PATCH https://api.suspensionlab.pro/users/me/onboarding \
    -H "X-API-Key: YOUR_API_KEY"
  ```

### Run Simulation
`POST /simulate`
Executes an immediate RK45 solver run over a specific bump profile.
- **Auth Required:** Yes
- **Request Body:** JSON matching `SimulateRequest` parameters.
- **Response Format:** `QuarterCarResultSchema` object containing telemetrics and RMS values.
- **Example cURL:**
  ```bash
  curl -X POST https://api.suspensionlab.pro/simulate \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"m_s": 450, "m_u": 45, "k_s": 35000, "c_s": 2500}'
  ```

### Start Optimizer
`POST /optimize`
Submits an AI genetic algorithm job to find the optimal spring/damper parameters for the provided mass and road constraints. Subject to tier concurrency limits.
- **Auth Required:** Yes (Rate limited)
- **Request Body:** JSON matching `OptimizeRequest` constraints.
- **Response Format:** `{"job_id": "job_123..."}`
- **Example cURL:**
  ```bash
  curl -X POST https://api.suspensionlab.pro/optimize \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"target": "comfort"}'
  ```

### Get Active Job
`GET /optimize/active`
Returns the user's currently running optimization job.
- **Auth Required:** Yes
- **Response Format:** Job schema or HTTP 404 if no job is actively running.
- **Example cURL:**
  ```bash
  curl -X GET https://api.suspensionlab.pro/optimize/active \
    -H "X-API-Key: YOUR_API_KEY"
  ```

### Get Job Status
`GET /optimize/{id}/status`
Polls the Redis cache for the current state and progression of a specific optimization job.
- **Auth Required:** Yes
- **Response Format:** `{"status": "RUNNING", "progress": 45.5}`
- **Example cURL:**
  ```bash
  curl -X GET https://api.suspensionlab.pro/optimize/job_1234/status \
    -H "X-API-Key: YOUR_API_KEY"
  ```

### Get Job History
`GET /optimize/history`
Returns a list of all historical optimization jobs run by the user.
- **Auth Required:** Yes
- **Response Format:** Array of completed optimization Job schemas.
- **Example cURL:**
  ```bash
  curl -X GET https://api.suspensionlab.pro/optimize/history \
    -H "X-API-Key: YOUR_API_KEY"
  ```

### Initiate Checkout
`POST /billing/checkout`
Initiates a Stripe Checkout session to upgrade the user's tier.
- **Auth Required:** Yes
- **Request Body:** `{"plan": "PRO"}` or `{"plan": "MAX"}`
- **Response Format:** `{"checkout_url": "https://checkout.stripe.com/..."}`
- **Example cURL:**
  ```bash
  curl -X POST https://api.suspensionlab.pro/billing/checkout \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"plan": "PRO"}'
  ```

### Billing Webhook
`POST /billing/webhook`
Receives asynchronous updates from Stripe regarding subscription lifecycle events.
- **Auth Required:** No (Uses `Stripe-Signature` validation instead).
- **Example cURL:** (Usually invoked directly by Stripe)
  ```bash
  curl -X POST https://api.suspensionlab.pro/billing/webhook \
    -H "Stripe-Signature: t=123,v1=abc" \
    -H "Content-Type: application/json" \
    -d '{"id": "evt_..."}'
  ```

---

## Error Codes

The API utilizes standard HTTP status codes combined with descriptive JSON payloads:

- **400 Bad Request:** The request was malformed or missing required parameters.
- **401 Unauthorized:** Invalid, missing, or revoked API key.
- **403 Forbidden:** The authenticated user lacks permission to access this resource or perform this action.
- **404 Not Found:** The requested resource (e.g., job ID) does not exist.
- **422 Unprocessable Entity:** Validation error (e.g., invalid JSON schema or type mismatch).
- **429 Too Many Requests:** You have exceeded the route's rate limit.
- **503 Service Unavailable:** The API or its underlying datastores are temporarily offline.
