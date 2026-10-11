classdef SimulationResult < handle
    % SIMULATIONRESULT Typed result container for SuspensionLab simulations.
    %
    % SuspensionLab PRO Industrial CAE Toolbox
    
    properties
        Time                  (:,1) double
        SprungDisplacement    (:,1) double
        UnsprungDisplacement  (:,1) double
        SuspensionTravel      (:,1) double
        DynamicTireLoad       (:,1) double
        BodyAcceleration      (:,1) double
        RoadDisplacement      (:,1) double
        RawData               struct
    end
    
    methods
        function obj = SimulationResult(raw)
            if nargin > 0 && isstruct(raw)
                obj.RawData = raw;
                
                % Parse time
                if isfield(raw, 'time')
                    obj.Time = raw.time(:);
                elseif isfield(raw, 't')
                    obj.Time = raw.t(:);
                else
                    obj.Time = [];
                end
                
                % Parse displacements
                if isfield(raw, 'z_s'), obj.SprungDisplacement = raw.z_s(:); end
                if isfield(raw, 'z_u'), obj.UnsprungDisplacement = raw.z_u(:); end
                if isfield(raw, 'susp_travel'), obj.SuspensionTravel = raw.susp_travel(:); end
                if isfield(raw, 'tire_load_var'), obj.DynamicTireLoad = raw.tire_load_var(:); end
                if isfield(raw, 'tire_load_dynamic'), obj.DynamicTireLoad = raw.tire_load_dynamic(:); end
                if isfield(raw, 'ddz_s'), obj.BodyAcceleration = raw.ddz_s(:); end
                if isfield(raw, 'body_accel'), obj.BodyAcceleration = raw.body_accel(:); end
                if isfield(raw, 'z_r'), obj.RoadDisplacement = raw.z_r(:); end
                if isfield(raw, 'z_road'), obj.RoadDisplacement = raw.z_road(:); end
            end
        end
        
        function tbl = toTable(obj)
            % TOTABLE Convert channels to standard MATLAB table
            tbl = table(obj.Time, obj.SprungDisplacement, obj.UnsprungDisplacement, ...
                obj.SuspensionTravel, obj.DynamicTireLoad, obj.BodyAcceleration, ...
                'VariableNames', {'Time_s', 'SprungDisp_m', 'UnsprungDisp_m', ...
                'SuspTravel_m', 'DynamicTireLoad_N', 'BodyAccel_mps2'});
        end
        
        function tt = toTimetable(obj)
            % TOTIMETABLE Convert channels to standard MATLAB timetable
            if isempty(obj.Time)
                error('SimulationResult:NoTime', 'Time vector is empty.');
            end
            timeSec = seconds(obj.Time);
            tt = timetable(timeSec, obj.SprungDisplacement, obj.UnsprungDisplacement, ...
                obj.SuspensionTravel, obj.DynamicTireLoad, obj.BodyAcceleration, ...
                'VariableNames', {'SprungDisp_m', 'UnsprungDisp_m', ...
                'SuspTravel_m', 'DynamicTireLoad_N', 'BodyAccel_mps2'});
        end
        
        function val = getRMS(obj, channel)
            % GETRMS Calculate Root-Mean-Square of specified channel
            switch lower(channel)
                case {'body_accel', 'accel', 'ddz_s'}
                    sig = obj.BodyAcceleration;
                case {'susp_travel', 'travel'}
                    sig = obj.SuspensionTravel;
                case {'tire_load', 'load'}
                    sig = obj.DynamicTireLoad;
                case {'z_s', 'sprung'}
                    sig = obj.SprungDisplacement;
                otherwise
                    error('SimulationResult:UnknownChannel', 'Unknown channel: %s', channel);
            end
            val = sqrt(mean(sig.^2));
        end
        
        function hFig = plot(obj)
            % PLOT Render professional vehicle dynamics subplots
            hFig = figure('Name', 'SuspensionLab Simulation Results', 'Color', 'w');
            
            subplot(3,1,1);
            plot(obj.Time, obj.SprungDisplacement*1000, 'b-', 'LineWidth', 1.5); hold on;
            plot(obj.Time, obj.UnsprungDisplacement*1000, 'r--', 'LineWidth', 1.2);
            if ~isempty(obj.RoadDisplacement)
                plot(obj.Time, obj.RoadDisplacement*1000, 'k:', 'LineWidth', 1.0);
                legend('Sprung (z_s)', 'Unsprung (z_u)', 'Road (z_r)');
            else
                legend('Sprung (z_s)', 'Unsprung (z_u)');
            end
            ylabel('Displacement [mm]'); grid on;
            title('Vehicle Vertical Displacements');
            
            subplot(3,1,2);
            plot(obj.Time, obj.SuspensionTravel*1000, 'm-', 'LineWidth', 1.5);
            ylabel('Travel [mm]'); grid on;
            title('Suspension Deflection Stroke (z_s - z_u)');
            
            subplot(3,1,3);
            plot(obj.Time, obj.BodyAcceleration, 'k-', 'LineWidth', 1.2);
            ylabel('Acceleration [m/s^2]'); xlabel('Time [s]'); grid on;
            title(sprintf('Body Vertical Acceleration (RMS: %.2f m/s^2)', obj.getRMS('body_accel')));
        end
    end
end
