"""
sdk/suspensionlab/models.py
===========================
SuspensionLab PRO — Typed SDK Data Models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class QuarterCarParams(BaseModel):
    m_s: float = Field(default=300.0, description="Sprung mass [kg]")
    m_u: float = Field(default=35.0, description="Unsprung mass [kg]")
    k_s: float = Field(default=25000.0, description="Spring stiffness [N/m]")
    c: float = Field(default=2050.0, description="Damping coefficient [Ns/m]")
    k_t: float = Field(default=200000.0, description="Tire radial stiffness [N/m]")
    MR: float = Field(default=0.85, description="Motion ratio [-]")
    c_t: float = Field(default=0.0, description="Tire damping [Ns/m]")


class FullCarParams(BaseModel):
    m_s: float = Field(default=1200.0, description="Sprung mass [kg]")
    m_uf: float = Field(default=45.0, description="Front unsprung mass [kg]")
    m_ur: float = Field(default=40.0, description="Rear unsprung mass [kg]")
    I_x: float = Field(default=350.0, description="Roll inertia [kg*m^2]")
    I_y: float = Field(default=1200.0, description="Pitch inertia [kg*m^2]")
    a: float = Field(default=1.20, description="CG to front axle distance [m]")
    b: float = Field(default=1.50, description="CG to rear axle distance [m]")
    tw_f: float = Field(default=1.60, description="Front track width [m]")
    tw_r: float = Field(default=1.55, description="Rear track width [m]")
    k_sf: float = Field(default=35000.0, description="Front spring rate [N/m]")
    k_sr: float = Field(default=40000.0, description="Rear spring rate [N/m]")
    c_f: float = Field(default=2200.0, description="Front damping [Ns/m]")
    c_r: float = Field(default=2500.0, description="Rear damping [Ns/m]")
    k_arb_f: float = Field(default=1200.0, description="Front anti-roll bar stiffness [Nm/rad]")
    k_arb_r: float = Field(default=900.0, description="Rear anti-roll bar stiffness [Nm/rad]")
    k_tf: float = Field(default=220000.0, description="Front tire radial stiffness [N/m]")
    k_tr: float = Field(default=220000.0, description="Rear tire radial stiffness [N/m]")
    speed_mps: float = Field(default=20.0, description="Vehicle forward speed [m/s]")


class RoadProfile(BaseModel):
    profile_type: str = Field(default="step", description="step, sine, pothole, random, iso8608")
    amplitude: float = Field(default=0.05, description="Excitation amplitude [m]")
    frequency: float = Field(default=2.0, description="Excitation frequency [Hz]")
    duration: float = Field(default=5.0, description="Simulation duration [s]")
    speed_mps: float = Field(default=20.0, description="Vehicle speed [m/s]")
    iso_class: str = Field(default="A", description="ISO 8608 road roughness class")


class SimulationResponse(BaseModel):
    time: List[float] = Field(default_factory=list)
    z_s: List[float] = Field(default_factory=list)
    z_u: List[float] = Field(default_factory=list)
    susp_travel: List[float] = Field(default_factory=list)
    tire_load_var: List[float] = Field(default_factory=list)
    ddz_s: List[float] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    raw: Dict[str, Any] = Field(default_factory=dict)


class MonteCarloResponse(BaseModel):
    iterations: int
    mean_rms_accel: float
    std_rms_accel: float
    confidence_95: Dict[str, float] = Field(default_factory=dict)
    raw_results: List[Dict[str, Any]] = Field(default_factory=list)


class JobInfo(BaseModel):
    job_id: str
    status: JobStatus
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TelemetryFrame(BaseModel):
    timestamp_us: int
    channel: str
    value: float


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    limit: int
    has_next: bool
