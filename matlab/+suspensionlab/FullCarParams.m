classdef FullCarParams < handle
    % FULLCARPARAMS Physical parameters for the 7-DOF Full Car Ride Model.
    %
    % SuspensionLab PRO Industrial CAE Toolbox
    
    properties
        m_s     (1,1) double {mustBePositive} = 1200.0
        m_uf    (1,1) double {mustBePositive} = 45.0
        m_ur    (1,1) double {mustBePositive} = 40.0
        I_x     (1,1) double {mustBePositive} = 350.0
        I_y     (1,1) double {mustBePositive} = 1200.0
        a       (1,1) double {mustBePositive} = 1.20
        b       (1,1) double {mustBePositive} = 1.50
        tw_f    (1,1) double {mustBePositive} = 1.60
        tw_r    (1,1) double {mustBePositive} = 1.55
        k_sf    (1,1) double {mustBeNonnegative} = 35000.0
        k_sr    (1,1) double {mustBeNonnegative} = 40000.0
        c_f     (1,1) double {mustBeNonnegative} = 2200.0
        c_r     (1,1) double {mustBeNonnegative} = 2500.0
        k_arb_f (1,1) double {mustBeNonnegative} = 1200.0
        k_arb_r (1,1) double {mustBeNonnegative} = 900.0
        k_tf    (1,1) double {mustBePositive} = 220000.0
        k_tr    (1,1) double {mustBePositive} = 220000.0
        speed_mps (1,1) double {mustBePositive} = 20.0
    end
    
    methods
        function obj = FullCarParams(varargin)
            if nargin > 0
                p = inputParser;
                fields = properties(obj);
                for i = 1:length(fields)
                    addParameter(p, fields{i}, obj.(fields{i}));
                end
                parse(p, varargin{:});
                for i = 1:length(fields)
                    obj.(fields{i}) = p.Results.(fields{i});
                end
            end
        end
        
        function s = toStruct(obj)
            fields = properties(obj);
            s = struct();
            for i = 1:length(fields)
                s.(fields{i}) = obj.(fields{i});
            end
        end
        
        function jsonStr = toJson(obj)
            jsonStr = jsonencode(obj.toStruct());
        end
    end
end
