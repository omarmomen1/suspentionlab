# SuspensionLab PRO - Headless SDK

This is the Python SDK for accessing the SuspensionLab PRO solver headless.
Perfect for batch optimizations, parameter sweeps, and machine learning pipelines.

## Installation
```bash
pip install .
```

## Quick Start
```python
from suspensionlab import SuspensionLabClient

client = SuspensionLabClient(base_url="http://localhost:8000", api_key="YOUR_KEY")

res = client.simulate_quarter_car({
    "m_s": 350.0,
    "m_u": 40.0,
    "k_s": 25000.0,
    "k_t": 200000.0,
    "c": 1500.0,
    "speed_kph": 72.0,
    "road_profile": "step",
    "amplitude": 0.05
})

print("Max Sprung Accel:", max(res['z_s_ddot']))
```
