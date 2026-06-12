// @ts-nocheck

"use client";

import { useEffect, useState, useRef } from "react";
import GGFrictionCircle from "../../components/GGFrictionCircle";
import TelemetryGauges from "../../components/TelemetryGauges";
import { Play, Square } from "lucide-react";

export default function DigitalTwinPage() {
  const [isConnected, setIsConnected] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  
  // Payload state
  const [telemetry, setTelemetry] = useState({
    speedMs: 0,
    latG: 0,
    longG: 0,
    maxG: 1.5,
    divergencePct: 0,
    status: "Waiting for data..."
  });

  const wsRef = useRef<WebSocket | null>(null);
  const simIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Connect to WS
  useEffect(() => {
    const connectWs = () => {
      const wsUrl = "ws://localhost:8000/telemetry/live";
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => setIsConnected(false);
      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setTelemetry(prev => ({
            ...prev,
            maxG: data.theoretical_max_lat_g ?? prev.maxG,
            divergencePct: data.divergence_pct ?? prev.divergencePct,
            status: data.grip_status ?? prev.status
          }));
        } catch (err) {
          console.error("Failed to parse websocket message:", err);
        }
      };
      wsRef.current = ws;
    };
    
    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (simIntervalRef.current) clearInterval(simIntervalRef.current);
    };
  }, []);

  const toggleMockSimulation = () => {
    if (isSimulating) {
      if (simIntervalRef.current) clearInterval(simIntervalRef.current);
      setIsSimulating(false);
      setTelemetry(prev => ({ ...prev, speedMs: 0, latG: 0, longG: 0, status: "Stopped" }));
    } else {
      setIsSimulating(true);
      let tick = 0;
      simIntervalRef.current = setInterval(() => {
        tick++;
        const speed = 20.0 + (tick * 0.1);
        const lat = 1.2 * Math.sin(tick * 0.1);
        const long = 0.5 * Math.cos(tick * 0.05);
        
        setTelemetry(prev => ({ ...prev, speedMs: speed, latG: lat, longG: long }));
        
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            speed_ms: speed,
            lat_g: lat,
            long_g: long,
            steer_rad: 0.05
          }));
        }
      }, 50); // 20Hz update rate
    }
  };

  return (
    <div className="w-full h-full p-8 flex flex-col space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Digital Twin</h1>
          <p className="text-gray-400 mt-1">Live F1-Grade Telemetry & Grip Utilization</p>
        </div>
        
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 bg-black/50 px-3 py-1.5 rounded-full border border-white/10">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-300">{isConnected ? 'DAQ Connected' : 'Disconnected'}</span>
          </div>
          
          <button 
            onClick={toggleMockSimulation}
            className={`flex items-center space-x-2 px-4 py-2 rounded-md font-medium text-sm transition-all ${
              isSimulating 
                ? 'bg-red-500/10 text-red-500 border border-red-500/30 hover:bg-red-500/20' 
                : 'bg-ansys-yellow text-black hover:bg-yellow-400'
            }`}
          >
            {isSimulating ? <Square size={16} /> : <Play size={16} />}
            <span>{isSimulating ? "Stop Mock DAQ" : "Start Mock DAQ"}</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[400px]">
        <div className="col-span-1 h-full flex items-center justify-center">
          <GGFrictionCircle 
            maxG={telemetry.maxG} 
            latG={telemetry.latG} 
            longG={telemetry.longG} 
          />
        </div>
        
        <div className="col-span-1 lg:col-span-2 h-full">
          <TelemetryGauges 
            speedMs={telemetry.speedMs}
            divergencePct={telemetry.divergencePct}
            status={telemetry.status}
          />
        </div>
      </div>
    </div>
  );
}
