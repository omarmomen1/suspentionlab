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
| 13 | Telemetry ingestion/calibration | ~3 weeks | Extreme 🔥🔥🔥 | 🔶 PARTIAL — parse/QA/segment/compare pipeline live; parameter identification & auto-calibration pending |
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

## 4. Immediate next sprint (highest ROI)

1. **Close #7** — route remaining inline compute through the orchestrator.
2. **Kinematics completion (#10)** — anti-geometry, jacking, rockers.
3. **Decision panel integration (#25)** — mount `DecisionPanel` on every result page.
4. **V&V expansion (#8)** — add half-car/full-car analytical cases + first commercial-solver benchmark.
5. **RBAC (#20)** — resource-level permissions on runs/profiles within teams.
