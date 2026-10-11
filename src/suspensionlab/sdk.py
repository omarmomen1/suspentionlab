"""
suspensionlab/sdk.py
====================
SuspensionLab PRO — Enterprise Python SDK Module.
Re-exports the SDK client, streaming interface, and typed models.
"""

import sys
import pathlib

# Ensure project root is in path for sdk package resolution
_ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import sdk.suspensionlab as _sdk

SuspensionLabClient = _sdk.SuspensionLabClient
SuspensionLabStreamingClient = _sdk.SuspensionLabStreamingClient
QuarterCarParams = _sdk.QuarterCarParams
FullCarParams = _sdk.FullCarParams
RoadProfile = _sdk.RoadProfile
SimulationResponse = _sdk.SimulationResponse
MonteCarloResponse = _sdk.MonteCarloResponse
JobInfo = _sdk.JobInfo
JobStatus = _sdk.JobStatus
TelemetryFrame = _sdk.TelemetryFrame
PaginatedResponse = _sdk.PaginatedResponse

__all__ = [
    "SuspensionLabClient",
    "SuspensionLabStreamingClient",
    "QuarterCarParams",
    "FullCarParams",
    "RoadProfile",
    "SimulationResponse",
    "MonteCarloResponse",
    "JobInfo",
    "JobStatus",
    "TelemetryFrame",
    "PaginatedResponse",
]
