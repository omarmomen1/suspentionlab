"""
src/suspensionlab/interop/registry.py
=====================================
SuspensionLab PRO — Solver Interoperability Adapter Capability Registry.

Maintains a deterministic, immutable-ordered catalog of available external
solver adapters and their capabilities.

Invariants:
1. Deterministic Ordering: Adapters are always returned in deterministic lexicographical
   order by adapter_id.
2. Honest Capability Reporting: Only real integrations with implemented routines are listed.
3. Unknown Solver Handling: Inquiries for unknown solvers return SupportLevel.UNSUPPORTED.
4. Truthful Dependencies: Uninstalled commercial solvers report UNAVAILABLE_DEPENDENCY.
"""
from __future__ import annotations

import collections
from typing import Dict, List, Optional, Set

from suspensionlab.interop.adapter import (
    AdapterCapability,
    BaseSolverAdapter,
    SupportLevel,
)
from suspensionlab.interop.adapters.canonical_json import CanonicalJsonAdapter
from suspensionlab.interop.adapters.adams import AdamsSolverAdapter
from suspensionlab.interop.adapters.matlab_simulink import MatlabSimulinkAdapter
from suspensionlab.interop.adapters.fmi import FMICoSimulationAdapter
from suspensionlab.interop.adapters.tir_tire import TirPropertyAdapter


class AdapterRegistry:
    """
    Deterministic registry for solver interoperability adapters.
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, BaseSolverAdapter] = {}

    def register(self, adapter: BaseSolverAdapter) -> None:
        """
        Registers an adapter instance.

        Raises:
            ValueError: If adapter identity is empty or version is unsupported.
        """
        caps = adapter.get_capabilities()
        if not caps.adapter_id or not caps.adapter_id.strip():
            raise ValueError("Adapter identity cannot be empty.")
        if not caps.adapter_version or not caps.adapter_version.strip():
            raise ValueError("Adapter version cannot be empty.")

        # Store keyed by adapter_id
        self._adapters[caps.adapter_id] = adapter

    def get_adapter(self, adapter_id: str) -> Optional[BaseSolverAdapter]:
        """Retrieves an adapter by its unique identity, or None if not registered."""
        return self._adapters.get(adapter_id)

    def list_adapters(self) -> List[AdapterCapability]:
        """
        Returns list of capabilities for all registered adapters in deterministic order
        sorted by adapter_id.
        """
        sorted_keys = sorted(self._adapters.keys())
        return [self._adapters[k].get_capabilities() for k in sorted_keys]

    def find_by_solver(self, solver_name: str) -> List[BaseSolverAdapter]:
        """
        Finds all adapters supporting a given solver name (case-insensitive).
        Returns in deterministic order by adapter_id.
        """
        norm_name = (solver_name or "").strip().upper()
        matches = []
        for adapter_id in sorted(self._adapters.keys()):
            adapter = self._adapters[adapter_id]
            if adapter.get_capabilities().solver_name.upper() == norm_name:
                matches.append(adapter)
        return matches

    def find_by_format(self, file_format: str, mode: Optional[str] = None) -> List[BaseSolverAdapter]:
        """
        Finds all adapters supporting a given file extension or MIME type (e.g. '.adm', '.json').
        If mode is 'import', checks supported_import_formats.
        If mode is 'export', checks supported_export_formats.
        If mode is None, checks general supported_formats.
        Returns in deterministic order by adapter_id.
        """
        norm_ext = (file_format or "").strip().lower()
        if not norm_ext.startswith(".") and "/" not in norm_ext:
            norm_ext = f".{norm_ext}"

        matches = []
        for adapter_id in sorted(self._adapters.keys()):
            adapter = self._adapters[adapter_id]
            caps = adapter.get_capabilities()
            if mode == "import":
                fmts = caps.supported_import_formats if caps.supported_import_formats else caps.supported_formats
            elif mode == "export":
                fmts = caps.supported_export_formats if caps.supported_export_formats else caps.supported_formats
            else:
                fmts = caps.supported_formats

            supported = [fmt.lower() for fmt in fmts]
            if norm_ext in supported:
                matches.append(adapter)
        return matches

    def get_solver_support_level(self, solver_name: str) -> SupportLevel:
        """
        Determines the overall support level for a solver name.
        If unknown, returns SupportLevel.UNSUPPORTED.
        """
        matches = self.find_by_solver(solver_name)
        if not matches:
            return SupportLevel.UNSUPPORTED

        # Determine best available capability
        best = SupportLevel.UNSUPPORTED
        for m in matches:
            caps = m.get_capabilities()
            if caps.export_capability == SupportLevel.SUPPORTED or caps.import_capability == SupportLevel.SUPPORTED:
                return SupportLevel.SUPPORTED
            elif (
                caps.export_capability == SupportLevel.PARTIALLY_SUPPORTED
                or caps.import_capability == SupportLevel.PARTIALLY_SUPPORTED
            ):
                best = SupportLevel.PARTIALLY_SUPPORTED
            elif (
                caps.export_capability == SupportLevel.UNAVAILABLE_DEPENDENCY
                or caps.import_capability == SupportLevel.UNAVAILABLE_DEPENDENCY
            ):
                if best != SupportLevel.PARTIALLY_SUPPORTED:
                    best = SupportLevel.UNAVAILABLE_DEPENDENCY

        return best


_GLOBAL_REGISTRY: Optional[AdapterRegistry] = None


def get_adapter_registry() -> AdapterRegistry:
    """
    Returns the global, pre-populated deterministic adapter registry.
    """
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        reg = AdapterRegistry()
        # Register built-in verified adapters
        reg.register(CanonicalJsonAdapter())
        reg.register(AdamsSolverAdapter())
        reg.register(MatlabSimulinkAdapter())
        reg.register(FMICoSimulationAdapter())
        reg.register(TirPropertyAdapter())
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY


def reset_adapter_registry() -> None:
    """Resets the global adapter registry to default state."""
    global _GLOBAL_REGISTRY
    _GLOBAL_REGISTRY = None
