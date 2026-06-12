# 🏎️ SuspensionLab PRO

An enterprise-grade, professional vehicle dynamics platform. This tool simulates ride comfort, handling, kinematics, and NVH (Noise, Vibration, and Harshness) metrics using both time-domain and frequency-domain numerical methods.

## Engineering Features

* **Physics Engine:** Core dynamic models including 2-DOF Quarter Car, 4-DOF Half Car, and 7-DOF Full Car utilizing SciPy's `solve_ivp` (RK45) for time-domain integration.
* **Kinematics & Handling:** Pacejka Magic Formula tire models with real-time 3D React Three Fiber visualizations.
* **NVH Analytics:** Structural transmissibility and A-Weighting impedance matrix solvers.
* **Modern Stack:** React/Next.js frontend with an ultra-fast FastAPI backend and SQLite persistence.

## Repository Structure

* `frontend/` — Next.js 15 App Router frontend featuring Plotly graphs and 3D telemetry.
* `src/suspensionlab/backend/` — FastAPI REST server and SQLAlchemy database models.
* `src/suspensionlab/physics/` — Core mathematical models, state-space formulation, and ODE solvers.

## Installation & Usage (Docker)

The fastest way to run SuspensionLab PRO is via Docker Compose:

```bash
docker-compose up --build
```

- **Frontend UI:** `http://localhost:3000`
- **Backend API Docs:** `http://localhost:8000/docs`

## Manual Development

To run locally without Docker:

**Terminal 1 (Backend):**
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements-backend.txt
set PYTHONPATH=src
uvicorn suspensionlab.backend.api.main:app --port 8000 --reload
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm install
npm run dev
```