import type { Metadata } from "next";
import Link from "next/link";
import { BookOpen, Zap, BarChart3, Activity, Settings2, ExternalLink, ChevronRight } from "lucide-react";

export const metadata: Metadata = {
  title: "Documentation — SuspensionLab Pro",
  description: "Complete reference for SuspensionLab simulation parameters, physics models, and API access.",
};

const PARAMS = [
  { param: "m_s",  name: "Sprung Mass",        unit: "kg",    range: "50–2000",    typical: "280–550",   desc: "The mass supported by the suspension springs — chassis + body + drivetrain. Does NOT include wheel assemblies." },
  { param: "m_u",  name: "Unsprung Mass",       unit: "kg",    range: "10–100",     typical: "25–55",     desc: "Mass not isolated by springs: wheels, brakes, hubs, and part of the control arm. Lower = better road holding." },
  { param: "k_s",  name: "Spring Rate",         unit: "N/m",   range: "5k–200k",   typical: "15k–60k",   desc: "Stiffness of the suspension spring at the wheel. Higher = firmer ride, better roll control, worse comfort." },
  { param: "c",    name: "Damping Coefficient", unit: "N·s/m", range: "500–20k",   typical: "1.5k–5k",   desc: "Viscous damping at the shock absorber. Optimum is typically 0.25–0.5× critical damping for ride comfort." },
  { param: "k_t",  name: "Tire Stiffness",      unit: "N/m",   range: "100k–400k", typical: "180k–280k", desc: "Radial stiffness of the pneumatic tire. Acts as a secondary spring between the wheel and the road." },
  { param: "MR",   name: "Motion Ratio",        unit: "—",     range: "0.5–1.2",   typical: "0.75–0.95", desc: "Ratio of spring displacement to wheel displacement. Rocker and pushrod suspensions can be < 1. Direct-acting = 1." },
  { param: "c_t",  name: "Tire Damping",        unit: "N·s/m", range: "0–500",     typical: "0",         desc: "Viscous damping in the tire sidewall. Usually negligible for passenger cars. Rarely needs adjustment." },
];

const KPIs = [
  { name: "Sprung Frequency (fₙ_s)",    good: "0.9–1.4 Hz",  desc: "Natural frequency of the body. <1 Hz feels wallowy; >2 Hz feels harsh. Sports cars target 1.5–2 Hz. Comfort cars 0.9–1.1 Hz." },
  { name: "Unsprung Frequency (fₙ_u)",  good: "8–15 Hz",     desc: "Natural frequency of the wheel assembly. Should be well above fₙ_s (ideally 3–5× higher) to avoid modal coupling." },
  { name: "Damping Ratio (ζ)",          good: "0.25–0.5",    desc: "Ratio of actual damping to critical damping. ζ = 1 is critically damped. Typical suspension: 0.25 (comfort) to 0.5 (sporty)." },
  { name: "Peak Transmissibility",      good: "<2.5×",        desc: "Maximum amplification of road input to body at the resonant frequency. Lower is better. >3× indicates underdamping." },
  { name: "ISO 2631-1 Wk RMS (m/s²)",  good: "<0.315",       desc: "Frequency-weighted body acceleration. ISO 2631-1 thresholds: <0.315 = not uncomfortable, 0.315–0.63 = slightly, >1.0 = very uncomfortable." },
  { name: "Peak Suspension Travel (m)", good: "<0.08 m",      desc: "Maximum compression or extension of the suspension. Exceeding physical bump stop travel causes damage." },
];

const SECTIONS = [
  { id: "quickstart",  label: "Quick Start"         },
  { id: "params",      label: "Parameters"          },
  { id: "kpis",        label: "KPIs Explained"      },
  { id: "models",      label: "Physics Models"      },
  { id: "api",         label: "REST API"            },
  { id: "faq",         label: "FAQ"                 },
];

export default function DocsPage() {
  return (
    <div className="min-h-full bg-black pt-[44px]">
      <div className="max-w-6xl mx-auto px-6 py-12 flex gap-12">
        {/* Sidebar */}
        <div className="w-48 shrink-0 sticky top-16 self-start">
          <p className="text-[9px] font-bold text-gray-700 uppercase tracking-widest mb-3">Contents</p>
          <nav className="space-y-1">
            {SECTIONS.map((s) => (
              <a key={s.id} href={`#${s.id}`}
                className="block text-xs text-gray-500 hover:text-white transition-colors py-1">
                {s.label}
              </a>
            ))}
          </nav>
          <div className="mt-8 p-3 bg-[#111113] border border-[#1e1e1e] rounded-xl">
            <p className="text-[10px] text-gray-600 mb-2">Need more help?</p>
            <a href="mailto:support@suspensionlab.io"
              className="text-[10px] text-ansys-yellow hover:underline flex items-center gap-1">
              Email support <ExternalLink size={9} />
            </a>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0 space-y-16">
          {/* Header */}
          <div>
            <span className="text-[10px] font-bold tracking-[0.2em] text-ansys-yellow uppercase">Reference</span>
            <h1 className="text-4xl font-semibold text-white mt-2 mb-4">Documentation</h1>
            <p className="text-gray-500 leading-relaxed">
              Complete reference for simulation parameters, physics models, KPI interpretation,
              and REST API access.
            </p>
          </div>

          {/* Quick Start */}
          <section id="quickstart">
            <h2 className="text-2xl font-semibold text-white mb-6 flex items-center gap-2">
              <Zap size={20} className="text-ansys-yellow" /> Quick Start
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { step: "1", title: "Choose a vehicle",      desc: "Load a preset from the Vehicle Library, or manually enter mass and stiffness values in the parameter panel." },
                { step: "2", title: "Select a road profile", desc: "Choose from Step, Sine, Pothole, Random (ISO 8608), or Impulse. Or upload your own CSV measured data." },
                { step: "3", title: "Run & analyse",         desc: "Click Run Solver. The RK45 ODE engine returns results in <1 second. Check the KPI ribbon and plots." },
              ].map((s) => (
                <div key={s.step} className="bg-[#111113] border border-[#1e1e1e] rounded-xl p-5">
                  <div className="w-7 h-7 rounded-full bg-ansys-yellow/10 text-ansys-yellow text-xs font-bold
                    flex items-center justify-center mb-3">
                    {s.step}
                  </div>
                  <h3 className="text-sm font-bold text-white mb-1">{s.title}</h3>
                  <p className="text-xs text-gray-500 leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Parameters */}
          <section id="params">
            <h2 className="text-2xl font-semibold text-white mb-6 flex items-center gap-2">
              <Settings2 size={20} className="text-ansys-yellow" /> Input Parameters
            </h2>
            <div className="overflow-hidden rounded-xl border border-[#1e1e1e]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#111113] border-b border-[#1e1e1e]">
                    <th className="px-5 py-3 text-left text-[10px] font-bold text-gray-600 uppercase tracking-wider">Symbol</th>
                    <th className="px-5 py-3 text-left text-[10px] font-bold text-gray-600 uppercase tracking-wider">Name</th>
                    <th className="px-5 py-3 text-left text-[10px] font-bold text-gray-600 uppercase tracking-wider">Unit</th>
                    <th className="px-5 py-3 text-left text-[10px] font-bold text-gray-600 uppercase tracking-wider">Typical Range</th>
                    <th className="px-5 py-3 text-left text-[10px] font-bold text-gray-600 uppercase tracking-wider">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {PARAMS.map((p, i) => (
                    <tr key={p.param} className={`border-b border-[#111113] ${i % 2 === 0 ? "bg-[#0a0a0c]" : "bg-[#0d0d0f]"}`}>
                      <td className="px-5 py-3 font-mono text-ansys-yellow text-xs font-bold">{p.param}</td>
                      <td className="px-5 py-3 text-white text-xs font-medium">{p.name}</td>
                      <td className="px-5 py-3 text-gray-500 text-xs font-mono">{p.unit}</td>
                      <td className="px-5 py-3 text-gray-400 text-xs">{p.typical}</td>
                      <td className="px-5 py-3 text-gray-600 text-xs leading-relaxed">{p.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* KPIs */}
          <section id="kpis">
            <h2 className="text-2xl font-semibold text-white mb-6 flex items-center gap-2">
              <BarChart3 size={20} className="text-ansys-yellow" /> KPI Interpretation
            </h2>
            <div className="space-y-4">
              {KPIs.map((kpi) => (
                <div key={kpi.name} className="bg-[#111113] border border-[#1e1e1e] rounded-xl p-5 flex gap-5">
                  <div className="shrink-0 w-28">
                    <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-1">Target</p>
                    <p className="text-xs font-bold text-emerald-400 font-mono">{kpi.good}</p>
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white mb-1">{kpi.name}</h3>
                    <p className="text-xs text-gray-500 leading-relaxed">{kpi.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Models */}
          <section id="models">
            <h2 className="text-2xl font-semibold text-white mb-6 flex items-center gap-2">
              <Activity size={20} className="text-ansys-yellow" /> Physics Models
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {[
                { name: "Quarter Car (2-DOF)", plan: "FREE", href: "/quarter-car",
                  desc: "Single wheel station. Sprung + unsprung mass coupled by spring-damper. Solves heave only. Best for ride comfort optimisation and ISO 2631-1 compliance studies.",
                  eqs: ["m_s·z̈_s + c(ż_s-ż_u) + k_s(z_s-z_u) = 0", "m_u·z̈_u - c(ż_s-ż_u) - k_s(z_s-z_u) + k_t(z_u-z_r) = 0"] },
                { name: "Half Car (4-DOF)", plan: "PRO", href: "/half-car",
                  desc: "Front + rear axles. Adds pitch coupling. Reveals front-to-rear phase lag at highway speeds, critical for vehicle-level comfort and dynamic weight transfer.",
                  eqs: ["m_s·z̈_s = ...", "I_y·θ̈ = ..."] },
                { name: "Full Car (7-DOF)", plan: "PRO", href: "/full-car",
                  desc: "All 4 corners. Body heave + pitch + roll + 4 unsprung masses. Required for roll dynamics, anti-roll bar sizing, and lateral load transfer analysis.",
                  eqs: [] },
                { name: "Active Suspension", plan: "PRO", href: "/active",
                  desc: "Skyhook control law applied to a quarter car. Compares controlled damping against passive baseline. Quantifies the theoretical maximum comfort improvement.",
                  eqs: [] },
              ].map((m) => (
                <Link key={m.name} href={m.href}
                  className="bg-[#111113] border border-[#1e1e1e] rounded-xl p-5 hover:border-[#333] transition-colors group">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-bold text-white">{m.name}</h3>
                    <div className="flex items-center gap-2">
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                        m.plan === "FREE" ? "text-gray-500 bg-[#1e1e1e]" : "text-ansys-yellow bg-ansys-yellow/10"
                      }`}>{m.plan}</span>
                      <ChevronRight size={13} className="text-gray-700 group-hover:text-white transition-colors" />
                    </div>
                  </div>
                  <p className="text-xs text-gray-500 leading-relaxed mb-3">{m.desc}</p>
                  {m.eqs.length > 0 && (
                    <div className="bg-black/50 rounded-lg px-3 py-2 border border-[#1a1a1a]">
                      {m.eqs.map((eq) => (
                        <p key={eq} className="text-[10px] font-mono text-gray-600">{eq}</p>
                      ))}
                    </div>
                  )}
                </Link>
              ))}
            </div>
          </section>

          {/* API */}
          <section id="api">
            <h2 className="text-2xl font-semibold text-white mb-2 flex items-center gap-2">
              <BookOpen size={20} className="text-ansys-yellow" /> REST API
            </h2>
            <p className="text-sm text-gray-500 mb-6">
              The SuspensionLab API is available to Pro and Enterprise subscribers.
              Interactive docs are at{" "}
              <a href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/docs`}
                target="_blank" className="text-ansys-yellow hover:underline inline-flex items-center gap-1">
                /docs <ExternalLink size={11} />
              </a>
            </p>

            <div className="space-y-4">
              {[
                { method: "POST", path: "/simulate",           desc: "Run a 2-DOF quarter car simulation. Returns time series, frequency domain, and KPIs." },
                { method: "POST", path: "/simulate/half-car",  desc: "4-DOF half car simulation with pitch coupling." },
                { method: "POST", path: "/simulate/full-car",  desc: "7-DOF full car with roll, pitch, and lateral load transfer." },
                { method: "POST", path: "/auto-tune",          desc: "AI-driven L-BFGS-B optimiser. Returns optimal k_s and c for minimum weighted RMS acceleration." },
                { method: "POST", path: "/auth/login",         desc: "Authenticate with email + password. Returns a JWT Bearer token." },
                { method: "GET",  path: "/profiles",           desc: "List all vehicle profiles belonging to the authenticated user." },
                { method: "POST", path: "/billing/checkout",   desc: "Create a Stripe Checkout Session. Returns a URL to redirect the user to." },
              ].map((ep) => (
                <div key={ep.path} className="flex gap-4 items-start bg-[#111113] border border-[#1e1e1e] rounded-xl px-5 py-3">
                  <span className={`text-[10px] font-black tracking-wider px-2 py-1 rounded font-mono shrink-0 mt-0.5 ${
                    ep.method === "GET" ? "bg-blue-950 text-blue-400" : "bg-green-950 text-green-400"
                  }`}>
                    {ep.method}
                  </span>
                  <div>
                    <code className="text-xs text-gray-300 font-mono">{ep.path}</code>
                    <p className="text-xs text-gray-600 mt-0.5">{ep.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* FAQ */}
          <section id="faq">
            <h2 className="text-2xl font-semibold text-white mb-6">FAQ</h2>
            <div className="space-y-5">
              {[
                { q: "What ODE solver does the physics engine use?",
                  a: "RK45 (Runge-Kutta 4th/5th order with adaptive step size) via scipy.integrate.solve_ivp. This provides excellent accuracy for stiff suspension systems with minimal numerical drift." },
                { q: "How is ISO 2631-1 Wk weighting applied?",
                  a: "A 3rd-order IIR filter approximating the Wk frequency weighting curve is applied to the sprung mass acceleration time series. Requires a simulation sample rate > 160 Hz." },
                { q: "My simulation shows ringing/oscillations — what does this mean?",
                  a: "High-frequency ringing usually indicates underdamping (ζ < 0.1). Increase the damping coefficient c, or check that your spring rate isn't unrealistically high relative to your mass." },
                { q: "Can I import real shock absorber dyno data?",
                  a: "CSV road profile import is available. Non-linear damper force-velocity curves are on the roadmap for the next Pro release." },
                { q: "What does the Motion Ratio (MR) do?",
                  a: "MR accounts for suspension geometry between the wheel and the spring/damper. An MR of 0.8 means the spring compresses 0.8 mm for every 1 mm of wheel travel. The effective spring rate at the wheel is k_s × MR²." },
              ].map((faq) => (
                <div key={faq.q} className="border-b border-[#1e1e1e] pb-5">
                  <h3 className="text-sm font-semibold text-white mb-2">{faq.q}</h3>
                  <p className="text-sm text-gray-500 leading-relaxed">{faq.a}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
