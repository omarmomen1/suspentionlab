# Scope: E2E Test Suite Creation

## Architecture
- Framework: Playwright (`@playwright/test`)
- Target: Next.js frontend (`c:\Users\omaar\Downloads\project\frontend`) and FastAPI backend.
- Storage: Tests placed in `c:\Users\omaar\Downloads\project\e2e\`

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Setup & Tier 1 | Install Playwright, config, write Tier 1 tests (25 tests) | none | DONE |
| 2 | Tier 2 | Write Tier 2 boundary/edge-case tests (25 tests) | M1 | DONE |
| 3 | Tier 3 & Tier 4 | Write Tier 3 (pairwise) and Tier 4 (scenarios) (10 tests) | M2 | DONE |
| 4 | Finalize | Verify `npx playwright test` passes or fails correctly, publish TEST_READY.md | M3 | DONE |

## Interface Contracts
- Playwright tests should use `http://localhost:3002` (or whatever the app runs on, probably `3002` for frontend, `8001` for backend based on package.json/docker). Wait, `docker-compose.yml` likely defines the ports. Playwright should assume a base URL.
