import sys

content = '''"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { Play, CheckCircle2, Users, Download, ShieldCheck, Zap } from "lucide-react";
import Link from "next/link";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export default function Home() {
  const [mounted, setMounted] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setMounted(true), []);

  return (
    <div className="w-full bg-black text-white selection:bg-ansys-yellow selection:text-black pb-24 overflow-hidden">
      
      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6 max-w-[1200px] mx-auto text-center flex flex-col items-center">
        <div className="absolute top-[-10%] left-1/2 -translate-x-1/2 w-[1000px] h-[500px] bg-[#f2a900]/15 blur-[150px] rounded-full pointer-events-none"></div>
        <div className="absolute top-[20%] right-[-10%] w-[600px] h-[600px] bg-[#00aeff]/10 blur-[150px] rounded-full pointer-events-none"></div>
        
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs font-semibold tracking-wide uppercase text-gray-300 mb-8 backdrop-blur-md">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          SuspensionLab Enterprise is Live
        </div>

        <h1 className="text-6xl md:text-8xl font-black tracking-tighter mb-6 relative z-10 leading-[1.1]">
          Engineering Excellence. <br/>
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-ansys-yellow via-[#ffaa00] to-[#ff2d55]">
            Procurement Ready.
          </span>
        </h1>
        <p className="text-xl md:text-2xl text-gray-400 max-w-3xl font-light mb-12 relative z-10">
          The industry standard in 7-DOF full-car dynamics. From native MSC ADAMS exports to real-time team collaboration, SuspensionLab is the ultimate platform for elite OEMs and motorsport teams.
        </p>
        <div className="flex flex-col sm:flex-row items-center gap-4 relative z-10">
          <Link href="/pricing" className="px-8 py-4 bg-white text-black font-bold rounded-full hover:bg-gray-200 transition-transform hover:scale-105 active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.2)]">
            Upgrade to Enterprise
          </Link>
          <Link href="/quarter-car" className="px-8 py-4 bg-transparent text-white font-semibold rounded-full border border-white/20 hover:bg-white/10 hover:border-white/40 transition-all flex items-center gap-2 backdrop-blur-sm">
            Launch Demo <Play size={16} fill="currentColor" />
          </Link>
        </div>
      </section>

      {/* Feature 1: Team Collaboration Hub */}
      <section className="py-24 px-6 border-t border-white/5 bg-[#050505] relative">
        <div className="max-w-[1200px] mx-auto flex flex-col md:flex-row items-center gap-16">
          <div className="flex-1 space-y-6">
            <div className="w-12 h-12 rounded-2xl bg-[#00aeff]/10 flex items-center justify-center border border-[#00aeff]/20 mb-4">
              <Users size={24} className="text-[#00aeff]" />
            </div>
            <h2 className="text-4xl md:text-5xl font-bold tracking-tight">Real-Time Sync. <br/><span className="text-gray-500">The Collaboration Hub.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Engineering isn't a solo sport. Host live simulation sessions with your entire team. Instantly broadcast parameter changes, visualize dynamic responses synchronously, and iterate in real-time across the globe.
            </p>
            <ul className="space-y-3 pt-4">
              {["Low-latency WebSocket synchronization", "Role-based access (Owner, Engineer, Viewer)", "Live cursor tracking & parameter forks"].map((f, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300 font-medium"><CheckCircle2 size={18} className="text-[#00aeff]"/> {f}</li>
              ))}
            </ul>
          </div>
          <div className="flex-1 w-full bg-black border border-white/10 rounded-2xl p-6 shadow-2xl relative">
            <div className="absolute top-4 right-4 flex -space-x-2">
              <div className="w-8 h-8 rounded-full border-2 border-black bg-emerald-500 flex items-center justify-center text-xs font-bold">JD</div>
              <div className="w-8 h-8 rounded-full border-2 border-black bg-blue-500 flex items-center justify-center text-xs font-bold">AM</div>
              <div className="w-8 h-8 rounded-full border-2 border-black bg-amber-500 flex items-center justify-center text-xs font-bold">+3</div>
            </div>
            <div className="mt-8 space-y-4">
              <div className="flex justify-between p-3 bg-[#111] rounded-lg border border-[#222]">
                <span className="text-gray-400 font-mono text-sm">Front Spring Rate</span>
                <span className="text-white font-mono font-bold">28,500 <span className="text-[#00aeff] ml-2 animate-pulse">▲ +500</span></span>
              </div>
              <div className="flex justify-between p-3 bg-[#111] rounded-lg border border-[#222]">
                <span className="text-gray-400 font-mono text-sm">Rear Damping</span>
                <span className="text-white font-mono font-bold">3,200</span>
              </div>
              <div className="w-full h-32 mt-4 bg-gradient-to-r from-[#00aeff]/20 to-transparent rounded-lg border border-[#00aeff]/30 flex items-end">
                <div className="w-full h-1/2 border-t-2 border-[#00aeff] opacity-50 relative">
                  <div className="absolute right-10 -top-2 w-4 h-4 bg-[#00aeff] rounded-full shadow-[0_0_15px_#00aeff]"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature 2: CAE Export Pipeline */}
      <section className="py-24 px-6 border-t border-white/5 bg-black">
        <div className="max-w-[1200px] mx-auto flex flex-col md:flex-row-reverse items-center gap-16">
          <div className="flex-1 space-y-6">
            <div className="w-12 h-12 rounded-2xl bg-[#ff2d55]/10 flex items-center justify-center border border-[#ff2d55]/20 mb-4">
              <Download size={24} className="text-[#ff2d55]" />
            </div>
            <h2 className="text-4xl md:text-5xl font-bold tracking-tight">CAE Pipeline. <br/><span className="text-gray-500">Native integrations.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Bridge the gap between conceptual tuning and multi-body simulation. Export your 7-DOF setups natively as Simulink (.m) State-Space matrices or MSC ADAMS (.adm) solver datasets with a single click.
            </p>
            <ul className="space-y-3 pt-4">
              {["MATLAB/Simulink State-Space (.m)", "MSC ADAMS Solver Datasets (.adm)", "Drop-in compatible with enterprise workflows"].map((f, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300 font-medium"><CheckCircle2 size={18} className="text-[#ff2d55]"/> {f}</li>
              ))}
            </ul>
          </div>
          <div className="flex-1 w-full aspect-square md:aspect-auto md:h-[400px] bg-[#0a0a0c] border border-white/10 rounded-2xl overflow-hidden shadow-2xl relative flex items-center justify-center">
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')]"></div>
            <div className="flex flex-col gap-4 z-10 w-3/4">
              <div className="p-4 bg-[#141416] border border-[#252525] rounded-xl flex items-center gap-4 hover:border-[#ff2d55]/50 transition-colors cursor-pointer group">
                <div className="w-10 h-10 rounded-lg bg-[#ff2d55]/10 flex items-center justify-center text-[#ff2d55] font-bold font-mono">.adm</div>
                <div>
                  <h3 className="font-bold text-white group-hover:text-[#ff2d55] transition-colors">Export to MSC ADAMS</h3>
                  <p className="text-xs text-gray-500">Generates 7-DOF structural bodies & joints</p>
                </div>
              </div>
              <div className="p-4 bg-[#141416] border border-[#252525] rounded-xl flex items-center gap-4 hover:border-ansys-yellow/50 transition-colors cursor-pointer group">
                <div className="w-10 h-10 rounded-lg bg-ansys-yellow/10 flex items-center justify-center text-ansys-yellow font-bold font-mono">.m</div>
                <div>
                  <h3 className="font-bold text-white group-hover:text-ansys-yellow transition-colors">Export to Simulink</h3>
                  <p className="text-xs text-gray-500">14x14 A-Matrix LTI State-Space formulation</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature 3: ISO 2631 Compliance */}
      <section className="py-24 px-6 border-t border-white/5 bg-[#050505]">
        <div className="max-w-[1200px] mx-auto flex flex-col md:flex-row items-center gap-16">
          <div className="flex-1 space-y-6">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 mb-4">
              <ShieldCheck size={24} className="text-emerald-400" />
            </div>
            <h2 className="text-4xl md:text-5xl font-bold tracking-tight">ISO 2631-1. <br/><span className="text-gray-500">Certified reporting.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Stop guessing if your design meets human vibration exposure limits. Our backend automatically applies Wk frequency-weighting filters and generates standalone, procurement-ready HTML compliance reports.
            </p>
            <ul className="space-y-3 pt-4">
              {["Wk Frequency Weighting filter", "RMS Acceleration (Comfort) assessment", "One-click standalone HTML reports"].map((f, i) => (
                <li key={i} className="flex items-center gap-3 text-gray-300 font-medium"><CheckCircle2 size={18} className="text-emerald-400"/> {f}</li>
              ))}
            </ul>
          </div>
          <div className="flex-1 w-full bg-[#111113] border border-white/10 rounded-2xl overflow-hidden shadow-2xl relative p-6">
            <div className="w-full bg-white rounded-lg p-6 shadow-inner transform rotate-1 scale-105 origin-center text-black font-sans">
              <div className="border-b-2 border-black pb-4 mb-4">
                <h1 className="text-2xl font-black">ISO 2631-1 COMPLIANCE REPORT</h1>
                <p className="text-sm font-mono text-gray-600">ID: SL-RPT-7823-A | PROCUREMENT-READY</p>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="bg-gray-100 p-3 rounded">
                  <p className="text-xs font-bold text-gray-500">WEIGHTED RMS</p>
                  <p className="text-xl font-black text-emerald-600">0.28 m/s²</p>
                </div>
                <div className="bg-gray-100 p-3 rounded">
                  <p className="text-xs font-bold text-gray-500">RATING</p>
                  <p className="text-xl font-black">Not uncomfortable</p>
                </div>
              </div>
              <div className="w-full h-24 bg-gray-100 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-400 text-sm font-bold">
                [ PSD PLOT PREVIEW ]
              </div>
            </div>
            <div className="absolute inset-0 bg-gradient-to-tr from-[#050505] via-transparent to-transparent"></div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-32 px-6 border-t border-white/5 text-center flex flex-col items-center relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-ansys-yellow/10 blur-[150px] rounded-full pointer-events-none"></div>
        <Zap size={48} className="text-ansys-yellow mb-8 relative z-10" />
        <h2 className="text-5xl md:text-7xl font-black tracking-tight mb-8 relative z-10">Close the deal.</h2>
        <p className="text-xl text-gray-400 max-w-2xl font-light mb-10 relative z-10">
          SuspensionLab is technically validated, procurement-ready, and equipped with the highest-leverage enterprise features for Tier-1 OEMs.
        </p>
        <Link href="/pricing" className="px-10 py-5 bg-ansys-yellow text-black text-lg font-bold rounded-full hover:bg-white transition-all hover:scale-105 active:scale-95 shadow-[0_0_50px_rgba(242,169,0,0.4)] relative z-10">
          Acquire SuspensionLab Now
        </Link>
      </section>

    </div>
  );
}
'''

with open('frontend2/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
