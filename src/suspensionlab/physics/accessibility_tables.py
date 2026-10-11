"""
physics/accessibility_tables.py
===============================
SuspensionLab PRO — Accessible Tabular Data Alternatives for Engineering Charts

Ensures that visual graphs are never the sole representation of critical vehicle dynamics data.
Generates ARIA-compliant, screen-reader friendly data tables summarizing time-series,
frequency responses, and load transfer distributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass
class AccessibleTableData:
    """Accessible tabular representation of a vehicle dynamics chart."""
    title: str
    summary_aria: str
    column_headers: List[str]
    rows: List[List[Any]]

    def to_markdown_table(self, max_rows: int = 15) -> str:
        """Render standard markdown table with truncated representative samples."""
        header_line = "| " + " | ".join(self.column_headers) + " |"
        separator_line = "| " + " | ".join(["---"] * len(self.column_headers)) + " |"
        
        display_rows = self.rows[:max_rows]
        row_lines = [
            "| " + " | ".join([f"{val:.3f}" if isinstance(val, float) else str(val) for val in row]) + " |"
            for row in display_rows
        ]
        
        caption = f"\n*Table: {self.title} ({self.summary_aria})*"
        return "\n".join([header_line, separator_line] + row_lines) + caption

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "aria_summary": self.summary_aria,
            "headers": self.column_headers,
            "row_count": len(self.rows),
            "rows": self.rows[:50],  # Sample for JSON payload
        }


def generate_time_series_accessible_table(
    time_s: List[float] | np.ndarray,
    channels: Dict[str, List[float] | np.ndarray],
    title: str = "Quarter Car Step Response Telemetry",
    sample_stride: int = 20,
) -> AccessibleTableData:
    """Create an accessible tabular dataset from continuous multi-channel time series."""
    t = np.asarray(time_s)
    channel_names = list(channels.keys())
    headers = ["Time (s)"] + [chn.replace("_", " ").title() for chn in channel_names]

    rows: List[List[Any]] = []
    n = len(t)
    for i in range(0, n, max(1, sample_stride)):
        row = [float(t[i])] + [float(channels[chn][i]) for chn in channel_names]
        rows.append(row)

    aria_summary = f"Summary data table containing {len(rows)} sampled rows across {len(channel_names)} channels."
    return AccessibleTableData(
        title=title,
        summary_aria=aria_summary,
        column_headers=headers,
        rows=rows,
    )
