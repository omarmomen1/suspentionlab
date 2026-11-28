"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../contexts/AuthContext";
import { Car, BarChart3, Zap, CheckCircle2, ArrowRight } from "lucide-react";

function buildSteps(plan: string | undefined) {
  const normalizedPlan = (plan || "FREE").toUpperCase();
  const isPaidPlan = ["PRO", "TEAM", "ENTERPRISE"].includes(normalizedPlan);

  return [
    {
      title:   "Welcome to SuspensionLab",
      icon:    Car,
      content: (
        <div className="space-y-4 text-center">
          <p className="text-zinc-300 text-sm leading-relaxed">
            Welcome to <span className="text-signal font-bold">SuspensionLab{isPaidPlan ? ` ${normalizedPlan}` : ""}</span>.
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
                <p className="text-xs text-zinc-400 leading-relaxed">{desc}</p>
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
        <div className="space-y-3 text-sm text-zinc-300">
          <div className="flex items-start gap-3">
            <span className="w-6 h-6 rounded-full bg-signal/15 text-signal text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
            <div>
              <p className="text-white font-medium text-sm">Set parameters</p>
              <p className="text-xs text-zinc-400 leading-relaxed">Enter mass, spring rate, damping, and tire stiffness in the left panel. Or choose a vehicle from the preset library.</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-6 h-6 rounded-full bg-signal/15 text-signal text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
            <div>
              <p className="text-white font-medium text-sm">Click Run Solver</p>
              <p className="text-xs text-zinc-400 leading-relaxed">The implicit BDF/RK45 ODE solver integrates the equations of motion. Results appear in under 1 second.</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="w-6 h-6 rounded-full bg-signal/15 text-signal text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
            <div>
              <p className="text-white font-medium text-sm">Analyse & iterate</p>
              <p className="text-xs text-zinc-400 leading-relaxed">Review the KPI ribbon, transmissibility plot, and ISO 2631-1 comfort score. Use Auto-Tune to find the optimal setup.</p>
            </div>
          </div>
        </div>
      ),
    },
    {
      title:   "You're all set",
      icon:    Zap,
      content: (
        <div className="text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-signal/15 border border-signal/30
            flex items-center justify-center mx-auto">
            <CheckCircle2 size={32} className="text-signal" />
          </div>
          <p className="text-zinc-300 text-sm leading-relaxed">
            {isPaidPlan
              ? `Your ${normalizedPlan} account is active. Run your first simulation, save it to the Garage, and explore every model — no restrictions.`
              : "Your Free workspace is ready. Run Quarter-Car & Half-Car simulations, save configurations to the Garage, or upgrade anytime for Full-Car and ApexSim."}
          </p>

          <p className="text-xs text-zinc-400 leading-relaxed">
            Need help? Check the{" "}
            <a href="/docs" className="text-signal hover:underline">documentation</a>
            {" "}or use the in-app tooltips.
          </p>
        </div>
      ),
    },
  ];
}

export default function OnboardingPage() {
  const { user, fetchWithAuth } = useAuth();
  const router  = useRouter();
  const [step,  setStep]  = useState(0);
  const [loading, setLoading] = useState(false);
  const steps = buildSteps(user?.plan);
  const current = steps[step];
  const Icon    = current.icon;

  const finish = async () => {
    setLoading(true);
    try {
      await fetchWithAuth("/api/v1/auth/onboard", {
        method: "POST",
      });
    } catch { /* non-fatal */ }
    router.push("/quarter-car");
  };

  return (
    <div className="min-h-screen bg-carbon flex items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* Progress dots */}
        <div className="flex justify-center gap-2 mb-8">
          {steps.map((_, i) => (
            <div key={i} className={`h-1.5 rounded-full transition-all duration-300 ${
              i === step ? "w-8 bg-signal" : i < step ? "w-4 bg-signal/40" : "w-4 bg-[#252525]"
            }`} />
          ))}
        </div>

        <div className="bg-panel border border-line-soft rounded-2xl p-8 shadow-2xl">
          <div className="flex flex-col items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-2xl bg-signal/15 border border-signal/30
              flex items-center justify-center">
              <Icon size={22} className="text-signal" />
            </div>
            <h1 className="text-xl font-bold text-white text-center">{current.title}</h1>
          </div>

          <div className="mb-8">{current.content}</div>

          <div className="flex gap-3">
            {step > 0 && (
              <button onClick={() => setStep((s) => s - 1)}
                className="flex-1 py-2.5 bg-[#1e1e20] border border-[#2a2a2c] text-sm text-zinc-200
                  rounded-xl hover:bg-[#252527] transition-colors">
                Back
              </button>
            )}
            {step < steps.length - 1 ? (
              <button onClick={() => setStep((s) => s + 1)}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-signal
                  text-carbon text-sm font-bold rounded-xl hover:brightness-110 transition-all">
                Next <ArrowRight size={14} />
              </button>
            ) : (
              <button onClick={finish} disabled={loading}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-signal
                  text-carbon text-sm font-bold rounded-xl hover:brightness-110 transition-all
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
