classdef RoadProfile < handle
    % ROADPROFILE Excitation road profile definition.
    %
    % SuspensionLab PRO Industrial CAE Toolbox
    %
    % Supported profile types:
    %   'step'    - Step excitation displacement
    %   'sine'    - Harmonic single-frequency road waviness
    %   'pothole' - Localized pothole depression
    %   'random'  - Multi-harmonic stochastic road surface
    %   'iso8608' - ISO 8608 Class A-H PSD synthesized road
    
    properties
        profile_type (1,:) char {mustBeMember(profile_type, {'step', 'sine', 'pothole', 'random', 'iso8608'})} = 'step'
        amplitude    (1,1) double {mustBeNonnegative} = 0.05
        frequency    (1,1) double {mustBePositive} = 2.0
        duration     (1,1) double {mustBePositive} = 5.0
        speed_mps    (1,1) double {mustBePositive} = 20.0
        iso_class    (1,1) char = 'A'
    end
    
    methods
        function obj = RoadProfile(varargin)
            if nargin > 0
                p = inputParser;
                addParameter(p, 'profile_type', 'step');
                addParameter(p, 'amplitude', 0.05);
                addParameter(p, 'frequency', 2.0);
                addParameter(p, 'duration', 5.0);
                addParameter(p, 'speed_mps', 20.0);
                addParameter(p, 'iso_class', 'A');
                parse(p, varargin{:});
                
                obj.profile_type = p.Results.profile_type;
                obj.amplitude    = p.Results.amplitude;
                obj.frequency    = p.Results.frequency;
                obj.duration     = p.Results.duration;
                obj.speed_mps    = p.Results.speed_mps;
                obj.iso_class    = p.Results.iso_class;
            end
        end
        
        function s = toStruct(obj)
            s = struct(...
                'profile_type', obj.profile_type, ...
                'amplitude',    obj.amplitude, ...
                'frequency',    obj.frequency, ...
                'duration',     obj.duration, ...
                'speed_mps',    obj.speed_mps, ...
                'iso_class',    obj.iso_class ...
            );
        end
        
        function jsonStr = toJson(obj)
            jsonStr = jsonencode(obj.toStruct());
        end
    end
end
