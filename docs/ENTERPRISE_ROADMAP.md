# SuspensionLab PRO — Enterprise Roadmap

Status as of 2026-08-23. This document maps the prioritised improvement
backlog against what is **already implemented**, so effort estimates apply
only to remaining work.

## 1. Improvement backlog — status

Legend: ✅ DONE · 🔶 PARTIAL · ⬜ TODO

| # | Improvement | Effort (remaining) | ROI | Status |
|---|-------------|--------------------|-----|--------|
| 1 | Motion-ratio contract fix | — | Extreme | ✅ DONE — MR = spring/wheel travel, k_w = k_s·MR² consistent everywhere |
| 2 | Remove false enterprise/F1 claims | — | High | ✅ DONE — ISO/ADAMS wording corrected; no F1-grade claims |
| 3 | JWT secret handling | — | Extreme | ✅ DONE — PROD fail-fast gate, key rotation, weak-secret rejection |
| 4 | Team creation/analytics | — | High | ✅ DONE — slug fix; team_id propagated through all job paths |
| 5 | Audit infrastructure | — | High | ✅ DONE — durable AuditLog + EngineeringAuditLog, team-scoped API |
| 6 | Secure public reports | — | High | ✅ DONE — server-side artifacts, SHA-256, HMAC-signed tokens, provenance labels |
| 7 | Move all compute to queue | ~3 days | Extreme | 🔶 PARTIAL — orchestrator + bounded pool + concurrency caps done; sensitivity/inline paths still bypass RQ for small runs |
| 8 | Physics V&V framework | ~2 weeks | Extreme | 🔶 PARTIAL — registry + runner + API live (6/6 cases); add commercial-solver & physical-test correlation cases |
| 9 | Proper damper model | — | Extreme | ✅ DONE — compression/rebound curves, validation, energy-equivalent linearisation |
| 10 | Kinematics engine | ~2 weeks | Extreme 🔥🔥🔥 | 🔶 PARTIAL — C++ NR solver live (camber/toe/RC/MR/scrub); missing anti-dive/squat, jacking, rocker/ARB geometry |
| 11 | Dynamic 3D roll center | 2–4 weeks | Very high 🔥🔥 | ⬜ TODO — RC-vs-travel exists; RC-vs-roll + 3D visualisation pending |
| 12 | Real tire model/calibration | 3–6 weeks | Extreme 🔥🔥🔥 | 🔶 PARTIAL — MF 5.2 + TIR parsing + thermal µ; no fitting/calibration pipeline |
| 13 | Telemetry ingestion/calibration | ~2 weeks | Extreme 🔥🔥🔥 | 🔶 PARTIAL — parse/QA/segment/compare pipeline + **Digital Setup Twin parameter identification live** (Welch PSD → SDOF acceleration-FRF NLLS fit; verified recovering f_n within 2.1% and ζ within 1.4% on noisy synthetic telemetry); multi-parameter/full-vehicle identification pending |
| 14 | Real lap-time engine | ~3 weeks | Extreme 🔥🔥🔥 | 🔶 PARTIAL — GGV QSS solver w/ aero, ERS, thermal; missing transients, diff, brake bias |
| 15 | Multiobjective optimization | — | Very high 🔥🔥 | ✅ DONE — Pareto frontier + constraint-driven lap-time optimizer |
| 16 | Aero map integration | ~2 weeks | Very high 🔥🔥🔥 | 🔶 PARTIAL — ride-height-dependent CL/CD map; no CFD/wind-correlation import |
| 17 | Vehicle/setup versioning | ~3 days | Very high 🔥🔥 | ✅ DONE — immutable RUN artifacts with version pinning + hashes |
| 18 | Setup comparison/diff | — | Very high 🔥🔥 | ✅ DONE — /runs/{a}/diff/{b} + what-changed headline |
| 19 | SSO + SCIM | — | High | ✅ DONE — OIDC auth-code flow (PKCE/JWKS); SCIM 2.0 CRUD |
| 20 | RBAC | ~1 week | High | 🔶 PARTIAL — plan gating + team roles (Owner/Admin/Viewer); per-resource permissions pending |
| 21 | Audit/provenance | — | High 🔥 | ✅ DONE — immutable artifacts + engineering audit ledger |
| 22 | Private/on-prem deployment | 2–4 weeks | Extreme 🔥🔥🔥 | 🔶 PARTIAL — Docker/K8s/Terraform exist; air-gapped packaging + license enforcement pending |
| 23 | Enterprise API/SDK | 2–3 weeks | Very high 🔥🔥 | 🔶 PARTIAL — API keys + OpenAPI docs; official SDK packages pending |
| 24 | AI engineer grounded in physics | — | Very high 🔥🔥 | ✅ DONE — LLM-as-interface; physics proposes, sim validates, LLM explains |
| 25 | Layered decision UI | ~2 days | High | 🔶 PARTIAL — decision engine + DecisionPanel component; integrate across all result pages |
| 26 | **Digital Setup Twin** (#40) | ~4 weeks (to full vehicle) | Extreme 🔥🔥🔥 | 🔶 PARTIAL — VehicleTwin model, telemetry-driven parameter identification, calibration history, learning store (`/twins` API) live for the ride domain; extend to tire/aero/kinematics domains |
| 27 | **Vehicle-specific learning moat** (#41) | ongoing | Extreme 🔥🔥🔥 | 🔶 PARTIAL — CalibrationObservation ledger + aggregated learnings endpoint live; response-surface modelling over accumulated observations pending |
| 28 | **Setup Proposal workflow** (#50) | ~1 week (to full UX) | Extreme 🔥🔥🔥 | ✅ CORE DONE — twin params → candidate search → simulate → validate → immutable proposal with predicted effects + approve/reject/export lifecycle (`/twins/{id}/propose`) |
| 26 | **Digital Setup Twin** (#40) | ~4 weeks (to full vehicle) | Extreme 🔥🔥🔥 | 🔶 PARTIAL — VehicleTwin model, telemetry-driven parameter identification, calibration history, learning store (`/twins` API) live for the ride domain; extend to tire/aero/kinematics domains |
| 27 | **Vehicle-specific learning moat** (#41) | ongoing | Extreme 🔥🔥🔥 | 🔶 PARTIAL — CalibrationObservation ledger + aggregated learnings endpoint live; response-surface modelling over accumulated observations pending |

## 2. Explicitly NOT building yet

Per strategy: no social collaboration, dashboard-widget bloat, excessive AI
chat, gamification, mobile app, simulation-type sprawl, or export-format
sprawl until the 🔥 items above close.

## 3. Target architecture

```
                    ┌─────────────────────┐
                    │     Next.js UI      │
                    │ Engineer Workspace  │
                    └──────────┬──────────┘
                               │ REST / WebSocket
                    ┌──────────▼──────────┐
                    │      FastAPI        │
                    │ API + Auth + RBAC   │
                    └──────────┬──────────┘
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        PostgreSQL           Redis        Object Storage
        metadata             queue        results/data
              └────────────────┼────────────────┘
                               ▼
                       Compute Orchestrator   ← DONE (workers/orchestrator.py)
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
        Python Workers    C++ Physics       ML Surrogate   ← C++ kinematics live; ML surrogate TODO
              └────────────────┘
                       │
              ┌────────▼─────────┐
              │ Physics Engine   │  ← kinematics ✅ · suspension ✅ · tires 🔶
              │                  │    vehicle dynamics ✅ · aero 🔶 · lap sim 🔶
              └──────────────────┘
                       │
              Validation Engine    ← model validity ✅ · V&V suite 🔶
                       │
              Optimization Engine  ← Pareto + constraint-driven ✅
                       │
              Engineering Decision ← layered decision UI 🔶 · run artifacts ✅
```



## 4. Business model & positioning (Issues 47–49)

### Pricing tiers

| Tier | Price | Includes |
|------|-------|----------|
| Professional | $100–300/month | Engineers, students, consultants: core simulators, profiles, history |
| Motorsport Team | $10k–50k/year | Multi-user workspace, telemetry + twin calibration, optimization, API, reports |
| Enterprise / OEM | $50k–250k+/year | Private deployment, dedicated compute, SSO/SCIM/RBAC, audit, custom models, validation SLA |
| Custom engineering | $50k–500k/project | Vehicle/tire model calibration, telemetry and data-pipeline integration, solver integration, on-prem |

Deliberately **not** a "$49/month simulator" — that positioning is a race to the bottom.

### Honest pitch (the only one that works)

> SuspensionLab does not replace an F1 team's existing CAE ecosystem. It is a
> rapid vehicle-dynamics exploration, telemetry-correlation, optimization, and
> engineering-decision layer that sits on top of it.

What makes an engineer listen: *"Upload your telemetry and vehicle parameters.
SuspensionLab identifies where the model disagrees with reality, quantifies the
discrepancy, searches the feasible setup space, and produces a traceable
engineering recommendation."* — not "we have AI."

## 5. Phased execution status (Issue 51)

| Phase | Scope | Status |
|-------|-------|--------|
| **0 — Stop the bleeding** | Motion ratio, damper consistency, secrets, teams, audit, provenance, SSO/SCIM honesty, compute protection | ✅ DONE — trustworthy prototype |
| **1 — V&V engine** | Framework, regression suite, references, tolerances, versioning, hashes | ~70% — registry+runner+API live; commercial/physical correlation cases pending |
| **2 — Kinematics engine** | Hardpoints, NR solver, camber/toe/RC/MR, anti-geometry, 3D dynamic geometry | ~60% — C++/Eigen solver live; anti-geometry, jacking, rockers, 3D viz pending |
| **3 — Telemetry intelligence** | Ingestion, mapping, sync, segmentation, correlation, parameter identification, residuals | ~65% — full pipeline + Digital Twin identification live; residual analysis and multi-domain ID pending |
| **4 — Vehicle dynamics coupling** | Kinematics+tire+aero+suspension to load transfer to lap sim | ~55% — GGV QSS lap sim with aero+ERS+thermal; transient/diff/bias pending |
| **5 — Optimization** | DOE, Pareto, constraints, surrogates, uncertainty, robust | ~60% — Pareto + constraint-driven done; DOE/surrogates/UQ pending |
| **6 — Enterprise** | OIDC done, SCIM done, RBAC partial, audit done, artifacts done; private deploy / SDK / SLOs pending | ~70% |

## 6. Immediate next sprint (highest ROI)
1. **Close #7** — route remaining inline compute through the orchestrator.
2. **Kinematics completion (#10)** — anti-geometry, jacking, rockers.
3. **Decision panel integration (#25)** — mount `DecisionPanel` on every result page.
4. **V&V expansion (#8)** — add half-car/full-car analytical cases + first commercial-solver benchmark.
5. **RBAC (#20)** — resource-level permissions on runs/profiles within teams.
