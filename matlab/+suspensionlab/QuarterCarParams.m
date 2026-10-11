classdef QuarterCarParams < handle
    % QUARTERCARPARAMS Physical parameters for the 2-DOF Quarter Car Model.
    %
    % SuspensionLab PRO Industrial CAE Toolbox
    %
    % Properties:
    %   m_s : Sprung mass [kg]
    %   m_u : Unsprung mass [kg]
    %   k_s : Suspension coil spring stiffness [N/m]
    %   c   : Damper damping coefficient [Ns/m]
    %   k_t : Tire radial stiffness [N/m]
    %   MR  : Motion ratio (spring travel / wheel travel) [-]
    %   c_t : Tire damping rate [Ns/m]
    
    properties
        m_s (1,1) double {mustBePositive} = 300.0
        m_u (1,1) double {mustBePositive} = 35.0
        k_s (1,1) double {mustBeNonnegative} = 25000.0
        c   (1,1) double {mustBeNonnegative} = 2050.0
        k_t (1,1) double {mustBePositive} = 200000.0
        MR  (1,1) double {mustBePositive} = 0.85
        c_t (1,1) double {mustBeNonnegative} = 0.0
    end
    
    properties (Dependent)
        k_w (1,1) double % Wheel rate [N/m] = k_s * MR^2
        c_w (1,1) double % Wheel damping rate [Ns/m] = c * MR^2
    end
    
    methods
        function obj = QuarterCarParams(varargin)
            % QUARTERCARPARAMS Construct parameter set from name-value pairs.
            if nargin > 0
                p = inputParser;
                addParameter(p, 'm_s', 300.0);
                addParameter(p, 'm_u', 35.0);
                addParameter(p, 'k_s', 25000.0);
                addParameter(p, 'c', 2050.0);
                addParameter(p, 'k_t', 200000.0);
                addParameter(p, 'MR', 0.85);
                addParameter(p, 'c_t', 0.0);
                parse(p, varargin{:});
                
                obj.m_s = p.Results.m_s;
                obj.m_u = p.Results.m_u;
                obj.k_s = p.Results.k_s;
                obj.c   = p.Results.c;
                obj.k_t = p.Results.k_t;
                obj.MR  = p.Results.MR;
                obj.c_t = p.Results.c_t;
            end
            obj.validate();
        end
        
        function val = get.k_w(obj)
            val = obj.k_s * (obj.MR ^ 2);
        end
        
        function val = get.c_w(obj)
            val = obj.c * (obj.MR ^ 2);
        end
        
        function validate(obj)
            % VALIDATE Validate mechanical sanity
            if obj.m_u >= obj.m_s
                error('QuarterCarParams:InvalidMass', ...
                    'Unsprung mass (%.1f kg) must be strictly less than sprung mass (%.1f kg).', ...
                    obj.m_u, obj.m_s);
            end
            if obj.MR > 1.5 || obj.MR < 0.1
                error('QuarterCarParams:InvalidMotionRatio', ...
                    'Motion Ratio MR=%.2f outside realistic mechanical bounds (0.1, 1.5].', obj.MR);
            end
        end
        
        function s = toStruct(obj)
            % TOSTRUCT Serialize parameters to struct for API ingestion
            s = struct(...
                'm_s', obj.m_s, ...
                'm_u', obj.m_u, ...
                'k_s', obj.k_s, ...
                'c',   obj.c, ...
                'k_t', obj.k_t, ...
                'MR',  obj.MR, ...
                'c_t', obj.c_t ...
            );
        end
        
        function jsonStr = toJson(obj)
            % TOJSON Convert to JSON string
            jsonStr = jsonencode(obj.toStruct());
        end
    end
end
