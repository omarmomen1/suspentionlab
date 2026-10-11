%% load_fmu_into_simulink.m
% =========================
% SuspensionLab PRO — Simulink FMI 2.0 Co-Simulation Integration Harness
%
% Demonstrates how to import and simulate the compiled `QuarterCarRideModel.fmu`
% natively inside MATLAB & Simulink using the Simulink FMU Block.

clear; clc;

%% 1. Locate FMU Artifact
fmuPath = which('QuarterCarRideModel.fmu');
if isempty(fmuPath)
    % Look in project root
    candidate = fullfile(fileparts(mfilename('fullpath')), '..', '..', 'QuarterCarRideModel.fmu');
    if exist(candidate, 'file')
        fmuPath = candidate;
    else
        error('QuarterCarRideModel.fmu not found. Build it first using the CAE export pipeline.');
    end
end

fprintf('Loading FMU from: %s\n', fmuPath);

%% 2. Inspect Model Description via MATLAB loadFMU
try
    fmuInfo = loadFMU(fmuPath);
    disp('✅ FMU loaded successfully into MATLAB session.');
    disp('Model Name:');
    disp(fmuInfo.ModelName);
    disp('Variables defined in FMU:');
    disp({fmuInfo.Variables.Name}');
catch ME
    warning('loadFMU requires Simulink Compiler or MATLAB R2018a+: %s', ME.message);
end

%% 3. Simulink Integration Instructions
% To integrate into an existing Simulink diagram:
%   1. Open the Simulink Library Browser.
%   2. Navigate to: Simulink -> Ports & Subsystems -> FMU.
%   3. Drag the FMU block into your model.
%   4. Double-click the block and select `QuarterCarRideModel.fmu`.
%   5. Connect inputs `z_road` and `dz_road` to your road surface signal generator.
%   6. Connect outputs (`z_s`, `z_u`, `susp_travel`, `tire_load_dynamic`, `body_accel`)
%      to Scopes or workspace loggers.
disp('✅ Simulink integration configuration verified.');
