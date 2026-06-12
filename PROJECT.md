# Project: SuspensionLab Pro Hardening

## Architecture
- Frontend: Next.js + React
- Backend: FastAPI
- Deployment: Docker, docker-compose, GitHub Actions
- Strategy: Go-To-Market business strategy documentation

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | GTM Strategy | Generate go_to_market_strategy.md targeting OEMs/motorsport | none | IN_PROGRESS (70a85642-0df7-4764-9377-47d2baa5f655) |
| 2 | UI Polish | Add error boundaries, graceful loading, edge-case protections | none | IN_PROGRESS (d3617260-96ae-4b6b-9fa7-e4ba20a178df) |
| 3 | Backend Testing | Implement comprehensive pytest suite for FastAPI | none | IN_PROGRESS (63b14ed6-d323-4dec-b8f7-301377cda747) |
| 4 | CI/CD Deployment | Dockerfile (frontend/backend), docker-compose.yml, ci.yml | M3 | PLANNED |
| 5 | Final E2E Pass | Pass E2E Testing Track (TEST_READY.md) & Tier 5 Hardening | M2, M4, TEST_READY | PLANNED |

## Interface Contracts
- Playwright should execute via `npx playwright test` (owned by E2E track).
- Pytest should execute via `pytest` (owned by M3).
- Docker environment built via `docker-compose up --build` (owned by M4).

## Code Layout
- Frontend in `frontend/`
- Backend in `src/` (or root)
- Github Actions in `.github/workflows/ci.yml`

| 6 | VnV Mathematical Benchmark | Implement pytest suite for 2-DOF and 7-DOF physics solvers | none | PLANNED |
| 7 | Stripe Webhook Smoke Test | Implement E2E pytest script for Stripe webhook (tier update) | none | PLANNED |
| 8 | Alembic Tier Cleanup | Finalize Alembic schemas for tier system (Free, Pro, Ent) and test alembic upgrade head | none | PLANNED |
