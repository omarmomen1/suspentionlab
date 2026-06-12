# E2E Test Infra: SuspensionLab Pro

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + BVA + Pairwise + Workload Testing.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Quarter Car Simulation | ORIGINAL_REQUEST R2 | 5      | 5      | ✓      |
| 2 | Full Car Simulation | ORIGINAL_REQUEST R2 | 5      | 5      | ✓      |
| 3 | ISO Compliance Reports | ORIGINAL_REQUEST R2 | 5      | 5      | ✓      |
| 4 | CAE Exports | ORIGINAL_REQUEST R2 | 5      | 5      | ✓      |
| 5 | Live Sessions | ORIGINAL_REQUEST R2 | 5      | 5      | ✓      |

## Test Architecture
- Test runner: `npx playwright test` (run from root or `frontend/` directory, usually `frontend/` for Next.js, but need to configure to work seamlessly)
- Test case format: Playwright test files in `e2e/` or `tests/e2e/`.
- Expected output format: Exit code 0, standard Playwright reports.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Complete workflow: run Quarter car sim, export CAE, generate ISO report | F1, F3, F4 | High |
| 2 | Live collaborative tuning of Full car sim | F2, F5 | High |
| 3 | Stress testing: multiple rapid CAE exports during a live session | F4, F5 | Medium |
| 4 | Generating ISO reports for edge-case full car simulation parameters | F2, F3 | Medium |
| 5 | End-to-end suspension tuning lifecycle (Sim -> Tune -> Sim -> Report) | F1, F2, F3 | High |

## Coverage Thresholds
- Tier 1: ≥5 per feature
- Tier 2: ≥5 per feature (where boundaries exist)
- Tier 3: pairwise coverage of major feature interactions
- Tier 4: ≥5 realistic application scenarios
