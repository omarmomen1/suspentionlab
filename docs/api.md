# SuspensionLab PRO API Documentation

## Base URL
`https://api.suspensionlab.pro`

## Authentication
Pass your API key via the `X-API-Key` header.
`X-API-Key: sl_live_...`

## Endpoints

### 1. Optimize Setup (Quarter Car)
`POST /optimize`
Run the AI genetic algorithm to find the optimal spring/damper parameters for a given road profile.

**Payload:**
```json
{
  "mass_body": 450.0,
  "mass_wheel": 45.0,
  ...
}
```

**Response:**
Returns a `QuarterCarResultSchema` containing the optimized stiffness, damping, and transmissibility arrays.

### 2. Simulate Setup
`POST /simulate`
Run the RK45 solver over a specific bump profile.

### 3. Billing
`POST /billing/checkout`
Initiates a Stripe Checkout session to upgrade tier.

## Rate Limits
Rate limits are enforced dynamically via Redis sliding windows.
- `/optimize`: 10 req / min
- `/simulate`: 30 req / min

Exceeding limits returns HTTP 429.
