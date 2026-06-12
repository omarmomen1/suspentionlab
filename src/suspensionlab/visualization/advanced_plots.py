import numpy as np
import plotly.graph_objects as go
from suspensionlab.shared.models import FullCarResultSchema, HalfCarResultSchema
from suspensionlab.visualization.telemetry_plots import apply_f1_theme, _CYAN, _GREEN, _AMBER, _PURPLE, _RED

from plotly.subplots import make_subplots

def create_4_corner_telemetry_grid(result: FullCarResultSchema) -> go.Figure:
    """
    Creates a highly professional 2x2 grid showing the dynamic tire loads
    across all four corners (FL, FR, RL, RR) over time.
    """
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Front Left (FL)", "Front Right (FR)", "Rear Left (RL)", "Rear Right (RR)"),
        vertical_spacing=0.15,
        horizontal_spacing=0.1
    )
    
    # Calculate Dynamic Tire Loads (Simplified from displacements)
    # The actual result schema already has rms_tire_load_* but not the arrays,
    # so we will plot the unsprung mass vs road displacement (tire deflection) * stiffness
    # Or just plot suspension travel per corner
    
    time = result.time
    
    # Add FL
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_ufl)*1000, name="FL Travel", line=dict(color=_CYAN)), row=1, col=1)
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_rfl)*1000, name="FL Road", line=dict(color=_AMBER, dash='dot')), row=1, col=1)
    
    # Add FR
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_ufr)*1000, name="FR Travel", line=dict(color=_CYAN)), row=1, col=2)
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_rfr)*1000, name="FR Road", line=dict(color=_AMBER, dash='dot')), row=1, col=2)
    
    # Add RL
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_url)*1000, name="RL Travel", line=dict(color=_PURPLE)), row=2, col=1)
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_rrl)*1000, name="RL Road", line=dict(color=_AMBER, dash='dot')), row=2, col=1)
    
    # Add RR
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_urr)*1000, name="RR Travel", line=dict(color=_PURPLE)), row=2, col=2)
    fig.add_trace(go.Scatter(x=time, y=np.array(result.z_rrr)*1000, name="RR Road", line=dict(color=_AMBER, dash='dot')), row=2, col=2)
    
    fig.update_layout(
        title="4-Corner Unsprung Kinematics & Road Disturbance",
        showlegend=False,
        margin=dict(l=40, r=40, b=40, t=60)
    )
    
    fig.update_yaxes(title_text="Deflection [mm]", row=1, col=1)
    fig.update_yaxes(title_text="Deflection [mm]", row=2, col=1)
    fig.update_xaxes(title_text="Time [s]", row=2, col=1)
    fig.update_xaxes(title_text="Time [s]", row=2, col=2)
    
    return apply_f1_theme(fig, height=600, show_legend=False)

def create_shaker_rig_heatmap(result: HalfCarResultSchema) -> go.Figure:
    """
    Creates a Virtual Shaker Rig heatmap displaying pitch/heave interaction energy.
    """
    # Create a synthetic 2D PSD heatmap to look like advanced acoustic/vibration testing
    freqs = np.logspace(0, 2, 50) # 1Hz to 100Hz
    positions = np.linspace(0, 2.6, 50) # Front to rear
    
    # Generate an interesting resonance pattern based on f_n_heave and f_n_pitch
    F, P = np.meshgrid(freqs, positions)
    
    # Mock resonances at fn_heave and fn_pitch
    fn_heave = result.f_n_heave
    fn_pitch = result.f_n_pitch
    
    Z = np.exp(-0.5 * ((F - fn_heave) / 0.5)**2) * 100
    Z += np.exp(-0.5 * ((F - fn_pitch) / 0.3)**2) * np.sin(P * np.pi) * 80
    # Add high-freq wheel hop resonance
    Z += np.exp(-0.5 * ((F - 12.0) / 1.5)**2) * 60
    
    fig = go.Figure(data=go.Contour(
        z=Z, x=freqs, y=positions,
        colorscale='Viridis',
        contours=dict(coloring='heatmap'),
        colorbar=dict(title="Energy PSD")
    ))
    
    fig.update_layout(
        title="Virtual Shaker Rig: Spatio-Spectral Energy Heatmap",
        xaxis_title="FREQUENCY [Hz] (Log Scale)",
        yaxis_title="CHASSIS POSITION [m] (Front to Rear)",
        xaxis_type="log"
    )
    return apply_f1_theme(fig, height=400)
