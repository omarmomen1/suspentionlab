# Legacy billing module — superseded by lemon_squeezy_routes.py
# This stub is kept to satisfy the main.py import. All real billing
# logic is handled in api/routes/lemon_squeezy_routes.py
from fastapi import APIRouter

router = APIRouter(prefix="/billing/legacy", tags=["billing-legacy"])
