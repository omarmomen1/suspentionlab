# ApexSim 2.0 build spec

Developer-ready spec distilled from the ApexSim 2.0 Transformation Dossier (31 pages, Nov 27 2026). Build directly from this file. Where a number came from the live app it is marked MEASURED; where it is a target or model estimate it is marked TARGET or ESTIMATE. Nothing here has been shipped.

## 0. Locked decisions (Omar, Nov 28 2026)

1. **Tire data:** start with FSAE TTC / published data. Label the source on every run until paying teams bring their own data.
2. **Correlation car:** Omar recruits one team for a logged Spa lap right after Sprint 2 ships. The correlation pilot is gated on that lap.
3. **Product shell:** ApexSim stays **inside the main SuspensionLab app and subscription** as the flagship feature. No separate domain, no separate billing shell, no separate SKU for now. (This overrides the dossier's standalone-shell chapter; the $200/mo tier discussion is parked.)

## 1. Baseline and target

MEASURED on the live app (production, 27 Nov 2026, signed in):

- Spa with elevation: **2:11.043** (S1 38.2 / S2 47.9 / S3 45.0). Flat: 2:10.527. Both uncorrelated, 4-5 s optimistic vs a real GT3 (audit).
- 15 input sliders (7 vehicle, 8 suspension). No tire curve, no aero map, no diff, no fuel.
- 4 circuits (Spa 7,004 m, Silverstone, Monza, FSAE) + custom track architect + CSV/GPS reconstruction.
- Elevation: 19 stations, one every 368 m; the UI itself says this cannot resolve Eau Rouge (~200 m, 13% actual grade, 6.2% resolved).
- Setup surface: 2 parameters, 21-51 s per run; optimum lands on the grid edge (25 setups, 1 non-dominated point — a boundary artifact).
- Correlation: separate page, demo telemetry, R² 0.8419 on a sample signal, never sees the lap sim.
- Capability index: **28/100** across 20 axes. TARGET: **84/100**.

**Product sentence:** ApexSim answers one question in under ten seconds: where did the lap go, and what do I change first? Anything that does not shorten those ten seconds, or make the answer defensible, is out of scope.

**Three pillars:**
1. **Conservation** — the budget sums. If a lap is 0.42 s slower, corner/phase/subsystem deltas add to 0.42 ± 0.001 s. No orphan percentages.
2. **Provenance** — every number carries an ID, a model version and a timestamp. The AI may quote only registered numbers.
3. **Correlation** — a lap is a result only when it matches a logged lap inside a stated tolerance; until then it is labeled PREDICTION everywhere it appears.

## 2. Architecture: one engine, six layers, one truth registry

```
INPUTS       Track | Vehicle | Tire | Aero | Ambient | Driver
KERNELS      Track 1 m | Vehicle 14-DOF | Tire MF 5.2 | Aero map | Driver OCP
SOLVER       Fixed-step 500 Hz, vectorized | implicit tire solve | warm start from last run
TRUTH        Budget engine | Sensitivity (adjoint) | Provenance registry | Constraint checker
CORRELATION  Telemetry ingest | Channel health | Alignment | Calibration | Residuals
SURFACE      Cockpit | Why chain | Twin replay | Optimizer | Report | API
```

Structural rule: **budget and sensitivities are computed once per run, stored with the run record, and never recomputed in the browser.** Every surface reads the same registry. The UI stops being the source of truth.

### 2.1 Truth Registry schema

```jsonc
// RunRecord — one per solver run, immutable once written
{
  "run_id": "R-8841",                 // unique, human-readable
  "created_at": "2026-11-28T01:00:00Z",
  "track": {"id": "spa", "source": "laser-scan|gps|csv|official-map", "resolution_m": 1, "elevation": true},
  "car": {"id": "gt3-base", "template_version": "v1"},
  "setup": { /* full parameter dict, hashed */ },
  "models": {"solver": "2.1.0", "tire": "MF52-GT3-v3", "aero_map": "GT3-RH-v1", "code_ref": "f53b5d0"},
  "result": {"lap_time_s": 130.62, "sectors_s": [38.1, 47.8, 44.7]},
  "label": "PREDICTION" | "CORRELATED",
  "correlation": {"tolerance_s": 0.5, "achieved_s": 0.31, "logged_lap_id": "L-102"} | null,
  "provenance": ["S-2210", "S-2211"]  // ids of every number derived from this run
}

// BudgetRecord — the conservation budget, stored with the run
{
  "run_id": "R-8841",
  "reference_run_id": "R-8840",
  "delta_s": -0.42,
  "terms": [                          // ranked; each links to a sensitivity id
    {"subsystem": "aero_balance", "delta_s": -0.19, "change": "front wing flap +1 click", "sensitivity_id": "S-2210"},
    {"subsystem": "tire_pressure_rl", "delta_s": -0.11, "change": "rear left -0.5 psi", "sensitivity_id": "S-2211"}
  ],
  "by_corner_s": [-0.01, ...],        // per-corner strip
  "conservation_check_s": 0.0004      // |sum(terms) - delta|; MUST be <= 0.001
}

// SensitivityRecord — adjoint derivatives for one run
{
  "run_id": "R-8841",
  "derivatives": [{"input": "rear_ride_height", "output": "lap_time", "value": 0.012, "units": "s/mm"}],
  "validation": {"method": "central-difference", "sampled": 5, "max_error_pct": 1.8}  // gate: <= 2%
}
```

Rules:
- If the conservation check fails, the page shows an **error, not a budget**.
- A run that fails correlation step 6 is labeled PREDICTION and **cannot be exported as a result**.
- If no tire data exists for a tire, ApexSim says so and **refuses to grade the run**.
- Every run carries the tire data source label (decision 0.1): e.g. `tire_data: "FSAE TTC"` shown on the run, the report and the API.

## 3. Kernels

### 3.1 Vehicle — 14 DOF, 24 states (TARGET)
- Sprung mass: heave, roll, pitch (3). Unsprung: 4 corners vertical (4). Wheel spin: 4 driven/braked (4). Planar: yaw, lateral, longitudinal (3). Plus tire states (slip, temperature, pressure) and a fuel mass state.
- Buys: dynamic load transfer, tire load sensitivity and combined slip (corner exit stops being free); a differential (power-on understeer, entry stability); brake temperature (bias drift over a stint); aero that responds to attitude (pitch → ride height → downforce → braking).
- Template: 1,320 kg, 2.60 m wheelbase, 1.65 m track, 0.42 m CG — all editable.
- Expected shift before calibration: +1.5 to +3.0 s at Spa.

### 3.2 Tire — Magic Formula 5.2 (TARGET)
- Today: single mu = 1.38, a circle, same at every load and temperature.
- Build: MF 5.2 with B, C, D, E per tire; load-sensitive D and E; pressure scaling; thermal window 70-110 °C; wear state; combined-slip weighting.
- Data source (decision 0.1): .tir import, **FSAE TTC dataset**, manufacturer curves; source labeled on every run.
- Where the time is (ESTIMATE): 0.3-0.8 s corner-exit combined slip; 0.2-0.5 s load sensitivity; 0.4 s/stint thermal degradation.

### 3.3 Aero — ride-height map (TARGET)
- Today: Cl 1.65, Cd 0.70, balance 46% fixed at every speed and ride height.
- Build: 5x5 front/rear ride-height downforce map; Cd(Cl, yaw); front/rear balance map; ±4° yaw; DRS 2 states; dynamic ride height.
- Why: at Spa, 10 mm of rear ride height moves aero balance ~1.5% and the lap ~0.15 s. Values populated from CFD/wind-tunnel data, certified per track. This is the cheapest large accuracy gain in the chain and the first thing a paying team will test.

### 3.4 Track (TARGET)
- 1 m elevation, 5 m centerline, banking, kerb height, grip variation per sector.
- Library: 12 laser-scanned circuits, GPS import, and a **track QA badge** stating source and resolution.
- Cost of today's 19 stations: 6.2% grade instead of 13% through Eau Rouge removes ~0.2 s of signal.

### 3.5 Driver — OCP (TARGET)
- Today: quasi-steady-state assumes the car is on the friction limit everywhere, transitions free. This is the largest single error term.
- Build: minimum-time optimal control over the full lap (not greedy corner-by-corner); braking-point search with tire-work and lock-up limits; trail-brake blend; steering-rate limits; repeatability noise → report a lap-time **distribution**, not one number.
- Expected effect at Spa: +1.2 to +2.0 s.

### 3.6 Error budget (HYPOTHESIS, tested in Phase 0)

| Term | ESTIMATE |
|---|---|
| No driver model | +1.8 s |
| Optimistic tire | +1.2 s |
| Single-point aero | +0.9 s |
| No thermal degradation | +0.4 s |
| Coarse elevation | +0.2 s |

Start 2:11.043 → end 2:15.5 (matches the audit band). **Phase 0 rule: any term that fails its test is removed from the budget and the target is revised. We do not keep a number because it is convenient.**

## 4. Truth layer

### 4.1 Conservation Budget Engine
- Computed once per run, stored, rendered as a corner strip plus a ranked list. The list sums to the delta ± 0.001 s.
- Each row expands into the sensitivity that justifies it, with units and the run ID.
- Output shape: "Change this first": subsystem, delta, concrete change, confidence (e.g. "3 of 3 runs agree").

### 4.2 Sensitivity Engine
- 31 inputs x 40 outputs = 1,240 derivatives per run (lap time, 3 sectors, 19 corner times, 6 KPIs), ranked in ~0.8 s by adjoint. Finite differences would need 31 extra solves (~46 s).
- Validation gate: every derivative checked against a central difference on 5 random inputs; max error 2% or the run is flagged.
- UI: sorts sliders by influence, greys out inputs that cannot matter at this track, pre-fills the optimizer's search box.

### 4.3 Constraint checker
- Legal constraints: front/rear ride height, plank wear, tire temperature window, brake temperature, fuel, and a weekend setup-change budget. Designs outside limits are **excluded, not penalized**.

## 5. Correlation (in ApexSim, not a separate page)

Six steps, one workspace:
1. **Ingest** — MoTeC, AiM, CSV; auto-map 24 channels.
2. **Health** — dropouts, drift, units, rate.
3. **Align** — distance-based, 1 m grid.
4. **Compare** — speed, throttle, brake, steer, GPS.
5. **Calibrate** — fit 6 parameters to the logged lap.
6. **Accept** — state the tolerance or refuse the label.

Target output: R² ~0.94, RMSE ~0.042 s, per-corner residual strip (sim minus logged). Gated on decision 0.2 (the recruited team's logged Spa lap: speed, throttle, brake, steer, GPS).

## 6. Stint simulation (TARGET)
- 30 laps: fuel burn, tire degradation, track evolution, pit window. One state per lap carried forward → a curve with a confidence band, not a single number.
- Model estimate: 100 kg fuel, 3.33 kg/lap, 0.03 s/lap fuel gain, 0.06 s/lap tire loss, 22 s pit loss → net +0.03 s/lap degradation, optimal stop lap 14.
- The optimizer consumes the stint curve: "fastest lap" and "fastest race" stop being the same objective.

## 7. Setup optimizer (TARGET)

| | Today | 2.0 |
|---|---|---|
| Parameters | 2 | 24 |
| Constraints | 0 | 6 |
| Designs | 25 | 500 |
| Wall time | 21-51 s | 6 min |
| Output | one point | quali / race / wet weekend plan |

Weekend plan output: three setups, the trade between them in seconds, and the two changes that buy the most per minute of garage time. Surrogate: 625-point surface from a 48-run surrogate, ≤ 3 s and R² ≥ 0.98 vs the full solver.

## 8. Twin Replay
- Synchronized sim-vs-logged replay: 3D ribbon is the track, shared cursor, delta trace per corner. Sync to distance or time; swap reference lap; export the frame as evidence.
- **Reuse:** the Sprint 2 `LandingHero3D` double-wishbone geometry and material language are the same mesh Twin Replay and the car inspector use. Build once.

## 9. Evidence pack and API
- Report generated from the same registry the UI reads, so the PDF cannot drift from the screen. Every number carries a run ID.
- Endpoints:
  - `POST /v1/apexsim/runs` `{track, car, setup, elevation}`
  - `GET /v1/apexsim/runs/{id}/budget` `{delta, terms[], check, provenance[]}`
  - `GET /v1/apexsim/runs/{id}/report.pdf`
- Auth: per-team keys, 60 runs/hour, signed report URLs, audit log.
- Note: per decision 0.3 these ship inside the existing app and subscription; no separate SKU gating for now.

## 10. AI engineer grounding
- Structural rule: the model gets a tool that returns registered numbers, and nothing else. **No citation, no sentence.** If the registry has no number, the answer is a refusal plus the missing input.
- Can: read the run registry, budget, residuals, sensitivity table; explain, rank, draft a debrief, propose the next three runs (queued for approval, never written directly).
- Cannot: invent a lap, channel, temperature or source.
- Test: 40 adversarial prompts with missing data. Pass = 40 refusals, 0 invented numbers, every number traceable.

## 11. Build plan: 12 weeks, 6 workstreams, 4 gates

```
W1-2    Phase 0: measure (error-budget tests; can cancel terms)
W3-6    Vehicle + tire + aero kernels
W5-8    Track + driver kernels
W6-9    Budget + sensitivities
W8-11   Correlation + calibration
W9-12   Stint + optimizer + shell polish
```

| Gate | Week | Pass criterion |
|---|---|---|
| G1 | 6 | Correlation ≤ 0.5 s on one real car |
| G2 | 8 | Budget sums ±0.001 s on 100 runs |
| G3 | 10 | 625-point surface ≤ 3 s, R² ≥ 0.98 |
| G4 | 12 | API p95 < 300 ms, evidence pack signed |

No gate is a demo: each is a number that passes or stops the next workstream. Twelve weeks assumes one full-time engineer plus Omar on data and access.

**Kill criterion:** if G1 fails at week 6 and no data path exists, ship the visual and correlation work as Studio features and stop the flagship tier work.

## 12. Sprint 2 → ApexSim 2.0 handoff

Sprint 2 (visuals, shipping now) is the surface of ApexSim 2.0:

| Sprint 2 item | Why it matters to ApexSim |
|---|---|
| 3D double-wishbone hero on `/` | Reusable geometry/materials for Twin Replay and the car inspector |
| Spa elevation ON by default, larger viewport | Immediate visual proof of the track kernel (ribbon currently fills ~15% of its panel) |
| Footprints/attitude + MR heatmap surfaced | Sets the ApexSim panel pattern: one idea, one number, one label |
| Single lime accent, zero orange | ApexSim is the product that must look like one brand |

**Do now:** all four; none touches the solver. **Do not do yet:** claim a new lap time, a new accuracy, or a new model in Sprint 2. The visuals change; the physics does not. Visual work now, physics claims later — the order matters for trust.

## 13. Acceptance protocol

| Test | Method | Pass | N |
|---|---|---|---|
| Lap correlation | 3 tracks x 3 cars x 10 logged laps | \|Δ\| ≤ 0.5 s, speed RMSE ≤ 2 km/h | 90 |
| Budget conservation | 100 random runs, sum the terms | error ≤ 0.001 s | 100 |
| Sensitivity accuracy | adjoint vs central difference | max error ≤ 2% | 5/run |
| Setup surface | 625 points vs full solver | ≤ 3 s, R² ≥ 0.98 | 625 |
| Stint model | 30 laps, two compounds | monotonic within noise | 4 stints |
| AI grounding | 40 adversarial prompts | 0 invented numbers | 40 |
| API | 1,000 requests, 10 concurrent | p95 < 300 ms | 1,000 |
| UI | 390 px and 1440 px, all routes | no overflow, Lighthouse ≥ 90 | 24 routes |

The honest definition of "100%": the lap matches the car inside a stated tolerance, the budget explains every tenth, and the team can defend both in a debrief.

## 14. Top risks (from the dossier register)

- **Tire data access (High):** mitigated by decision 0.1 (FSAE TTC / published, labeled per run).
- **No correlation car (High):** mitigated by decision 0.2; without one logged Spa lap the 0.35 s target cannot be proven.
- **Solver speed (Medium):** 14-DOF at 500 Hz may not hit 0.5 s/lap on Vercel CPU → vectorize, cache the track, worker with a warm pool.
- **Claim discipline (High):** provenance registry plus a review checklist on every visible string.
- **Scope creep (Medium):** the six workstreams and four gates are the contract; nothing else enters. Not in scope: CFD, FE tire models, OEM programs, driver biometrics, full race strategy.

## 15. Sources

Live app `/lap-sim`, `/correlation`, `/pricing` (27 Nov 2026); audit of the deployed build (27 Nov 2026, build f53b5d0); ChassisSim Online ($5/simulation) and OptimumLap (free, ~10% accuracy) as market references, read 27 Nov 2026. Charts in the source dossier labeled schematic/illustrative show shape, not measured data; targets are engineering estimates with a test attached (section 13).
