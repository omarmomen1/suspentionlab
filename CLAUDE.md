# SuspensionLab PRO

## Project Phase
**Current Phase:** Production Infrastructure & Optimization
We have completed the core physics implementation and are focusing on high-availability cloud deployment (Kubernetes/AWS) and backend performance optimizations (Redis/FastAPI).

## Tech Stack
- **Backend:** FastAPI (Python 3.11), SQLAlchemy, PostgreSQL, Redis (RQ workers)
- **Physics Engine:** Scipy (`solve_ivp`), Pacejka MF5.2
- **Frontend:** Next.js, React, Three.js (Fiber), Plotly
- **DevOps:** Docker, Kubernetes (Helm), GitHub Actions, Terraform

## Architecture Notes
- Heavy computation (Monte Carlo/Sweeps) is offloaded to RQ workers.
- The UI runs on port 3000.
- Production Domain: `suspensionlab.pro`
