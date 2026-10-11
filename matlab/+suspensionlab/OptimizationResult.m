classdef OptimizationResult < handle
    % OPTIMIZATIONRESULT Container for multi-objective optimization results.
    %
    % SuspensionLab PRO Industrial CAE Toolbox
    
    properties
        JobId              (1,:) char
        Status             (1,:) char
        OptimalParams      struct
        ParetoFront        struct
        SensitivityRanking struct
        ConvergenceHistory struct
        RawData            struct
    end
    
    methods
        function obj = OptimizationResult(raw)
            if nargin > 0 && isstruct(raw)
                obj.RawData = raw;
                if isfield(raw, 'job_id'), obj.JobId = raw.job_id; end
                if isfield(raw, 'status'), obj.Status = raw.status; end
                if isfield(raw, 'optimal_params'), obj.OptimalParams = raw.optimal_params; end
                if isfield(raw, 'pareto_front'), obj.ParetoFront = raw.pareto_front; end
                if isfield(raw, 'sensitivity'), obj.SensitivityRanking = raw.sensitivity; end
                if isfield(raw, 'history'), obj.ConvergenceHistory = raw.history; end
            end
        end
        
        function hFig = plotPareto(obj, objX, objY)
            % PLOTPARETO Plot 2D Pareto trade-off frontier
            if nargin < 2, objX = 'rms_accel'; end
            if nargin < 3, objY = 'rms_travel'; end
            
            hFig = figure('Name', 'SuspensionLab Pareto Optimal Frontier', 'Color', 'w');
            if isfield(obj.ParetoFront, objX) && isfield(obj.ParetoFront, objY)
                x = obj.ParetoFront.(objX);
                y = obj.ParetoFront.(objY);
                scatter(x, y, 60, 'filled', 'MarkerFaceColor', [0.1 0.5 0.9]);
                grid on;
                xlabel(objX, 'Interpreter', 'none');
                ylabel(objY, 'Interpreter', 'none');
                title('Multi-Objective Pareto Frontier');
            else
                text(0.5, 0.5, 'Pareto front objective data not available', ...
                    'HorizontalAlignment', 'center');
            end
        end
    end
end
