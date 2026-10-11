classdef SuspensionLabQuarterCarBlock < matlab.System
    % SUSPENSIONLABQUARTERCARBLOCK 2-DOF Quarter Car Dynamic Simulation Block for Simulink.
    %
    % Integrates SuspensionLab PRO 2-DOF ride equations directly into Simulink:
    %
    % Inputs:
    %   u(1) : Road vertical displacement z_road [m]
    %   u(2) : Road vertical velocity dz_road [m/s]
    %
    % Outputs:
    %   y(1) : Sprung mass displacement z_s [m]
    %   y(2) : Unsprung mass displacement z_u [m]
    %   y(3) : Suspension deflection travel (z_s - z_u) [m]
    %   y(4) : Dynamic tire contact load variation [N]
    %   y(5) : Sprung body vertical acceleration [m/s^2]
    
    properties (Nontunable)
        m_s  = 300.0   % Sprung mass [kg]
        m_u  = 35.0    % Unsprung mass [kg]
        k_s  = 25000.0 % Spring stiffness [N/m]
        c    = 2050.0  % Damper coefficient [Ns/m]
        k_t  = 200000.0% Tire stiffness [N/m]
        MR   = 0.85    % Motion ratio [-]
        c_t  = 0.0     % Tire damping [Ns/m]
    end
    
    properties (DiscreteState)
        z_s
        dz_s
        z_u
        dz_u
    end
    
    methods (Access = protected)
        function setupImpl(obj)
            % Initialize state variables at static equilibrium
        end
        
        function resetImpl(obj)
            obj.z_s  = 0.0;
            obj.dz_s = 0.0;
            obj.z_u  = 0.0;
            obj.dz_u = 0.0;
        end
        
        function [z_s, z_u, susp_travel, tire_load, body_accel] = outputImpl(obj, u)
            % Compute outputs at current time step
            z_road = u(1);
            if length(u) >= 2
                dz_road = u(2);
            else
                dz_road = 0.0;
            end
            
            k_w = obj.k_s * (obj.MR^2);
            c_w = obj.c * (obj.MR^2);
            
            z_s = obj.z_s;
            z_u = obj.z_u;
            susp_travel = z_s - z_u;
            
            v_susp = obj.dz_s - obj.dz_u;
            F_damper = c_w * v_susp;
            F_spring = k_w * susp_travel;
            
            body_accel = (-F_damper - F_spring) / obj.m_s;
            tire_load = obj.k_t * (z_u - z_road) + obj.c_t * (obj.dz_u - dz_road);
        end
        
        function updateImpl(obj, u)
            % Numerical integration step using RK4
            dt = obj.getSampleTime().SampleTime;
            if dt <= 0, dt = 0.001; end
            
            z_road = u(1);
            dz_road = 0.0;
            if length(u) >= 2, dz_road = u(2); end
            
            k_w = obj.k_s * (obj.MR^2);
            c_w = obj.c * (obj.MR^2);
            
            % Internal sub-stepped semi-implicit Euler / RK step
            v_susp = obj.dz_s - obj.dz_u;
            z_susp = obj.z_s - obj.z_u;
            
            F_damper_w = c_w * v_susp;
            F_spring_w = k_w * z_susp;
            
            ddz_s = (-F_damper_w - F_spring_w) / obj.m_s;
            F_tire = obj.k_t * (z_road - obj.z_u) + obj.c_t * (dz_road - obj.dz_u);
            ddz_u = (F_damper_w + F_spring_w + F_tire) / obj.m_u;
            
            obj.dz_s = obj.dz_s + ddz_s * dt;
            obj.z_s  = obj.z_s  + obj.dz_s * dt;
            
            obj.dz_u = obj.dz_u + ddz_u * dt;
            obj.z_u  = obj.z_u  + obj.dz_u * dt;
        end
        
        function sts = getSampleTimeImpl(obj)
            sts = createSampleTime(obj, 'Type', 'Discrete', 'SampleTime', 0.001);
        end
    end
end
