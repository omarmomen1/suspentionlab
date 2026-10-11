"""
sdk/suspensionlab/client.py
===========================
SuspensionLab PRO — Enterprise Python SDK Client.
Provides full programmatic access to:
- Quarter Car & 7-DOF Full Car Multibody Dynamics engines
- Asynchronous job execution and polling
- Constrained optimization and parameter sensitivity sweeps
- Multi-channel telemetry ingestion and analysis
- Live WebSocket streaming telemetry
- Industrial CAE export pipeline (FMI 2.0 FMU, Simulink, MSC ADAMS)
"""

from __future__ import annotations

import time
import uuid
import random
import pathlib
import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import (
    QuarterCarParams,
    FullCarParams,
    RoadProfile,
    SimulationResponse,
    MonteCarloResponse,
    JobInfo,
    JobStatus,
    PaginatedResponse,
)

logger = logging.getLogger("suspensionlab.sdk")


class SuspensionLabClient:
    """
    Production Python SDK Client for SuspensionLab PRO API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        base_url: str = "http://localhost:8000",
        timeout: Union[float, Tuple[float, float]] = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        """
        Initialize the SuspensionLab Client.

        :param api_key: Secret API key (starts with 'sk_' or 'slk_').
        :param access_token: JWT bearer token.
        :param base_url: Base URL of the API gateway.
        :param timeout: Request timeout in seconds (or (connect, read) tuple).
        :param max_retries: Maximum exponential backoff retry attempts for transient errors.
        :param backoff_factor: Multiplier for exponential backoff delay.
        """
        if not api_key and not access_token:
            raise ValueError("Either api_key or access_token must be provided.")

        self.api_key = api_key
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self.session = requests.Session()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SuspensionLab-Python-SDK/2.0.0",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        self.session.headers.update(headers)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> requests.Response:
        """
        Execute an HTTP request with automatic Idempotency-Key and exponential backoff retry.
        """
        url = f"{self.base_url}{path}"
        headers = {"Idempotency-Key": str(uuid.uuid4())}

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    json=json_payload,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                    stream=stream,
                )

                # Retry on rate limits (429) or transient server faults (500, 502, 503, 504)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    # Exponential backoff with jitter
                    sleep_time = (self.backoff_factor * (2 ** attempt)) + (random.random() * 0.1)
                    logger.warning(
                        "Request %s %s returned status %d (attempt %d/%d). Retrying in %.2f s...",
                        method, path, resp.status_code, attempt + 1, self.max_retries, sleep_time
                    )
                    time.sleep(sleep_time)
                    continue

                resp.raise_for_status()
                return resp

            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt < self.max_retries:
                    sleep_time = (self.backoff_factor * (2 ** attempt)) + (random.random() * 0.1)
                    logger.warning(
                        "Request %s %s failed with %s (attempt %d/%d). Retrying in %.2f s...",
                        method, path, e, attempt + 1, self.max_retries, sleep_time
                    )
                    time.sleep(sleep_time)
                else:
                    raise last_exc

        raise last_exc or RuntimeError(f"Request failed after {self.max_retries} attempts.")

    # ── Simulation ────────────────────────────────────────────────────────────

    def simulate_quarter_car(
        self,
        params: Union[QuarterCarParams, Dict[str, Any]],
        profile: Optional[Union[RoadProfile, Dict[str, Any]]] = None,
    ) -> SimulationResponse:
        """
        Run a forward 2-DOF Quarter Car ride simulation.
        """
        p_dict = params.model_dump() if isinstance(params, QuarterCarParams) else params
        prof_dict = (
            profile.model_dump() if isinstance(profile, RoadProfile)
            else (profile or RoadProfile().model_dump())
        )

        payload = {"params": p_dict, "profile": prof_dict}
        resp = self._request_with_retry("POST", "/api/v1/simulate/quarter", json_payload=payload)
        data = resp.json()

        return SimulationResponse(
            time=data.get("time", []),
            z_s=data.get("z_s", []),
            z_u=data.get("z_u", []),
            susp_travel=data.get("susp_travel", []),
            tire_load_var=data.get("tire_load_var", data.get("tire_load_dynamic", [])),
            ddz_s=data.get("ddz_s", data.get("body_accel", [])),
            metrics=data.get("metrics", {}),
            raw=data,
        )

    def simulate_full_car(
        self,
        params: Union[FullCarParams, Dict[str, Any]],
        profile: Optional[Union[RoadProfile, Dict[str, Any]]] = None,
    ) -> SimulationResponse:
        """
        Run a 7-DOF Full Car vehicle ride simulation.
        """
        p_dict = params.model_dump() if isinstance(params, FullCarParams) else params
        prof_dict = (
            profile.model_dump() if isinstance(profile, RoadProfile)
            else (profile or RoadProfile().model_dump())
        )

        payload = {"params": p_dict, "profile": prof_dict}
        resp = self._request_with_retry("POST", "/api/v1/simulate/full-car", json_payload=payload)
        data = resp.json()
        return SimulationResponse(raw=data)

    def run_monte_carlo(
        self,
        params: Union[QuarterCarParams, Dict[str, Any]],
        profile: Optional[Union[RoadProfile, Dict[str, Any]]] = None,
        iterations: int = 500,
        tolerance_pct: float = 5.0,
    ) -> MonteCarloResponse:
        """
        Run a Monte Carlo parameter sweep on the Quarter Car model.
        """
        p_dict = params.model_dump() if isinstance(params, QuarterCarParams) else params
        prof_dict = (
            profile.model_dump() if isinstance(profile, RoadProfile)
            else (profile or RoadProfile().model_dump())
        )

        payload = {
            "params": p_dict,
            "profile": prof_dict,
            "iterations": iterations,
            "tolerance_pct": tolerance_pct,
        }
        resp = self._request_with_retry("POST", "/api/v1/simulate/monte-carlo", json_payload=payload)
        data = resp.json()

        return MonteCarloResponse(
            iterations=iterations,
            mean_rms_accel=data.get("mean_rms_accel", 0.0),
            std_rms_accel=data.get("std_rms_accel", 0.0),
            confidence_95=data.get("confidence_95", {}),
            raw_results=data.get("results", []),
        )

    # ── Asynchronous Jobs ─────────────────────────────────────────────────────

    def submit_job(self, job_type: str, payload: Dict[str, Any]) -> JobInfo:
        """Submit an asynchronous background computation job."""
        data = {"type": job_type, "payload": payload}
        resp = self._request_with_retry("POST", "/api/v1/jobs", json_payload=data)
        return JobInfo(**resp.json())

    def get_job(self, job_id: str) -> JobInfo:
        """Fetch current status and results of a background job."""
        resp = self._request_with_retry("GET", f"/api/v1/jobs/{job_id}")
        return JobInfo(**resp.json())

    def cancel_job(self, job_id: str) -> JobInfo:
        """Cancel an ongoing or queued background job."""
        resp = self._request_with_retry("POST", f"/api/v1/jobs/{job_id}/cancel")
        return JobInfo(**resp.json())

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 1.0,
        timeout: float = 60.0,
    ) -> JobInfo:
        """
        Poll job status until it reaches a terminal state (COMPLETED, FAILED, CANCELLED).
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            job = self.get_job(job_id)
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                return job
            time.sleep(poll_interval)

        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds.")

    # ── Pagination ────────────────────────────────────────────────────────────

    def paginate_jobs(self, limit: int = 50) -> Iterator[JobInfo]:
        """
        Iterate over paginated jobs using generator.
        """
        page = 1
        has_next = True
        while has_next:
            resp = self._request_with_retry(
                "GET", "/api/v1/jobs", params={"page": page, "limit": limit}
            )
            data = resp.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            if not items:
                break

            for item in items:
                yield JobInfo(**item)

            if isinstance(data, dict):
                has_next = data.get("has_next", len(items) >= limit)
            else:
                has_next = len(items) >= limit
            page += 1

    # ── Telemetry & CAE Exporters ─────────────────────────────────────────────

    def get_telemetry(self, dataset_id: str) -> Dict[str, Any]:
        """Fetch telemetry dataset metadata and channel metrics."""
        resp = self._request_with_retry("GET", f"/api/v1/telemetry/{dataset_id}")
        return resp.json()

    def export_fmu(self, output_path: Union[str, pathlib.Path]) -> pathlib.Path:
        """Download packaged FMI 2.0 Co-Simulation archive (.fmu)."""
        resp = self._request_with_retry("POST", "/api/v1/export/fmu", stream=True)
        out = pathlib.Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return out

    def export_adams(
        self,
        params: Union[FullCarParams, Dict[str, Any]],
        export_format: str = "adm",
        output_path: Optional[Union[str, pathlib.Path]] = None,
    ) -> str:
        """Download MSC.ADAMS solver deck (.adm), command file (.cmd), or Python script (.py)."""
        p_dict = params.model_dump() if isinstance(params, FullCarParams) else params
        resp = self._request_with_retry(
            "POST",
            "/api/v1/export/adams",
            json_payload=p_dict,
            params={"export_format": export_format},
        )
        content = resp.text
        if output_path:
            out = pathlib.Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
        return content

    def export_simulink(
        self,
        params: Union[FullCarParams, Dict[str, Any]],
        output_path: Optional[Union[str, pathlib.Path]] = None,
    ) -> str:
        """Download MATLAB/Simulink state-space initialization script (.m)."""
        p_dict = params.model_dump() if isinstance(params, FullCarParams) else params
        resp = self._request_with_retry("POST", "/api/v1/export/simulink", json_payload=p_dict)
        content = resp.text
        if output_path:
            out = pathlib.Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
        return content
