# SuspensionLab PRO — Trial Operator Guide

This document contains the complete operational instructions for hosting a private 7-day Formula Student evaluation workspace from your laptop for an external evaluating engineer.

---

## 1. COMMAND 1: START TRIAL ENVIRONMENT

Run the one-command startup script to launch the isolated backend, hardened frontend, and secure public HTTPS tunnel:

```powershell
python scripts/run_trial_environment.py --public
```

* Automatically checks service health on private loopback (`127.0.0.1:8001` and `127.0.0.1:3001`).
* Automatically spawns an encrypted HTTPS public tunnel (Cloudflare Quick Tunnel with LocalTunnel fallback).
* Enforces zero source exposure: suppresses `/docs`, `.map`, `/.git`, and `/.env`.
* Completely hides database and Redis ports from the host machine.
* Prints the active public **Customer URL**. Keep this terminal window open while the prospect is evaluating.

---

## 2. COMMAND 2: CREATE CUSTOMER ACCOUNT

Provision a new prospective engineer with a self-contained 7-day evaluation organization, preloaded Formula Student electric vehicle twin (`SLP-FS-EV-01`), Turn 4 autocross telemetry, and a 50-simulation quota:

```powershell
python scripts/create_trial_user.py --email "engineer@apex-racing.com" --name "Alex Mercer" --org "Apex Formula Student"
```

### Exact Output Format to Hand to the Engineer:

```text
========================================================================
      SUSPENSIONLAB PRO — EVALUATOR ONBOARDING CREDENTIALS
========================================================================
CUSTOMER URL:         https://<tunnel-subdomain>.trycloudflare.com/login
USERNAME:             engineer@apex-racing.com
TEMPORARY CREDENTIAL: <generated-temporary-password>
TRIAL EXPIRATION:     7 Days from Provisioning (50 Simulation Runs)
------------------------------------------------------------------------
ORGANIZATION:         Apex Formula Student
PRELOADED VEHICLE:    SLP-FS-EV-01 (Formula Student EV)
BASELINE QUESTION:    Why is front tire-load variation increasing during
                      aggressive corner entry?
DIRECT WORKSPACE:     https://<tunnel-subdomain>.trycloudflare.com/evaluation
========================================================================
```

---

## 3. COMMAND 3: RESET CUSTOMER GARAGE

If an evaluator wants to restart their investigation from a clean slate, or if you are conducting a second demonstration:

```powershell
python scripts/reset_trial.py --email "engineer@apex-racing.com"
```

* Purges all custom experiment runs, hypothesis records, candidate setups, and decisions created by this user.
* Resets simulation run count back to `0 / 50`.
* Restores the pristine baseline vehicle `SLP-FS-EV-01` and hero question `Q-FS-01`.
* Strict tenant isolation is preserved: other organizations and evaluators are completely untouched.

---

## 4. SECURITY & HARDENING VERIFICATIONS

* **No Source Exposure:** Source repository, `.git`, `.env`, and Next.js source maps (`.map`) are blocked.
* **No Documentation Routes:** `/docs`, `/redoc`, and `/openapi.json` return HTTP 404.
* **No Direct Localhost Leakage:** Frontend reverse-proxies all `/api/v1/*` calls through Next.js; browser never calls backend port `:8000` or `:8001`.
* **Server-Authoritative Enforcement:** Simulation quotas and 7-day expiration are validated in the backend database. Expired tokens cannot execute ODE solvers or mutate workspace state.
* **Audit Provenance:** Decisions generate an immutable engineering decision record with cryptographic provenance and server-verifiable authenticated approval.
