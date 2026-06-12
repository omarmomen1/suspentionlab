"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../contexts/AuthContext";
import { Car, BarChart3, Zap, CheckCircle2, ArrowRight } from "lucide-react";

const STEPS = [
  {
    title:   "Welcome to SuspensionLab",
    icon:    Car,
    content: (
      <div className="space-y-4 text-center">
        <p className="text-gray-400 text-sm leading-relaxed">
          You have <span className="text-ansys-yellow font-bold">14 days of Pro access</span> — free, no card needed.
          Let&apos;s get you to your first simulation result in under 60 seconds.
        </p>
        <div className="grid grid-cols-3 gap-3">
          {[
            ["Quarter Car", "2-DOF vertical dynamics"],
            ["Half Car",    "4-DOF pitch coupling"],
            ["Full Car",    "7-DOF roll dynamics"],
          ].map(([name, desc]) => (
            <div key={name} className="bg-[#0d0d0f] border border-[#252525] rounded-xl p-3 text-left">
              <p className="text-xs font-bold text-white mb-0.5">{name}</p>
              <p className="text-[10px] text-gray-600">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    title:   "How the simulator works",
    icon:    BarChart3,
    content: (
      <div className="space-y-3 text-sm text-gray-400">
        <div className="flex items-start gap-3">
          <span className="w-6 h-6 rounded-full bg-ansys-yellow/10 text-ansys-yellow text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
          <div>
            <p className="text-white font-medium text-sm">Set parameters</p>
            <p className="text-xs text-gray-600">Enter mass, spring rate, damping, and tire stiffness in the left panel. Or choose a vehicle from the preset library.</p>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <span className="w-6 h-6 rounded-full bg-ansys-yellow/10 text-ansys-yellow text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
          <div>
            <p className="text-white font-medium text-sm">Click Run Solver</p>
            <p className="text-xs text-gray-600">The RK45 ODE solver integrates the equations of motion. Results appear in under 1 second.</p>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <span className="w-6 h-6 rounded-full bg-ansys-yellow/10 text-ansys-yellow text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
          <div>
            <p className="text-white font-medium text-sm">Analyse & iterate</p>
            <p className="text-xs text-gray-600">Review the KPI ribbon, transmissibility plot, and ISO 2631-1 comfort score. Use AI Auto-Tune to find the optimal setup.</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    title:   "You&apos;re all set",
    icon:    Zap,
    content: (
      <div className="text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-ansys-yellow/10 border border-ansys-yellow/20
          flex items-center justify-center mx-auto">
          <CheckCircle2 size={32} className="text-ansys-yellow" />
        </div>
        <p className="text-gray-400 text-sm leading-relaxed">
          Your 14-day Pro trial is active. Run your first simulation, save it to the Garage,
          and explore every model — no restrictions.
        </p>
        <p className="text-[11px] text-gray-600">
          Need help? Check the{" "}
          <a href="/docs" className="text-ansys-yellow hover:underline">documentation</a>
          {" "}or use the in-app tooltips.
        </p>
      </div>
    ),
  },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function OnboardingPage() {
  const { token, authHeader } = useAuth();
  const router  = useRouter();
  const [step,  setStep]  = useState(0);
  const [loading, setLoading] = useState(false);
  const current = STEPS[step];
  const Icon    = current.icon;

  const finish = async () => {
    setLoading(true);
    try {
      await fetch(`${API_BASE}/auth/onboard`, {
        method: "POST", headers: authHeader(),
      });
    } catch { /* non-fatal */ }
    router.push("/quarter-car");
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* Progress dots */}
        <div className="flex justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div key={i} className={`h-1.5 rounded-full transition-all duration-300 ${
              i === step ? "w-8 bg-ansys-yellow" : i < step ? "w-4 bg-ansys-yellow/40" : "w-4 bg-[#252525]"
            }`} />
          ))}
        </div>

        <div className="bg-[#111113] border border-[#252525] rounded-2xl p-8 shadow-2xl">
          <div className="flex flex-col items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-2xl bg-ansys-yellow/10 border border-ansys-yellow/20
              flex items-center justify-center">
              <Icon size={22} className="text-ansys-yellow" />
            </div>
            <h1 className="text-xl font-bold text-white text-center">{current.title}</h1>
          </div>

          <div className="mb-8">{current.content}</div>

          <div className="flex gap-3">
            {step > 0 && (
              <button onClick={() => setStep((s) => s - 1)}
                className="flex-1 py-2.5 bg-[#1e1e20] border border-[#2a2a2c] text-sm text-gray-300
                  rounded-xl hover:bg-[#252527] transition-colors">
                Back
              </button>
            )}
            {step < STEPS.length - 1 ? (
              <button onClick={() => setStep((s) => s + 1)}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-ansys-yellow
                  text-black text-sm font-bold rounded-xl hover:brightness-110 transition-all">
                Next <ArrowRight size={14} />
              </button>
            ) : (
              <button onClick={finish} disabled={loading}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-ansys-yellow
                  text-black text-sm font-bold rounded-xl hover:brightness-110 transition-all
                  disabled:opacity-60">
                {loading ? "Starting…" : <><Zap size={14} fill="currentColor" /> Launch Simulator</>}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
