"use client";

interface TelemetryGaugesProps {
  speedMs: number;
  divergencePct: number;
  status: string;
}

export default function TelemetryGauges({ speedMs, divergencePct, status }: TelemetryGaugesProps) {
  const speedKmh = speedMs * 3.6;
  
  // Color coding based on divergence
  let statusColor = "text-ansys-yellow"; // default
  if (status.includes("Optimal")) statusColor = "text-green-400";
  else if (status.includes("Exceeding")) statusColor = "text-red-500";
  
  return (
    <div className="w-full h-full bg-[#0d0d0f] rounded-xl border border-white/10 p-6 flex flex-col justify-center space-y-6">
      <h2 className="text-xl font-semibold text-white tracking-tight">Live Telemetry</h2>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col bg-black/50 p-4 rounded-lg border border-white/5">
          <span className="text-xs text-gray-400 uppercase tracking-wider">Speed</span>
          <span className="text-3xl font-mono text-white">{speedKmh.toFixed(1)} <span className="text-sm text-gray-500">km/h</span></span>
        </div>
        
        <div className="flex flex-col bg-black/50 p-4 rounded-lg border border-white/5">
          <span className="text-xs text-gray-400 uppercase tracking-wider">Grip Divergence</span>
          <span className={`text-3xl font-mono ${statusColor}`}>{divergencePct.toFixed(1)}%</span>
        </div>
      </div>
      
      <div className="flex flex-col bg-black/50 p-4 rounded-lg border border-white/5">
        <span className="text-xs text-gray-400 uppercase tracking-wider mb-1">Status</span>
        <span className={`text-sm font-semibold ${statusColor}`}>{status}</span>
      </div>
    </div>
  );
}
