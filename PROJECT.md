# Project: ApexSim ANSYS/ADAMS Grade Audit & Production Hardening

## Architecture
- **Backend Physics & API**: Python 3.14 + FastAPI + Numba in `src/suspensionlab/` (3-pass closed-loop GGV solver, quasi-steady-state lap simulator, dynamic aero-pitch bottoming, roll/pitch angles, work-energy integration).
- **Vercel Backend**: Serverless FastAPI deployment in `backend_vercel/` synced from `src/suspensionlab/`.
- **Frontend Studio**: Next.js 14 + React + Plotly.js in `frontend/` (`/lap-sim` Telemetry Studio & `/` Landing Page).
- **Verification & Deployment**: Pytest (`tests/test_lap_sim_ansys_grade_audit.py`), Vercel CLI (`npx vercel --prod --yes`), Playwright headless live browser verification at 1440x900.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Work-Energy Balance | Newtonian closed-loop integration: `energy_used_kj = aero_drag_energy_kj + rolling_energy_kj + braking_energy_kj` with residual `<= 1.5%` | M1 | R1 |
| 2 | Chassis Roll & Pitch Angles | Compute instantaneous `roll_deg` via `(m * lat_g * 9.81 * arm)/max(K_phi, 5000)`, include in trace, plus `max_roll_deg`/`max_pitch_deg` in summary | M1 | R1 |
| 3 | U-Shaped LLTD Convexity | Two-axle cornering saturation & rear traction-ellipse exit coupling: `lap_time(arb=42)` strictly faster than both `arb=10` and `arb=95` | M1 | R1 |
| 4 | Physics Pytest Audit Suite | Implement `tests/test_lap_sim_ansys_grade_audit.py` testing work-energy <= 1.5% (Spa, Silverstone, Monza, FSAE), U-shaped convexity, monotonic roll reduction | M1 | R1 |
| 5 | FSAE Preset Auto-Switch | Auto-switch to Formula Student EV profile (295 kg / 80 kW) on FSAE circuit selection; restore GT3 baseline (1285 kg / 395 kW) on Spa/Silverstone/Monza | M2 | R2 |
| 6 | Lower Telemetry Charts Formatting | Ensure all 6 lower charts have `margin: { t: 48, r: 20, b: 42, l: 54 }`, unclipped titles, horizontal legends at `y: 1.14` | M2 | R2 |
| 7 | Landing Page Flagship Promotion | Elevate `/lap-sim` to co-headline flagship in Hero with 4 verified capabilities card and `'Launch ApexSim Lap Studio ->'` CTA | M3 | R3 |
| 8 | Solver Matrix Table Row | Add ApexSim 3-Pass Closed-Loop GGV row to Verification & Physical Applicability Matrix with method, <= 0.82% / <= 1.5% accuracy, ~3.5 hrs -> < 3 sec benchmark | M3 | R3 |
| 9 | Code Synchronization | Recursively sync `src/suspensionlab/` into `backend_vercel/src/suspensionlab/` | M4 | R4 |
| 10 | Build & Pytest Verification | Execute `pytest tests/test_lap_sim_ansys_grade_audit.py` and frontend Next.js production build | M4 | R4 |
| 11 | Vercel Production Deployments | Non-interactive production deploy of `backend_vercel` and `frontend` via `npx vercel --prod --yes` | M4 | R4 |
| 12 | Live 4-Workflow Browser Verification | Execute all 4 interactive workflows on production `https://suspensionlab-studio.vercel.app/lap-sim` at 1440x900 and capture required screenshots | M4 | R4 |
| 13 | Host System Shutdown | Execute host laptop shutdown command upon completion of all goals | M5 | R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Physics & Pytest Audit | R1: `src/suspensionlab/physics/lap_sim.py`, routes, `tests/test_lap_sim_ansys_grade_audit.py` | none | DONE |
| 2 | Frontend FSAE Preset & Charts | R2: `frontend/app/lap-sim/page.tsx` | none | DONE |
| 3 | Landing Page Flagship Promotion | R3: `frontend/app/page.tsx` | none | DONE |
| 4 | Deployment & Live Browser Verification | R4: Sync to `backend_vercel/`, Pytest, Vercel deployments, 4-workflow live testing | M1, M2, M3 | DONE |
| 5 | Host System Shutdown | R5: Host laptop shutdown | M4 | DONE |

## Interface Contracts
### Physics ↔ API Routes & Frontend Contract
- `ClosedLoopSimResult` and `to_contract_dict()` include:
  * `aero_drag_energy_kj: float`
  * `rolling_energy_kj: float`
  * `braking_energy_kj: float`
  * `energy_balance_error_pct: float`
  * `max_roll_deg: float`
  * `max_pitch_deg: float`
- `trace` dictionary includes:
  * `roll_deg: list[float]`
  * `pitch_deg: list[float]`
- Circuit ID mapping:
  * Built-in FSAE circuit ID is `fsae_michigan` (label `FSAE (1,450m)`).

## Code Layout
- Physics core: `src/suspensionlab/physics/lap_sim.py`
- Backend API routes: `src/suspensionlab/backend/api/routes/lap_sim_routes.py`
- Vercel Backend copy: `backend_vercel/src/suspensionlab/`
- Frontend Studio: `frontend/app/lap-sim/page.tsx`
- Frontend Landing: `frontend/app/page.tsx`
- Tests: `tests/test_lap_sim_ansys_grade_audit.py`
