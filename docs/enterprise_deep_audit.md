# Enterprise deep audit (consolidated): Pass 1, Passes 2/3, and the scoped security/physics audit

One consolidated audit file, as requested Nov 28. Audit only: no source files were changed to produce any part of this document, and nothing was executed against production by the code passes.

Contents and bases:
- **Part 1** — Live-app findings with code-level answers. Live report from the deployed app (Nov 27, 5:48 AM); code read at `f53b5d0`.
- **Part 2** — Passes 2 and 3 (code) plus live-audit findings N1 to N32, each marked CODE / PARTIAL / CONTRADICTED / LIVE-ONLY. Code read at origin/master `f759115`.
- **Part 3** — Scoped audit of `/auth/*`, `tenancy.py`, `webhook_routes.py`, `share_routes.py`, and the core physics files (`lap_sim.py`, `handling_model.py`, `yaw_dynamics.py`, `full_car.py`, `half_car.py`). Code read at `f759115`. Includes the P0 `testuser@suspensionlab.com` login backdoor.

Note: Part 3's "NOT reviewed" remainder still applies; C++ and the secondary tire/helper files were out of scope everywhere.

---

## Part 1 — Live findings + code-level answers (base `f53b5d0`)


Sources: (a) the live-app audit agent report of 5:48 AM Nov 27 (deployed app, not re-run here); (b) code read in this repo at `f53b5d0`. Each row says which. Nothing was executed against the deployed app by the code pass. No product code was changed on this branch.
Line numbers are at f53b5d0.

### P0
| # | Live finding | Code root cause (read in code) |
|---|---|---|
| 1 | `/active` Run Skyhook fails with "cannot access local variable 'np'", raw Python error shown in the UI. | CONFIRMED in code. `backend/workers/unified_worker.py` `_run_job_async` (def at line 144) has local `import numpy as np` inside other branches (line 276 in `SIMULATE_FULL`, line 357 in a later branch). That makes `np` a local of the whole function. The `SIMULATE_ACTIVE` branch (starts ~line 305) uses `np.allclose` at line 334 and never imports it, so it raises UnboundLocalError. There is no module-level numpy import (module imports lines 1 to 11 are logging/time/json/asyncio/os/math/redis). Fix: one `import numpy as np` at module top and delete the local ones. The leak path: line 702 stores `f"Transient Error: {str(e)}"` in `JobRecord.error` and the UI shows it. Sanitize at that write (generic message plus job id, full detail to the log only). Not applied: audit only. |

### P1
| # | Live finding | Code finding |
|---|---|---|
| 2 | Quarter-car Save Setup closes the dialog, `/garage` shows 0, nothing in localStorage. | C5, NOT determined from code. Save: `app/quarter-car/page.tsx` line 196 to 210 does `fetchWithAuth("/api/v1/profiles/", POST {name, vehicle_type:"QUARTER_CAR", params})` and toasts "Setup saved to Garage!" on `r.ok`, else "Failed to save". Garage: `app/garage/page.tsx` line 58 does `apiFetch("/api/v1/profiles")` (a different helper, `lib/api.ts` line 83, vs `AuthContext.fetchWithAuth` line 254; both send cookies and X-CSRF-Token). Backend `api/routes/profiles.py` accepts both `""` and `"/"` for POST and GET, and the list filters `team_id == t_id OR user_id == u_id`, so a scope mismatch is possible only if team_id/user_id resolve differently between calls. Candidate causes to check live: (i) trial governance `TrialService.assert_trial_access(..., action="vehicle", delta=1)` at profiles.py line ~121 enforces a 1-vehicle trial limit and can return 4xx; (ii) the toast is a `fixed top-14 right-4` element removed after 3.5 s, so a quick error toast can be missed; (iii) the two fetch helpers resolve the API base differently (`resolveApiUrl` vs `normalizeApiUrl`). Check the network tab for the POST status. Also there is no localStorage write in this path by design. |
| 3 | `/durability` life 1.2 km, Miner D = 1.000 on all four parts, "Uncomfortable" at 1.108 m/s2. | C2, CONFIRMED. (a) Miner D is not a Miner sum: `app/durability/page.tsx` line 266 is `Math.min(1.0, Math.max(0.01, 100000 / Math.max(comp.life_km, 1000)))`. Any `life_km <= 100000` gives D = 1.000 exactly (life clamped to 1000 gives 100, clamped to 1). It is a display transform of life_km, not damage. (b) Life model is a placeholder: `backend/api/routes/durability_routes.py` lines 50 to 55 `COMPONENT_DATA` (m, ref_cycles, ref_rms per part, no S-N source), life = ref_cycles * (ref_rms/rms_body_accel)^m (lines 173 to 175), with body RMS acceleration used as the load proxy for every part, 1 cycle = speed / f_n_s metres (line 177), capped at 999,999 km (line 180). The spring exponent m = 8 turns a 3.7x RMS ratio into a factor of about 2.5e4, so 1.2 km is the formula, not a physics result. (c) VDV is not a VDV: line 131 `vdv = rms_accel_wk * duration**0.25 * 1.4`, an approximation, not the fourth-power integral. (d) Comfort bands (lines 134 to 150) use cut-offs 0.315/0.5/0.8/1.25/2.0 on `rms_accel_wk`. The label is chosen from the Wk-weighted RMS, so a 1.108 shown on screen is the unweighted `rms_body_accel` if the two differ: confirm which number the page prints. The 0.8 to 1.25 band is "Uncomfortable" in this code. The ISO 2631-1 Annex C ranges overlap (about 0.8 to 1.6 for "uncomfortable") and the code uses non-overlapping cut-offs, which is a simplification the UI should say. |
| 4 | Exported PDF: "Compliance Certificate / VERIFIED PROVENANCE" beside DEGRADED / HMAC NONE, VDV 0.01 next to RMS 6.31, "UNCOMFORTABLE" with "8-Hour PASS", fabricated R2 0.9945, placeholders, garbled glyph. | C3, CONFIRMED in `frontend/components/PDFExport.tsx`. Line 161: title "Authoritative Engineering Artifact & Compliance Certificate" is unconditional. Line 195: "VERIFIED PROVENANCE" is pushed into every footer unconditionally (only the solver/input-hash bits are conditional). Line 472: "Continuous Exposure 8-Hour Daily Limit: PASS . Crest Factor: 2.14 . Kurtosis: 3.08" is a hard-coded string, not computed. Line 473: "MAE: 1.41 mm . R2 Correlation vs Physical Rig: 0.9945" is hard-coded, though the same file elsewhere labels telemetry correlation "UNVALIDATED". Lines 300 to 310: the fallback metric table prints N/A for VDV and RMS, so the VDV 0.01 / RMS 6.31 pair comes from the passed `metrics` object (the durability VDV approximation above is about a wk-RMS of 0.0x times 20^0.25 times 1.4, which cannot match 6.31: the two values come from different runs or units, not verified). Line 90 default `setupRef = "REV-01"` (also report/page.tsx line 298 and 344, report/[token]/ReportClient.tsx lines 174 and 322, `report_routes.py` line 394, `report_service.py` line 525). Line 741 draws "●" with the built-in Helvetica font, which lacks that glyph (WinAnsi), which is the likely cause of the garbled "%Ï Simulated Operating Points". Aero, camber/toe and G-G sections come from a quarter-car run that has none of that data: not traced to a specific line. |
| 5 | MATLAB export disagrees with screen: .m f_n_s 1.2001, zeta_s 0.28238, omega_n_s 7.5407 vs screen 1.23 Hz, 0.318, 7.7593. | C1: NOT formula drift in the Python code, it is two different quantities with the same label. `physics/quarter_car.py` lines 427 to 461: `omega_n_s`, `f_n_s`, `zeta_s` come from the eigenvalues of the coupled 4-state system (sprung mode lam1: wn = abs(lam), zeta = -Re/abs). `c_crit_s = 2*sqrt(k_w*m_s)` (line 455) is the uncoupled value. So `zeta_s != c/c_crit_s` is expected, because the unsprung mass and tire stiffness shift the sprung mode. The on-screen 1.23 Hz / 0.318 / k_w 18063 are the analytical preview: sqrt(k_w/m_s) gives 7.7593 rad/s (= 1.2349 Hz, m_s = 300 kg) and c/c_crit gives 0.318. So the screen preview (uncoupled) and the solver/export (coupled) differ by design, but the UI labels both "sprung natural frequency / damping ratio". Not found: the code that writes `f_n_s` into the .m text. `backend/services/cae_exporter.py` `export_quarter_car_to_matlab` (line 371) emits only matrices and k_w/c_w. Locate the producer (likely a different export path) before claiming the values are consistent. Fix direction: label them "analytical (uncoupled)" and "solver (coupled eigenvalue)". |
| 6 | `/compare` and `/experiment` "WHAT GOT WORSE" explanations argue the wrong direction; SETUP B FAVORED next to UNVALIDATED, confidence 0.88. | Not traced in code in this pass. |
| 7 | `/experiment` "increase front roll stiffness by 10%" changes K_S. | C6, CONFIRMED. `app/experiment/page.tsx` lines 58 to 63: preset q1 is titled "front roll stiffness", subsystem "Front Suspension / Anti-Roll Bar", but `param: "k_s"` (spring rate, N/m). A real ARB parameter exists on the same page (`k_arb_f` "Front Anti-Roll Bar", line 87). The hypothesis text itself says "Stiffening front spring rate". The question is mapped by preset id, not parsed from the user's text: any typed question that matches the default string behaves the same. Fix: change q1 to `param: "k_arb_f"` only if the backend experiment route accepts it (not verified), otherwise retitle to "front spring rate". |
| 8 | `/lap-sim` at 390 px: two-pane layout persists, overlaps. | Live finding only. Not traced. |
| 9 | Trust contradictions across `/timeline`, `/audit`, `/investigate`, `/digital-twin`, `/evaluation`, `/nvh`, `/vnv`, `/setup-sensitivity`. | C4 only: the "ISO 16331 / DIN 70000" claim exists as a literal string in `app/vnv/page.tsx` lines 215 and 349 and in `physics/ai_engineering_authority.py` lines 714 to 718 and 1120, a report template header. No code in these paths validates anything against those standards. The "100% VERIFIED" claim was not traced. ISO 16331 and DIN 70000 are vehicle-dynamics/vehicle-geometry measurement standards, not a certification this code can award: treat as an unsupported claim until a source is shown. Other routes not traced. |
| 10 | Slow endpoints: lap-sim simulate 13.5 s, Why Chain about 10.6 s, durability about 25 s, no progress indicator. | Live timings. Durability simulates 20 s of ISO 8608 road in `_compute_durability` (line 103 onward, `duration = 20.0`), synchronous in the request. Not profiled. |

### P2
| # | Live finding | Code finding |
|---|---|---|
| 11 to 15 | `/cae` empty CSV no-op; quarter-car Export MATLAB inert before first run; `/parameter-trust` raw null; 390 px clipping on `/kinematics`, `/quarter-car`, `/handling`; `/sensitivity` optimum on grid edge. | Live findings only. Not traced in code in this pass. |

### Also found in code (not in the live report)
| # | Where | Finding |
|---|---|---|
| a | `app/lap-sim/page.tsx` line 2636 | Helper text "Other circuits stay flat (z = 0)" contradicts the new EmptyState for non-Spa. Copy fix. |
| b | `app/lap-sim/page.tsx` lines 1191, 1484 | Elevation defaults off and is only sent for `spa`. Making it default-on adds backend time on Spa (not measured). |
| c | `components/v2/instruments/TerrainElevation3D.tsx` | Spa profile has 19 altitude stations, not 17. |
| d | Why Chain | Runs on the backend default vehicle (decision by Omar: leave as is). |
| e | `app/full-car/page.tsx` | Four-corner Fz is rebuilt in the UI (full_car.py returns no per-corner series), using the run's k_t = 250000. |

### Verified clean (live report, not re-run)
27 routes return 200, Ctrl+K palette, invalid license key rejected, Gumroad link 200, `/api/v1/trust` real, `/solver-interop` honest, onboarding flow, `/yaw-dynamics`, `/sensitivity`, `/experiment` runs plausible.

### Not covered
Every route in the Track 1 list was not clicked through by the code pass. Rows marked "not traced" need a code read. The 81-file physics units/sign sweep was not done.

---

## Part 2 — Passes 2 and 3 (code) plus live audit N1 to N32 (base `f759115`)


Audit only. No source files were changed. Code read at origin/master f759115 (paths under `src/suspensionlab/backend/` unless stated).
Nothing here was run in a browser, WebGL, C++ or against production. "Code-verified" means I read the code. Live findings (N-numbers) come from the live-audit agent's report; I checked what I could against code and say so for each.
Pass 1 is in `docs/enterprise_deep_audit.md` and is not repeated.

### P0

| # | Finding | Where | Fix |
|---|---|---|---|
| A1 | SAML account takeover. User is linked by email only. An existing user (any tenant) is moved into the IdP's org, `auth_provider="saml"`. No check that the user is already in that org or that the IdP owns the email domain. | `api/routes/saml_routes.py:135-160` | Only auto-link inside the same org, or when the org has a verified domain claim matching the email domain. Never reassign `organization_id` on login. |
| A2 | SAML signature wrapping risk. Hand-rolled XMLDSig verifies the first `ds:Signature` anywhere (l.299). Digest target is the `@ID` match, else the first Assertion or root (337-339). The consumer reads `root.find(".//Assertion")` (l.451), which is not tied to the signed element. A missing Reference or DigestValue skips the digest check (327-330). Reference URI is interpolated into an XPath string (337). sha1 and rsa-sha1 are accepted (318-320, 347-348). Transforms and c14n method ignored. Two parsers (lxml verifies, defusedxml validates). | `security/saml.py:267-352, 451` | Replace with python3-saml or signxml. Minimum: require exactly one Signature, require a Reference, and consume only the element whose ID the Reference points to. Reject SHA-1. |
| A3 | Experiment service can return fabricated regression results (pass 2). | see Pass 2 recap | see pass 2 |

(A3 and the other pass 2 items were reported at 10:19 PM and are listed under "Pass 2 recap" below.)

### P1

#### Billing and entitlements
| # | Finding | Where | Fix |
|---|---|---|---|
| B1 | No Gumroad webhook/ping and no re-verification. A refunded or charged-back key stays PRO/ENTERPRISE forever. | `api/routes/gumroad_routes.py` (no handler) | Add Gumroad ping endpoint (verify seller id), or periodic re-verify, and downgrade on `refunded`/`chargebacked`. |
| B2 | Reuse check is dead code. The verify call sends `increment_uses_count: "false"` so `uses > 1` (~l.189) never fires. Only the DB unique `uq_users_gumroad_license_key` protects (`database/models/user.py:40`, alembic `b2c3d4e5f6a1`). Select-then-write (~l.164) is not atomic; a race gives a generic IntegrityError. | `gumroad_routes.py:99-112, ~164, ~189` | Rely on the constraint, catch IntegrityError and return a clear 409, delete the dead check. |
| B3 | Stripe webhook swallows commit failures. Final `try: commit / except: rollback` then `return {"received": True}`. Stripe never retries, so a paid upgrade can be lost. | `api/routes/billing_routes.py` (end of `/webhooks/stripe`, from l.74) | Return 500 on commit failure so Stripe retries. |
| B4 | `StripeEvent` is recorded (~l.123) before processing; unknown-user events (webhook before `billing_customer_id` stored) are marked processed and the plan is never applied. | `billing_routes.py:~123` | Record the event in the same transaction as the effect; for unknown users return 500/defer. |
| B5 | Plan granted without checking `obj.status` (`past_due`, `unpaid`, `incomplete`) or `payment_status`. | `billing_routes.py` (subscription.created/updated, checkout.session.completed) | Grant only on `active`/`trialing` and `paid`. |
| B6 | `checkout.session.completed` stores the session id (`cs_...`) as `billing_subscription_id`. | `billing_routes.py` | Store `obj.subscription`. |
| B7 | No ordering guard (`event.created`): a stale `updated` after `deleted` can resurrect a plan. | `billing_routes.py` | Store last-applied event time per user and skip older events. |
| B8 | `subscription.deleted` sets FREE unconditionally, overwriting a Gumroad or SLPRO entitlement. Downgrade block is duplicated with a dead nested `if user:`. | `billing_routes.py` | Only downgrade if the plan source is Stripe. Track entitlement source. |
| B9 | No handlers for `invoice.payment_failed`, `charge.refunded`, `charge.dispute.*`. | `billing_routes.py` | Add handlers. |
| B10 | `detail=str(e)` on signature failure leaks error text. Price IDs read from env at import (l.20-22). | `billing_routes.py:20-22, ~89` | Generic 400. Read settings lazily. |

#### Auth
| # | Finding | Where | Fix |
|---|---|---|---|
| C1 | JTI revocation fails open. Any Redis exception returns False (code-verified). In-memory registry is per process. | `security/jwt_utils.py:165-179` | Fail closed for revoked-token checks on sensitive routes, or keep a DB revocation fallback. |
| C2 | Legacy `User.api_key` lookup accepts both `sha256(key)` and the plaintext key. Plaintext keys may be stored. Hash is unsalted SHA-256. | `security/auth.py:409-420` | Migrate to hashed-only, drop the plaintext branch. |
| C3 | CSRF double-submit compared with `!=`, unsigned, not session-bound; only for cookie auth. | `security/auth.py:196-210` | `hmac.compare_digest`, bind to session. |
| C4 | Licence keys are signed with the JWT secret. A JWT secret leak forges licences; rotating JWT keys invalidates every issued licence. | `security/license_keys.py:88-103` | Separate licence signing secret. Callers of `secret_override` not checked. |
| C5 | SAML `return_to` HMAC uses the JWT key (key reuse). `saml_routes.py:133` returns `SAML Assertion validation failed: {exc}`. | `saml_routes.py:133` | Separate key, generic error. |
| C6 | `optional_verify_api_key` makes `/vnv/run` anonymous (pass 2). | `security/auth.py:494-507` | Require auth. |

#### Live-audit findings (N1 to N32) with code checks
Status key: CODE = confirmed in code, PARTIAL, CONTRADICTED, LIVE-ONLY = not checkable in code, not verified by me.

| N | Sev | Summary | Code check | Fix |
|---|---|---|---|---|
| N1 | P1 | /digital-twin is hard-coded demo data labelled MEASURED (DAQ) | PARTIAL: `AMR24-EVO` found only in `frontend/tests/telemetryDigitalTwinTimeline.test.ts`; `3820.2` in `frontend/app/cae/page.tsx:57` is sample CSV. Page source not located by my grep. | Replace with EmptyState until DAQ is loaded, or label "SAMPLE". |
| N2 | P1 | /investigate fixed story, two confidence numbers | CODE: `frontend/app/investigate/page.tsx:357` hard-codes `confidence={0.88}` with source "Active Telemetry R²". | Remove or drive from real data. |
| N3 | P1 | Four unrelated correlation numbers | LIVE-ONLY (partly CODE as N2) | Single source of truth, or EmptyState. |
| N4 | P1 | Best Compromise uses unnormalised distance | CONTRADICTED for the backend: `physics/pareto_optimizer.py:257-275` min-max normalises before the distance. The live agent may be reading page text only. Not verified which path /optimize shows. `pareto_optimizer.py` must not be edited (frozen). | Ask live agent to re-check by comparing against the backend response. |
| N5 | P1 | /optimize re-runs 36 sims on load | LIVE-ONLY; `api/routes/optimize.py:175,230` uses `bounded_run`. | Cache or run on button click. |
| N6 | P1 | Usage meter shows 0/500 | CODE (cause): the counter is incremented only inside `inline_compute_guard` (`core/compute_governance.py:~249`, used by 13 routes); `get_monthly_usage` returns 0 when Redis is down or errors (l.139-150); the guard skips everything when Redis is None (l.217+). Routes not using the guard (half_car and full_car use `bounded_run`) are never counted. Quota is not enforced without Redis. | Count in one place, add a DB fallback, fail visibly. |
| N7 | P1 | Report narrative canned, 4500 Ns/m never evaluated | LIVE-ONLY (template not located) | Generate text from the actual result. |
| N8 | P1 | Studios use private defaults; aero 56 N vs Cl 1.65 | PARTIAL: `physics/lap_sim.py:378,429` Cl 1.65 default. | One workspace vehicle for all studios. |
| N9 | P1 | /yaw-dynamics default 216 km/h on 60 m radius | LIVE-ONLY (default not located) | Add lateral-g limit check, default about 100 km/h and R 100 m. |
| N10 | P1 | /handling Kus plot past peak grip, KPI flicker | LIVE-ONLY | Cut at peak, hide interim values. |
| N11 | P1 | Kinematics PASS with 4/5 benchmarks | CODE: `frontend/components/kinematics/KinematicsModelValidity.tsx:196` prints the benchmark count separately from the status badge. | Derive the badge from the count. |
| N12 | P1 | Identical setups show GOOD 100% | LIVE-ONLY (string not located) | "No change" state. |
| N13 | P1 | Expired sessions listed as active | LIVE-ONLY | Filter by expiry, purge. |
| N14 | P1 | Session-expired modal mid-session | LIVE-ONLY | Test state survives. |
| N15 | P1 | Enterprise CTA with no Enterprise tier; tier gating inconsistent | CODE: `frontend/app/settings/page.tsx:597` "Upgrade to Enterprise". | Remove or link to contact sales. |
| N16 | P2 | /audit verify 403 but "LAST VERIFIED: Just now" | LIVE-ONLY | Show the real state. |
| N17 | P1 | /docs and /openapi.json 404 | CODE (by design): `api/main.py:99-101` sets `docs_url/redoc_url/openapi_url=None` when `is_prod_or_trial`. The frontend docs (`frontend/app/docs/page.tsx`) still tell users interactive docs exist. | Fix the text or publish a static OpenAPI. |
| N18 | P2 | Three error shapes | PARTIAL: custom handlers in `api/exceptions.py`. | One shape. |
| N19 | P2 | Validation runs before auth | PARTIAL: `api/exceptions.py:32` handler echoes input. | Auth dependency first, do not echo input. |
| N20 | P2 | CORS preflight 405 | LIVE-ONLY. Pass 2 covers the CORS regex. | Review the CORS config. |
| N21 | P2 | No security headers on studio HTML | PARTIAL: the backend has `security_headers_middleware` (`api/main.py:147`) but that only covers API responses. `frontend/next.config.mjs` has no `headers()` and there is no `vercel.json`. | Add headers in next.config. |
| N22 | P2 | Docs say RK45 for stiff systems | CODE: `frontend/app/docs/page.tsx:238`. Quarter-car uses BDF (`physics/quarter_car.py` header). | Fix the text. |
| N23 | P2 | Docs half/full-car equations are placeholders | LIVE-ONLY | Write them or remove. |
| N24 | P1 | Privacy policy names Railway, not Vercel | CODE: `frontend/app/legal/privacy/page.tsx:51` lists Railway; no Vercel mention found. | Legal review. |
| N25 | P2 | LLM provider not disclosed | LIVE-ONLY | Add to the policy. |
| N26 | P2 | Same title on every route | CODE: `frontend/app/layout.tsx:24` sets one title. Nested `<main>`: `layout.tsx:57` and `kinematics/page.tsx:1211`. | Per-route `metadata`, one main. |
| N27 | P2 | Unlabelled controls, no autocomplete | LIVE-ONLY | aria-labels. |
| N28 | P2 | Mega-menu rendered about 4 times | LIVE-ONLY | Render once. |
| N29 | P2 | Mobile 390 clipping | LIVE-ONLY (390 px layout never verified by me either) | Fix header wrapping. |
| N30 | P2 | /cae roadmap jargon, private defaults | PARTIAL (`cae/page.tsx` sample CSV) | Remove jargon. |
| N31 | P2 | Spa 7004 vs 7003 m | CODE: `frontend/app/lap-sim/page.tsx:194`, `contexts/WorkspaceContext.tsx:186`, `physics/lap_sim.py:1230` all say 7004. The "7003" caption was not found in code (may be computed). GT3 lap-time realism: live agent's recall, not verified. | Find the computed caption. |
| N32 | P2 | Garage/Save Setup never write storage | LIVE-ONLY | Wire or hide. |

#### Rate limiter (hypothesis, not verified in prod)
| # | Finding | Where | Fix |
|---|---|---|---|
| R1 | Anonymous requests keyed by `request.client.host`. Defaults `trusted_proxy_hosts=127.0.0.1,::1` (`config.py:102`) with `ProxyHeadersMiddleware` (`api/main.py:116-119`); frontend rewrites `/api/*` to `BACKEND_URL`, so the API may see the proxy IP. If `TRUSTED_PROXY_HOSTS` is not set in prod, all anonymous users share one bucket (login 15/min for everyone). | `security/rate_limit.py`, `config.py:102` | Check the deployed env. |
| R2 | In-memory fallback is per process, so not a global limit on serverless (`rate_limit.py:29-60`). | same | Redis required. |

### P2

#### Migrations (`alembic/versions`, 42 files)
- Single head `z88a0b1c2d3e`, single root `7e44398ceef5`, one branch point at `u1v2w3x4y5z6` (single head implies it was merged).
- `743884f94247_lemon_squeezy_migration.py:29` does `DROP TABLE IF EXISTS user_api_keys` in upgrade (data loss, no restore in downgrade).
- `31ab9076ca94_enterprise_remediation.py:166-349` downgrade drops `billing_customer_id`, `billing_subscription_id`, `deleted_at` columns and the `stripe_events` table (rollback loses data).
- RLS (`database/rls.py`, `z86a0b1c2d3e_...`): ENABLE and FORCE with `current_setting('app.current_*', true)` NULLIF. Fails closed when unset. `app.is_super_admin='true'` is a full bypass, so every setter is sensitive. Callers of `set_session_tenant_context` not audited.
- Not verified: whether `uq_users_gumroad_license_key` is applied in the deployed DB.

#### Physics (`physics/magic_formula.py`, finished)
- Default coefficients are in published MF5.2 ranges (pCy1 1.30, pCx1 1.60, pKx1 22, pKy1 15 normalised with `abs()` at l.366, pKy2 2.0, pDy2 -0.10, pEy1 -0.5). The Ky form peaks at Fz=pKy2*Fz0 as in Pacejka.
- Defaults are road-tyre scale (Fz0 4000 N, mu 1.05-1.10). FSAE tyres are about 1000-1200 N nominal and mu about 1.8-2.4. Defaults mislead unless a `.tir` is loaded. Flag only.
- Camber terms are tiny (pDy3 0.05, pVy3 +0.08). Standard files often carry a negative pVy3, so camber-thrust sign depends on the axis convention. Not checked against a sample `.tir`.
- Friction-ellipse guard (l.395-410) caps at `max(mu_x, mu_y)` and ignores anisotropy. Gxalpha/Gykappa clamped to [0,1]. Ex/Ey clamped to 0.999.
- Performance: `physics/active_quarter_car.py:13-14` and `half_car.py:404-410` build `np.array([t])` and call the road function on every RHS evaluation. `solve_ivp max_step` is duration/5000 (`active_quarter_car.py:82`, `quarter_car.py:964`), 0.01/0.005 (`half_car.py:477,490`), 0.05 (`handling_model.py:899`). 32 `to_thread` uses against 395 async handlers; I did not check which routes run heavy solves inline. No timings were run.

### Pass 2 recap (already reported; details in the 10:19 PM report)
Experiment-service fabricated regressions; `/approve` with client-supplied approver; CORS regex; signature scope; client-asserted validity flags; `/vnv` anonymous bypass; `active_quarter_car` has no `sol.success` check; `handling_analysis` default roll-centre heights; NVH dBA claim; committed binaries; test and code-quality counts.

### NOT reviewed
`tire_thermal.py`, `tire_fitting.py`, `tire_enveloping.py`, `tire_model.py` coefficient review; `lap_sim.py`, `dynamic_lap_sim.py`, `yaw_dynamics.py`, `handling_model.py`, `load_transfer_dynamics.py`, `anti_geometry.py`, `damper_model.py`, `half_car.py`, `full_car.py` units and signs; kinematics sign flip beyond the known C++/Python one; `webhook_routes.py`, `share_routes.py`, `report_routes.py`, `twin_routes.py`; `idempotency.py` body-hash logic; `/auth/*` enumeration and lockout; `tenancy.py` caller coverage; C++; every browser, WebGL and mobile claim; production environment values.

---

## Part 3 — Scoped audit: security/tenancy and core physics (base `f759115`)

SCOPED AUDIT RESULT (code-only, origin/master f759115, nothing edited, nothing run live). Paths are under src/suspensionlab/. I read the code; I did not test any of this against production. Two findings are marked hypothesis.

SECURITY AND TENANCY (P0/P1)
| Sev | File:line | Finding | Exact fix |
|---|---|---|---|
| P0 | backend/api/routes/auth_routes.py:354-361, 369-372, 382-386 | Hard-coded backdoor in /auth/login for testuser@suspensionlab.com. If the account is missing, ANY password creates it as a PRO account. If it exists, five known passwords ("SuspensionLab2026!#", "TestPass123!", "password123", "Testuser123!", "Password123!") are accepted. Every login forces plan=PRO. No env gate. The password strings sit in a public-facing code path. This is also why the live agent's test account works. | Delete all three blocks. Seed a test user in a fixture or migration, or gate it behind `settings.environment != "PROD"`. Rotate that account's password and review that user's data. |
| P1 | auth_routes.py:230-257 (/reset-password) | The reset token is an access-type JWT with type=password_reset. The endpoint never calls `_is_revoked`, and the jti is blacklisted only after use, so the same link can be replayed for up to 1 hour. No rate limit on this route. `ResetPasswordRequest.new_password` (l.207-209) has no min_length (register requires 12). A reset does not revoke existing sessions or refresh tokens. No `deleted_at` check (l.246). | Check `_is_revoked(payload["jti"])` before applying. Add `Depends(RateLimiter(...))`. Use `Field(min_length=12, max_length=128)`. On reset, delete all UserSession rows and blacklist the user's refresh jtis. Filter `User.deleted_at.is_(None)`. |
| P1 | auth_routes.py:343-360 vs security/rate_limit.py:154-195 | Lockout is keyed `login_failures:{email}:{ip}`. A distributed attacker (or anyone rotating IPs) never reaches the 5/10/20 thresholds, and there is no per-account counter. If Redis is down, both `record_login_failure` and `check_progressive_penalty` return silently (fail open). Hypothesis: if the proxy-IP issue from pass 3 is real, the key collapses to one IP per email and the lockout becomes a denial of service. | Add a second counter keyed on email alone (e.g. 20 per 15 min), and fail closed on Redis errors for login. |
| P1 | auth_routes.py:262-268, 299-300 | Account enumeration: /register returns 409 "An account with this email already exists" (twice). /login is generic, good. /forgot-password is generic, good. | Return the same response for register (email the existing owner), or accept it and rate limit. |
| P1 | auth_routes.py:344-420 | /login has no `User.deleted_at` check, so a soft-deleted user can still sign in (/onboard at l.611 does check it). | Add `.where(User.deleted_at.is_(None))` in the lookup. |
| P1 | auth_routes.py:86-110 (/refresh) | No check that the user still exists or is not deleted. The refresh token's `plan` claim is copied forward, so the plan can go stale. No reuse detection: a rotated (revoked) token is only rejected, with no family kill. Rotation blacklists the old token before the new one is persisted (non-atomic). | Load the user and reject if missing or deleted. Take the plan from the DB. If a revoked refresh token is presented, revoke all of that user's sessions. |
| P1 | backend/database/rls.py:~197-215 (`set_config(..., true)`) and security/auth.py:266, 366, 443 | HYPOTHESIS on the deployed role. Tenant context is set only inside `verify_api_key` (3 call sites, nowhere else) with is_local=true (transaction-local). After any `db.commit()` or rollback in the handler, the context is gone for later queries in the same request. With a non-BYPASSRLS role this fails closed (empty results); with a superuser or BYPASSRLS DB role the RLS policies do nothing and only app-level filters protect tenants. Public routes (share GET, login, register) have no context at all. | Verify the prod DB role is NOLOGIN-owner plus a restricted app role without BYPASSRLS. Re-apply context after commit with a `SessionEvents.after_begin` hook, or set it in `get_db_dependency`. |
| P1 | backend/security/tenancy.py:99-100, auth.py:271, 449 | `is_admin=True` returns `true()` (full bypass) in `get_tenant_filter`, and maps to `app.is_super_admin='true'` in RLS for every org. `User.is_admin` has no setter in code, so it is DB-only. That is fine, but any one admin sees all tenants. No audit log on admin access. | Log admin cross-tenant reads. Prefer a separate admin role and audit trail. |
| P1 | backend/services/webhooks.py:40-81 and 90-101 | SSRF DNS-rebinding TOCTOU: `validate_webhook_url` resolves the host, then httpx resolves it again at send time. The returned `safe_ip` is never used. `ALLOW_PRIVATE_WEBHOOKS=true` env turns the whole check off. Redirects are blocked (good). Blocking `getaddrinfo` also runs inside an async path. | Resolve once, connect to the pinned IP with a Host header (or an httpx transport with a custom resolver). Use `ip.is_global` as the allow rule. Refuse to start in PROD if ALLOW_PRIVATE_WEBHOOKS is set. |
| P1 | backend/api/routes/share_routes.py:239-244 (legacy path, l.226-243) | Any user with REPORT_SHARE can POST arbitrary `params` and `result`; the server computes the hashes and HMAC-signs them. The public GET then reports `payload_verified=True` and `signature_valid=True`. A fabricated report carries a valid server signature. Provenance is a separate field, but the signature badge is not conditioned on it. | Remove the legacy path, or sign with a `provenance="client_asserted"` bound into the HMAC and never show signature_valid=True for it. |
| P1 | share_routes.py:313-363 | The public GET returns the full params, result, `approved_by_email`, approval comment and signature to anyone with the token. Error text says "or has expired" but there is no expiry check. There is no revoke/delete route in this file (only POST /share and GET /{token}). Anonymous GET also writes view_count with no rate limit. | Add `expires_at` and a DELETE route (owner only). Redact `approved_by_email` and PII in the public response. Rate-limit the GET. |
| P1 | backend/api/routes/webhook_routes.py:109, 123 | `_uuid.UUID(endpoint_id)` on bad input raises, so the user gets a 500 instead of 404/422. Ownership scoping (user_id) is correct, so there is no IDOR. Secrets are stored plaintext (`ep.secret`). | Type the path param as `uuid.UUID`. Store the secret encrypted or hashed-with-pepper. |
Checked and OK: webhook and share access control is scoped by owner id. /auth/me and /status rate limited. Cookies are httponly/lax.

CORE PHYSICS (units, signs, fallbacks, sol.success)
| Sev | File:line | Finding | Exact fix |
|---|---|---|---|
| P1 | physics/handling_model.py:136-138 vs physics/lap_sim.py:378,429 | Spec/code conflict (this is N8's root cause). The handling default aero is C_l=0.1, frontal_area=2.2, which gives about 104 N total at 100 km/h (matches the 56+48 N seen live). The lap sim defaults to C_l=1.65, which gives about 1.5 kN at the same speed. Flag, not changed. Same car, 15x different downforce, so lap time and handling disagree. | One shared vehicle params object. If the handling default is meant to be "no aero", label it so in the UI; otherwise use the workspace aero. |
| P1 | physics/yaw_dynamics.py:302-325 (`_derivatives`), 360+ (`simulate_corner`) | The transient bicycle model is linear: Fyf = Cf*alpha, Fyr = Cr*alpha, with no saturation, while `compute_mmm` clips at Fy_lim (l.234-235). At the 216 km/h on 60 m default it reports "required steer 5.23 deg, settled 0.75 s" for about 6 g (impossible). Confirms N9. | In `simulate_corner`, compute ay = v^2/R and return an "infeasible" flag if ay/g > mu_peak*(1+aero). Clip Fy to mu*Fz in `_derivatives`. |
| OK | yaw_dynamics.py:126-138, 199-207 | The K_us formula m/L(b/Cf - a/Cr)*g*180/pi is correct, and the beta/r equations and signs are standard (d_beta = Fy/(m v) - r). | none |
| OK | physics/full_car.py:657-658, half_car.py:479-495, handling_model.py:902-904 | `sol.success` is checked (raise, or retry with BDF in half_car). `converged=sol.success` is also returned. | none |
| OK | all five files | No `except Exception` fallbacks and no hard-coded fallback numbers found in yaw_dynamics, handling_model, full_car, half_car. lap_sim.py has none either; its assumptions are declared as ModelAssumptions (l.2753+). The roll-centre 0.10/0.12 m fallback from pass 2 is in handling_analysis, not these files. | none |
Not found, not claimed: I did not trace sign conventions in half_car pitch / full_car roll in depth, nor lap_sim's cornering and braking solver beyond greps. A line-by-line review of those two was not done, so "no sign inversion found" means none surfaced in the greps and spot reads only.

Nothing committed. The pass 2 doc (727f1e6) is unchanged. If Omar wants this added to the doc, say so and I'll append it on sprint-2-visuals-prep (the earlier go-ahead covered the doc commit only).
