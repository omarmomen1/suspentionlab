# SuspensionLab PRO — MATLAB & Simulink Industrial CAE Toolbox

Enterprise integration toolbox for connecting MATLAB, Simulink, and hardware-in-the-loop (HIL) simulators to SuspensionLab PRO cloud and edge physics engines.

---

## Architecture Overview

```
matlab/
├── +suspensionlab/              # Typed Object-Oriented MATLAB Package
│   ├── Client.m                 # Production REST API Client
│   ├── QuarterCarParams.m       # 2-DOF Parameter Value Object
│   ├── FullCarParams.m          # 7-DOF Parameter Value Object
│   ├── RoadProfile.m            # Excitation Definition Object
│   ├── SimulationResult.m       # Typed Time/Freq Domain Results
│   └── OptimizationResult.m     # Pareto Trade-off Container
├── simulink/
│   ├── SuspensionLabQuarterCarBlock.m  # Native MATLAB System Block
│   └── load_fmu_into_simulink.m        # Simulink FMU Block Importer
└── README.md
```

---

## 1. Quickstart: MATLAB Toolbox

Add the toolbox to your MATLAB path:

```matlab
addpath('D:\project\matlab');
```

Initialize the client:

```matlab
client = suspensionlab.Client('sk_enterprise_key_here', 'https://api.suspensionlab.com');
```

### Run a Quarter Car Simulation

```matlab
params = suspensionlab.QuarterCarParams(...
    'm_s', 280.0, ...
    'k_s', 26000.0, ...
    'c', 1900.0, ...
    'MR', 0.90);

profile = suspensionlab.RoadProfile(...
    'profile_type', 'step', ...
    'amplitude', 0.03, ...
    'duration', 3.0);

result = client.simulateQuarterCar(params, profile);

% Access typed vectors
t = result.Time;
zs = result.SprungDisplacement;
accel_rms = result.getRMS('body_accel');

% Render subplots
result.plot();
```

---

## 2. Simulink Integration

### Method A: Native MATLAB System Block
Drag `SuspensionLabQuarterCarBlock` directly into any Simulink model.
- **Inputs**: `[z_road, dz_road]`
- **Outputs**: `[z_s, z_u, susp_travel, tire_load, body_accel]`

### Method B: FMI 2.0 Co-Simulation Block
Use the official FMU block provided in Simulink:
1. Open Simulink Library Browser.
2. Select **Simulink -> Ports & Subsystems -> FMU**.
3. Point the block to `QuarterCarRideModel.fmu`.
4. All inputs, outputs, and parameters automatically populate with units.

---

## 3. CAE Model Exporters

Download production solver datasets directly into your workflow:

```matlab
% Export FMI 2.0 Co-Simulation Archive (.fmu)
client.exportCAE('fmu', [], 'QuarterCarRideModel.fmu');

% Export MSC ADAMS View Command Deck (.cmd)
client.exportCAE('adams_cmd', params, 'Quarter_Car_Rig.cmd');

% Export Simulink Initialization Script (.m)
client.exportCAE('simulink', fullCarParams, 'init_full_car.m');
```
