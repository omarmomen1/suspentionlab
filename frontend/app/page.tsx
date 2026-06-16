"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { Play, CheckCircle2, Zap, LayoutDashboard, Server, ChevronRight, XCircle } from "lucide-react";
import Link from "next/link";
import { motion } from "framer-motion";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const NVH_DEMO_DATA = (() => {
    const rows = [];
    for (let i = 0; i < 20; i++) {
        const row = [];
        for (let j = 0; j < 20; j++) {
            const f = i * 2.5 + 0.5;   
            const v = j * 5 + 10;      
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
    <div className="w-full bg-[#0a0a0a] text-white selection:bg-ansys-yellow selection:text-black min-h-screen overflow-hidden font-sans">
      
      {/* Dynamic Hero Section */}
      <section className="relative pt-32 pb-20 px-6 max-w-[1200px] mx-auto text-center flex flex-col items-center">
        {/* Glow effect */}
        <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-ansys-yellow/15 blur-[120px] rounded-full pointer-events-none"></div>
        
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="relative z-10"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm mb-8 text-gray-300">
            <span className="w-2 h-2 rounded-full bg-ansys-yellow animate-pulse"></span>
            The Modern Standard for Vehicle Dynamics
          </div>
          
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6">
            Stop Guessing. <br className="hidden md:block"/>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-ansys-yellow to-[#ff9900]">Start Winning.</span>
          </h1>
          
          <p className="text-lg md:text-xl text-gray-400 max-w-2xl mx-auto font-light mb-10 leading-relaxed">
            The ultimate cloud-native vehicle dynamics simulation suite. Sub-millisecond precision, 7-post rig capabilities, and AI-driven tuning built for Tier-1 OEMs and elite racing teams.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/pricing" className="group px-8 py-4 bg-white text-black font-semibold rounded-full hover:bg-gray-200 transition-all hover:scale-105 active:scale-95 flex items-center gap-2 shadow-[0_0_30px_rgba(255,255,255,0.1)]">
              Get Pro Access — $50 <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link href="/quarter-car" className="px-8 py-4 bg-transparent text-white font-semibold rounded-full border border-white/20 hover:bg-white/10 transition-colors flex items-center gap-2 backdrop-blur-sm">
              Try Interactive Demo <Play size={16} fill="currentColor" />
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Feature Showcase: Glassmorphism Cards */}
      <section className="py-24 px-6 max-w-[1200px] mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">Unfair Advantage, Built In.</h2>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">Leave legacy software behind with tools designed for modern engineering workflows.</p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {[
            { icon: Zap, title: "Lightning Fast", desc: "Solve 10,000 parameter sweeps in the cloud before your competitor's desktop software even boots up." },
            { icon: LayoutDashboard, title: "Intuitive UI", desc: "No massive 1990s manuals required. Clean, modern interface designed by engineers, for engineers." },
            { icon: Server, title: "Cloud Native", desc: "Access your setups, telemetry, and 7-post rig simulations from any browser, anywhere in the world." }
          ].map((feat, i) => (
            <motion.div 
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              className="bg-[#111111] border border-[#222] rounded-2xl p-8 hover:border-ansys-yellow/30 transition-colors group relative overflow-hidden"
            >
              <div className="w-12 h-12 bg-ansys-yellow/10 rounded-xl flex items-center justify-center mb-6 text-ansys-yellow group-hover:scale-110 transition-transform">
                <feat.icon size={24} />
              </div>
              <h3 className="text-xl font-bold mb-3">{feat.title}</h3>
              <p className="text-gray-400 leading-relaxed">{feat.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* The Implicit Comparison Section */}
      <section className="py-24 px-6 bg-[#050505] border-t border-white/5 relative">
        <div className="absolute top-0 right-1/4 w-[500px] h-[500px] bg-ansys-yellow/5 blur-[150px] rounded-full pointer-events-none"></div>
        <div className="max-w-[1000px] mx-auto">
          <div className="text-center mb-16 relative z-10">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">Stop Paying For The 90s.</h2>
            <p className="text-gray-400 text-lg max-w-2xl mx-auto">How we stack up against the "industry standard" legacy software.</p>
          </div>

          <div className="bg-[#111] border border-[#222] rounded-3xl overflow-hidden relative z-10 shadow-2xl">
            <div className="grid grid-cols-3 border-b border-[#222] bg-[#1a1a1a] p-6">
              <div className="font-bold text-gray-400 uppercase tracking-wider text-sm">Feature</div>
              <div className="font-bold text-gray-500 uppercase tracking-wider text-sm text-center">Legacy Software</div>
              <div className="font-bold text-ansys-yellow uppercase tracking-wider text-sm text-center">SuspensionLab</div>
            </div>
            
            {[
              { label: "Learning Curve", legacy: "4-Week Training Course", us: "15 Minutes" },
              { label: "Pricing Model", legacy: "$50,000/seat Perpetual", us: "$50/mo Subscription" },
              { label: "Compute Engine", legacy: "Local Desktop CPU", us: "Infinite Cloud Servers" },
              { label: "User Interface", legacy: "Clunky 1990s Menus", us: "Modern, Web-Native" },
              { label: "Setup Sharing", legacy: "Emailing ZIP files", us: "1-Click Secure Links" },
            ].map((row, i) => (
              <div key={i} className={`grid grid-cols-3 p-6 ${i !== 4 ? 'border-b border-[#222]' : ''} hover:bg-white/[0.02] transition-colors`}>
                <div className="font-medium text-white flex items-center">{row.label}</div>
                <div className="text-gray-500 flex items-center justify-center text-center text-sm md:text-base">
                  <XCircle size={16} className="mr-2 text-red-500/50 hidden md:block" /> {row.legacy}
                </div>
                <div className="text-white font-semibold flex items-center justify-center text-center text-sm md:text-base">
                  <CheckCircle2 size={16} className="mr-2 text-ansys-yellow hidden md:block" /> {row.us}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Interactive NVH Demo Section */}
      <section className="py-24 px-6 border-t border-white/5 bg-black">
        <div className="max-w-[1200px] mx-auto flex flex-col md:flex-row items-center gap-16">
          <div className="flex-1 space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-bold uppercase tracking-wider">
              NVH Analyzer
            </div>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Acoustics & NVH. <br/><span className="text-gray-500">Isolate resonance instantly.</span></h2>
            <p className="text-lg text-gray-400 font-light leading-relaxed">
              Don&apos;t rely on blind luck to solve cabin drone. Perform highly optimized Fast Fourier Transforms (FFT) on chassis acceleration data to identify modal frequencies and optimize ride comfort before building a single physical prototype.
            </p>
          </div>
          <div className="flex-1 w-full aspect-square md:aspect-auto md:h-[450px] bg-[#0d0d0d] border border-[#222] rounded-3xl overflow-hidden shadow-2xl relative p-2">
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
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-32 px-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-ansys-yellow/10"></div>
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-20 mix-blend-overlay"></div>
        
        <div className="max-w-4xl mx-auto text-center relative z-10 bg-black/40 backdrop-blur-md border border-white/10 p-12 md:p-20 rounded-3xl shadow-2xl">
          <h2 className="text-4xl md:text-6xl font-black mb-6">Ready to dominate the track?</h2>
          <p className="text-xl text-gray-300 mb-10 max-w-2xl mx-auto font-light">Join the engineers who have already made the switch. Set up your first full vehicle model in less than 15 minutes.</p>
          
          <Link href="/pricing" className="inline-flex px-10 py-5 bg-ansys-yellow text-black text-lg font-bold rounded-full hover:brightness-110 transition-transform hover:scale-105 active:scale-95 shadow-[0_0_40px_rgba(242,169,0,0.4)]">
            Start Your Journey Now
          </Link>
        </div>
      </section>

    </div>
  );
}
