from fastapi import APIRouter

from .quarter_car import router as qc_router
from .half_car import router as hc_router
from .full_car import router as fc_router
from .handling import router as handling_router
from .active import router as active_router
from .sweep import router as sweep_router
from .monte_carlo import router as mc_router
from .utils import router as utils_router

router = APIRouter()

router.include_router(qc_router)
router.include_router(hc_router)
router.include_router(fc_router)
router.include_router(handling_router)
router.include_router(active_router)
router.include_router(sweep_router)
router.include_router(mc_router)
router.include_router(utils_router)
