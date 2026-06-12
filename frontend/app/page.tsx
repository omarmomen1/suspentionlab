"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { Play, CheckCircle2 } from "lucide-react";
import Link from "next/link";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const NVH_DEMO_DATA = (() => {
    const rows = [];
    for (let i = 0; i < 20; i++) {
        const row = [];
        for (let j = 0; j < 20; j++) {
            // Simulate a frequency response heatmap with two resonance peaks
            const f = i * 2.5 + 0.5;   // frequency [Hz]
            const v = j * 5 + 10;       // speed [km/h]
            const peak1 = 80 * Math.exp(-((f - 8) ** 2 + (v - 40) ** 2) / 100);
            const peak2 = 60 * Math.exp(-((f - 15) ** 2 + (v - 80) ** 2) / 200);
            row.push(peak1 + peak2 + 5);
        }
        rows.push(row);
    }
    return rows;
})();

export default function Home() {
  const [mounted, setMounted] = useState(false);
   
  useEffect(() => setMounted(true), []);

  return (
    <div className="w-full bg-black text-white selection:bg-ansys-yellow selection:text-black pb-24">
      
      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6 max-w-[1024px] mx-auto text-center flex flex-col items-center">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-ansys-yellow/10 blur-[120px] rounded-full pointer-events-none"></div>
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 relative z-10">
          Stop Guessing. <br/><span className="text-transparent bg-clip-text bg-gradient-to-r from-ansys-yellow to-[#ff9900]">Start Winning.</span>
        </h1>
        <p className="text-xl md:text-2xl text-gray-400 max-w-2xl font-light mb-10 relative z-10">
          The ultimate vehicle dynamics simulation suite. Sub-millisecond precision, 7-post rig capabilities, and AI-driven tuning built for Tier-1 OEMs and elite racing teams.
        </p>
        <div className="flex items-center gap-4 relative z-10">
          <Link href="/pricing" className="px-8 py-4 bg-white text-black font-semibold rounded-full hover:bg-gray-200 transition-transform hover:scale-105 active:scale-95">
            Subscribe Now — $300/mo
          </Link>
          <Link href="/quarter-car" className="px-8 py-4 bg-transparent text-white font-semibold rounded-full border border-white/20 hover:bg-white/5 transition-colors flex items-center gap-2">
            Try Demo <Play size={16} fill="currentColor" />
          </Link>
        </div>
      </section>

      {/* Feature 1: NVH Analyzer (Text Left, Graph Right) */}
      <section className="py-24 px-6 border-t border-white/10 bg-[#0a0a0a]">
        <div className="max-w-[1024px] mx-auto flex flex-col md:flex-row items-center gap-16">
          <div className="flex-1 space-y-6">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Acoustics & NVH. <br/><span className="text-gray-500">Isolate resonance instantly.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Don&apos;t rely on blind luck to solve cabin drone. Perform highly optimized Fast Fourier Transforms (FFT) on chassis acceleration data to identify modal frequencies and optimize ride comfort before building a single physical prototype.
            </p>
            <ul className="space-y-3 pt-4">
              {["Full-spectrum frequency analysis", "Multi-modal harmonic detection", "Export-ready compliance reports"].map((f, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300"><CheckCircle2 size={18} className="text-ansys-yellow"/> {f}</li>
              ))}
            </ul>
          </div>
          <div className="flex-1 w-full aspect-square md:aspect-auto md:h-[400px] bg-black border border-white/10 rounded-2xl overflow-hidden shadow-2xl relative">
            {mounted && (
              <Plot
                data={[
                  {
                    z: NVH_DEMO_DATA,
                    type: 'heatmap',
                    colorscale: 'Inferno',
                    showscale: false
                  }
                ]}
                layout={{
                  autosize: true,
                  margin: { l: 20, r: 20, t: 20, b: 20 },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  xaxis: { visible: false },
                  yaxis: { visible: false },
                }}
                useResizeHandler={true}
                style={{ width: "100%", height: "100%" }}
                config={{ displayModeBar: false }}
              />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent pointer-events-none"></div>
          </div>
        </div>
      </section>

      {/* Feature 2: Sensitivity Sweep (Graph Left, Text Right) */}
      <section className="py-24 px-6 border-t border-white/10 bg-black">
        <div className="max-w-[1024px] mx-auto flex flex-col md:flex-row-reverse items-center gap-16">
          <div className="flex-1 space-y-6">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Parametric Sweeps. <br/><span className="text-gray-500">Find the absolute limit.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Why test one setup when you can test a million? Automate batch runs sweeping through spring rates, damper curves, and anti-roll stiffness. Generate interactive 3D contour maps to visualize the exact boundary of mechanical grip.
            </p>
            <ul className="space-y-3 pt-4">
              {["100x faster than real-world testing", "GPU-accelerated solving", "3D topological limit mapping"].map((f, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300"><CheckCircle2 size={18} className="text-[#0071e3]"/> {f}</li>
              ))}
            </ul>
          </div>
          <div className="flex-1 w-full aspect-square md:aspect-auto md:h-[400px] bg-[#0a0a0a] border border-white/10 rounded-2xl overflow-hidden shadow-2xl relative">
            {mounted && (
              <Plot
                data={[
                  {
                    z: [
                      [8.83,8.89,8.81,8.87,8.9,8.87],
                      [8.89,8.94,8.85,8.94,8.96,8.92],
                      [8.84,8.9,8.82,8.92,8.93,8.91],
                      [8.79,8.85,8.79,8.9,8.94,8.92],
                      [8.79,8.88,8.81,8.9,8.95,8.92]
                    ],
                    type: 'surface',
                    colorscale: 'Viridis',
                    showscale: false
                  }
                ]}
                layout={{
                  autosize: true,
                  margin: { l: 0, r: 0, t: 0, b: 0 },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  scene: {
                    xaxis: { visible: false },
                    yaxis: { visible: false },
                    zaxis: { visible: false },
                    camera: { eye: { x: 1.5, y: 1.5, z: 0.5 } }
                  }
                }}
                useResizeHandler={true}
                style={{ width: "100%", height: "100%" }}
                config={{ displayModeBar: false }}
              />
            )}
          </div>
        </div>
      </section>

      {/* Feature 3: Non-Linear Dynamics */}
      <section className="py-24 px-6 border-t border-white/10 bg-[#0a0a0a]">
        <div className="max-w-[1024px] mx-auto flex flex-col md:flex-row items-center gap-16">
          <div className="flex-1 space-y-6">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Non-Linear Dynamics. <br/><span className="text-gray-500">True-to-life precision.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Standard solvers use linear approximations. We don&apos;t. Import direct dynamometer shock curves and aero downforce maps. Our engine computes non-linear hysteresis and progressive spring rates in real-time, just like the real world.
            </p>
            <ul className="space-y-3 pt-4">
              {["CSV Dynamo imports", "Real-time hysteresis mapping", "Progressive aero models"].map((f, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300"><CheckCircle2 size={18} className="text-[#ff3b30]"/> {f}</li>
              ))}
            </ul>
          </div>
          <div className="flex-1 w-full aspect-square md:aspect-auto md:h-[400px] bg-black border border-white/10 rounded-2xl overflow-hidden shadow-2xl p-6 relative flex items-center justify-center">
            {mounted && (
               <Plot
               data={[
                 {
                   x: [-50, -30, -10, 0, 10, 30, 50],
                   y: [-2500, -1200, -300, 0, 500, 1800, 3000],
                   type: 'scatter',
                   mode: 'lines+markers',
                   line: { color: '#ff3b30', shape: 'spline', width: 3 },
                   marker: { size: 8 }
                 }
               ]}
               layout={{
                 autosize: true,
                 margin: { l: 40, r: 20, t: 20, b: 40 },
                 paper_bgcolor: 'transparent',
                 plot_bgcolor: 'transparent',
                 xaxis: { title: { text: 'Velocity (mm/s)' }, color: '#666', gridcolor: '#222' },
                 yaxis: { title: { text: 'Force (N)' }, color: '#666', gridcolor: '#222' }
               }}
               useResizeHandler={true}
               style={{ width: "100%", height: "100%" }}
               config={{ displayModeBar: false }}
             />
            )}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-32 px-6 border-t border-white/10 text-center flex flex-col items-center">
        <h2 className="text-4xl md:text-6xl font-bold tracking-tight mb-8">Ready to dominate?</h2>
        <p className="text-xl text-gray-400 max-w-xl font-light mb-10">
          Join the elite teams who have already switched to SuspensionLab Pro. Gain the unfair advantage today.
        </p>
        <Link href="/pricing" className="px-10 py-5 bg-white text-black text-lg font-bold rounded-full hover:bg-gray-200 transition-transform hover:scale-105 active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.2)]">
          Get SuspensionLab MAX
        </Link>
      </section>

    </div>
  );
}
