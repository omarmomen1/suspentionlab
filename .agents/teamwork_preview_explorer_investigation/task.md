# Investigation Task

## Objective
Explore the SuspensionLab Pro codebase to analyze the implementation path for Sprint 2, Sprint 3, and Phase 2 & 3 features.

## Scope of Investigation
1. Locate where routes are registered in `main.py` and how to apply the `/api/v1/` prefix. Identify the syntax errors in `main.py`.
2. Locate team routes, team models, and user models. Determine how to implement Team RBAC (Owner, Admin, Viewer roles) and gate write routes.
3. Locate Redis/RQ queue setup, where jobs are processed, and how to add a `priority_queue` with a dedicated worker.
4. Locate audit log system and determine how to implement GET `/audit/export` (CSV/JSON).
5. Locate the Full-Car physics solver (`full_car.py`) and determine how to expose eigenvalues (7 mode shapes/frequencies/damping ratios) and animate them on the frontend.
6. Determine how to implement the ISO 8608 sensitivity sweep (64-simulation sweep heatmap).
7. Determine how to implement simulation result diff view in frontend/backend.
8. Locate worker cancellation, progress reporting, webhooks, and SSO/SCIM prep endpoints or designs.
9. Propose a specific, concrete implementation plan for each feature.
