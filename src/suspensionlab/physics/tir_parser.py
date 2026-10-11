"""
physics/tir_parser.py
=====================
SuspensionLab PRO — .tir File Parser & Exporter (MF 5.2 Canonical)

Parses standard .tir (Tyre Property File) format and maps Pacejka
coefficients to the TireCoeffs dataclass, and serializes TireCoeffs back
to industry-standard .tir files.

Supports the full MF 5.2 coefficient set including pure slip, aligning moment,
pneumatic trail, combined-slip Similarity Method, and inflation pressure scaling.
"""

import logging
import re
from typing import Optional
from .magic_formula import TireCoeffs
from .tire_model import TireDefinition, TireModelMetadata

logger = logging.getLogger(__name__)

# Comprehensive mapping of .tir keys (uppercase) to TireCoeffs attributes.
_TIR_KEY_MAP = {
    # ── Nominal load & pressure ───────────────────────────────────────
    "FNOMIN":  "Fz0",
    "PNOMIN":  "p0_bar",
    "NOMPRES": "p0_bar",

    # ── Lateral pure slip ─────────────────────────────────────────────
    "PCY1":    "pCy1",
    "PDY1":    "pDy1",
    "PDY2":    "pDy2",
    "PDY3":    "pDy3",
    "PEY1":    "pEy1",
    "PEY2":    "pEy2",
    "PEY3":    "pEy3",
    "PEY4":    "pEy4",
    "PKY1":    "pKy1",
    "PKY2":    "pKy2",
    "PKY3":    "pKy3",
    "PHY1":    "pHy1",
    "PHY2":    "pHy2",
    "PHY3":    "pHy3",
    "PVY1":    "pVy1",
    "PVY2":    "pVy2",
    "PVY3":    "pVy3",
    "PVY4":    "pVy4",

    # ── Longitudinal pure slip ────────────────────────────────────────
    "PCX1":    "pCx1",
    "PDX1":    "pDx1",
    "PDX2":    "pDx2",
    "PDX3":    "pDx3",
    "PEX1":    "pEx1",
    "PEX2":    "pEx2",
    "PEX3":    "pEx3",
    "PEX4":    "pEx4",
    "PKX1":    "pKx1",
    "PKX2":    "pKx2",
    "PKX3":    "pKx3",
    "PHX1":    "pHx1",
    "PHX2":    "pHx2",
    "PVX1":    "pVx1",
    "PVX2":    "pVx2",

    # ── Combined slip (Similarity Method) ─────────────────────────────
    "RBX1":    "rBx1",
    "RBX2":    "rBx2",
    "RCX1":    "rCx1",
    "RBY1":    "rBy1",
    "RBY2":    "rBy2",
    "RCY1":    "rCy1",
    "RHX1":    "rHx1",
    "RHY1":    "rHy1",

    # ── Aligning Moment & Pneumatic Trail ─────────────────────────────
    "QBZ1":    "qBz1",
    "QBZ2":    "qBz2",
    "QBZ3":    "qBz3",
    "QCZ1":    "qCz1",
    "QDZ1":    "qDz1",
    "QDZ2":    "qDz2",
    "QDZ3":    "qDz3",
    "QDZ4":    "qDz4",
    "QEZ1":    "qEz1",
    "QEZ2":    "qEz2",
    "QEZ3":    "qEz3",
    "QEZ4":    "qEz4",
    "QDZ6":    "qDz6",
    "QDZ7":    "qDz7",
    "QDZ8":    "qDz8",
    "QDZ9":    "qDz9",
    "QBZ9":    "qBz9",
    "QBZ10":   "qBz10",

    # ── Pressure scaling ──────────────────────────────────────────────
    "PPX1":    "pPx1",
    "PPX2":    "pPx2",
    "PPY1":    "pPy1",
    "PPY2":    "pPy2",
}


def parse_tir_file(content: str) -> TireCoeffs:
    """Parse a standard .tir (Tyre Property File) and return TireCoeffs."""
    coeffs = TireCoeffs()
    found_keys = set()

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("$") or line.startswith("!"):
            continue
        if line.startswith("["):
            continue

        parts = line.split("=")
        if len(parts) >= 2:
            key_part = parts[0].strip().upper()
            val_part = parts[1].split("$")[0].split("!")[0].strip()

            if key_part in _TIR_KEY_MAP:
                attr_name = _TIR_KEY_MAP[key_part]
                try:
                    val_float = float(val_part)
                    setattr(coeffs, attr_name, val_float)
                    found_keys.add(key_part)
                except ValueError:
                    logger.warning(
                        "TIR file: key '%s' has non-numeric value '%s'; using default.",
                        key_part, val_part,
                    )

    return coeffs


def export_tir_file(
    coeffs: TireCoeffs,
    definition: Optional[TireDefinition] = None,
    metadata: Optional[TireModelMetadata] = None,
) -> str:
    """Serialize TireCoeffs, TireDefinition, and TireModelMetadata to standard .tir file format."""
    defn = definition or TireDefinition()
    meta = metadata or TireModelMetadata()

    lines = [
        "!==================================================================",
        f"! SuspensionLab PRO — Exported Tyre Property File (.tir)",
        f"! Model ID:      {meta.model_id}",
        f"! Version:       {meta.model_version}",
        f"! Source:        {meta.source}",
        f"! ParameterHash: {meta.parameter_hash}",
        "!==================================================================",
        "[MDI_HEADER]",
        "FILE_TYPE                = 'tir'",
        "FILE_VERSION             = 3.0",
        "FILE_FORMAT              = 'ASCII'",
        "",
        "[UNITS]",
        "LENGTH                   = 'meter'",
        "FORCE                    = 'newton'",
        "ANGLE                    = 'radian'",
        "MASS                     = 'kg'",
        "TIME                     = 'second'",
        "",
        "[MODEL]",
        "FITTYP                   = 52",
        "TYRESIDE                 = 'RIGHT'",
        "LONGVL                   = 16.6",
        "",
        "[DIMENSION]",
        f"UNLOADED_RADIUS          = {defn.unloaded_radius:.4f}",
        f"WIDTH                    = {defn.section_width:.4f}",
        f"ASPECT_RATIO             = {defn.aspect_ratio:.2f}",
        f"RIM_RADIUS               = {(defn.rim_diameter_inch * 0.0254 / 2.0):.4f}",
        "",
        "[VERTICAL]",
        f"FNOMIN                   = {coeffs.Fz0:.1f}",
        f"VERTICAL_STIFFNESS       = {defn.vertical_stiffness_k_t:.1f}",
        "",
        "[LONGITUDINAL_COEFFICIENTS]",
        f"PCX1                     = {coeffs.pCx1:.5f}",
        f"PDX1                     = {coeffs.pDx1:.5f}",
        f"PDX2                     = {coeffs.pDx2:.5f}",
        f"PDX3                     = {coeffs.pDx3:.5f}",
        f"PEX1                     = {coeffs.pEx1:.5f}",
        f"PEX2                     = {coeffs.pEx2:.5f}",
        f"PEX3                     = {coeffs.pEx3:.5f}",
        f"PEX4                     = {coeffs.pEx4:.5f}",
        f"PKX1                     = {coeffs.pKx1:.5f}",
        f"PKX2                     = {coeffs.pKx2:.5f}",
        f"PKX3                     = {coeffs.pKx3:.5f}",
        f"PHX1                     = {coeffs.pHx1:.5f}",
        f"PHX2                     = {coeffs.pHx2:.5f}",
        f"PVX1                     = {coeffs.pVx1:.5f}",
        f"PVX2                     = {coeffs.pVx2:.5f}",
        f"RBX1                     = {coeffs.rBx1:.5f}",
        f"RBX2                     = {coeffs.rBx2:.5f}",
        f"RCX1                     = {coeffs.rCx1:.5f}",
        f"RHX1                     = {coeffs.rHx1:.5f}",
        "",
        "[LATERAL_COEFFICIENTS]",
        f"PCY1                     = {coeffs.pCy1:.5f}",
        f"PDY1                     = {coeffs.pDy1:.5f}",
        f"PDY2                     = {coeffs.pDy2:.5f}",
        f"PDY3                     = {coeffs.pDy3:.5f}",
        f"PEY1                     = {coeffs.pEy1:.5f}",
        f"PEY2                     = {coeffs.pEy2:.5f}",
        f"PEY3                     = {coeffs.pEy3:.5f}",
        f"PEY4                     = {coeffs.pEy4:.5f}",
        f"PKY1                     = {coeffs.pKy1:.5f}",
        f"PKY2                     = {coeffs.pKy2:.5f}",
        f"PKY3                     = {coeffs.pKy3:.5f}",
        f"PHY1                     = {coeffs.pHy1:.5f}",
        f"PHY2                     = {coeffs.pHy2:.5f}",
        f"PHY3                     = {coeffs.pHy3:.5f}",
        f"PVY1                     = {coeffs.pVy1:.5f}",
        f"PVY2                     = {coeffs.pVy2:.5f}",
        f"PVY3                     = {coeffs.pVy3:.5f}",
        f"PVY4                     = {coeffs.pVy4:.5f}",
        f"RBY1                     = {coeffs.rBy1:.5f}",
        f"RBY2                     = {coeffs.rBy2:.5f}",
        f"RCY1                     = {coeffs.rCy1:.5f}",
        f"RHY1                     = {coeffs.rHy1:.5f}",
        "",
        "[ALIGNING_COEFFICIENTS]",
        f"QBZ1                     = {coeffs.qBz1:.5f}",
        f"QBZ2                     = {coeffs.qBz2:.5f}",
        f"QBZ3                     = {coeffs.qBz3:.5f}",
        f"QCZ1                     = {coeffs.qCz1:.5f}",
        f"QDZ1                     = {coeffs.qDz1:.5f}",
        f"QDZ2                     = {coeffs.qDz2:.5f}",
        f"QDZ3                     = {coeffs.qDz3:.5f}",
        f"QDZ4                     = {coeffs.qDz4:.5f}",
        f"QEZ1                     = {coeffs.qEz1:.5f}",
        f"QEZ2                     = {coeffs.qEz2:.5f}",
        f"QDZ6                     = {coeffs.qDz6:.5f}",
        f"QDZ7                     = {coeffs.qDz7:.5f}",
        f"QDZ8                     = {coeffs.qDz8:.5f}",
        f"QDZ9                     = {coeffs.qDz9:.5f}",
        f"QBZ9                     = {coeffs.qBz9:.5f}",
        f"QBZ10                    = {coeffs.qBz10:.5f}",
    ]
    return "\n".join(lines) + "\n"

