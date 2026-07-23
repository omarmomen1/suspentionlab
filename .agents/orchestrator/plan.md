# Plan: SuspensionLab Pro Enterprise Hardening

## Overview
This plan outlines the milestones, dependencies, and verification criteria for implementing the requirements for Sprint 2, Sprint 3, and Phase 2 & 3 Core Features.

## Architecture
- Backend: FastAPI, SQLAlchemy, Redis (RQ for queues)
- Frontend: Next.js + React (simulation visualization, diff views)
- Security: Role-Based Access Control (RBAC), API key management
- Observability: Audit logging, OpenTelemetry, Redis progress reporting

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M9 | API Versioning & Documentation | Consistent `/api/v1/` prefix, fix main.py syntax errors, OpenAPI spec PDF at `/docs/api-reference.pdf` | none | PLANNED |
| M10| Team RBAC | Add Owner, Admin, and Viewer roles to team membership. Gate write operations. | M9 | PLANNED |
| M11| Enterprise Queue & Audit Logs | Add `priority_queue` RQ queue, dedicated worker. GET `/audit/export` returning CSV/JSON. | M10 | PLANNED |
| M12| Physics & Visualization | 7 eigenvalues from full car model, 3D animation, ISO 8608 sweep heatmap (64 simulations), simulation diff view. | M9 | PLANNED |
| M13| Phase 2 & 3 Core Features | Worker cancellation, progress reporting via Redis, webhooks, SSO/SCIM prep endpoints. | M11 | PLANNED |
| M14| E2E Testing & Integration | Integration and regression tests for all new endpoints. Forensic Audit clean validation. | M9, M10, M11, M12, M13 | PLANNED |

## Cross-Module Interface Contracts
- All new/modified API routes must respond under `/api/v1/` prefix.
- The RBAC role-checking middleware will intercept team operations and return HTTP 403 Forbidden for Viewer role attempting write operations.
- The physics sweep endpoint will run 64 runs in parallel or series and return a structured JSON response representation of the ISO 8608 heatmap.

## Verification Method
- Code compilation and syntax verification (ensuring FastAPI loads correctly).
- Unit tests via `pytest`.
- Forensic auditor verification.
