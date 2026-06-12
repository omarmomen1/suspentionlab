"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../contexts/AuthContext";
import { Eye, EyeOff, Loader2, CheckCircle2 } from "lucide-react";

const STRENGTH_LABELS = ["", "Weak", "Fair", "Good", "Strong"];
const STRENGTH_COLORS = ["", "bg-red-500", "bg-orange-400", "bg-yellow-400", "bg-emerald-500"];

function passwordStrength(p: string): number {
  let s = 0;
  if (p.length >= 8)  s++;
  if (/[A-Z]/.test(p)) s++;
  if (/[0-9]/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  return s;
}

export default function RegisterPage() {
  const { register } = useAuth();
  const router       = useRouter();
  const [name,     setName]     = useState("");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [showPwd,  setShowPwd]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const strength = passwordStrength(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError("Please enter your name."); return; }
    if (strength < 2) { setError("Please choose a stronger password."); return; }
    setError(null);
    setLoading(true);
    try {
      await register(email, password, name);
      router.push("/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#111113] border border-[#252525] rounded-2xl p-8 shadow-2xl">
      {/* Trial badge */}
      <div className="text-center mb-5">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-ansys-yellow/10 border border-ansys-yellow/20
          text-ansys-yellow text-[10px] font-bold uppercase tracking-wider rounded-full">
          <CheckCircle2 size={11} /> 14-Day Pro Trial — No Credit Card Required
        </span>
      </div>

      <h1 className="text-xl font-bold text-white mb-1 text-center">Create your account</h1>
      <p className="text-sm text-gray-500 mb-6 text-center">Full Pro access, free for 14 days</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Full Name</label>
          <input type="text" required value={name} onChange={(e) => setName(e.target.value)}
            placeholder="James Hunt"
            className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
              placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
              focus:ring-ansys-yellow/15 transition-all" />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Work Email</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
              placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
              focus:ring-ansys-yellow/15 transition-all" />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
          <div className="relative">
            <input type={showPwd ? "text" : "password"} required value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder="Min 8 characters"
              className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
                placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
                focus:ring-ansys-yellow/15 transition-all pr-10" />
            <button type="button" onClick={() => setShowPwd((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-300">
              {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          {password.length > 0 && (
            <div className="mt-2">
              <div className="flex gap-1">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${
                    strength >= i ? STRENGTH_COLORS[strength] : "bg-[#252525]"
                  }`} />
                ))}
              </div>
              <p className="text-[10px] text-gray-600 mt-1">{STRENGTH_LABELS[strength]}</p>
            </div>
          )}
        </div>

        {error && (
          <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/30 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <button type="submit" disabled={loading}
          className="w-full py-2.5 bg-ansys-yellow text-black text-sm font-bold rounded-xl
            hover:brightness-110 transition-all shadow-[0_0_16px_rgba(242,169,0,0.2)]
            disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2">
          {loading ? <><Loader2 size={14} className="animate-spin" /> Creating account…</> : "Start Free Trial"}
        </button>

        <p className="text-[10px] text-gray-700 text-center">
          By registering you agree to our{" "}
          <Link href="/legal/terms" className="text-gray-500 hover:text-gray-300">Terms of Service</Link>
          {" "}and{" "}
          <Link href="/legal/privacy" className="text-gray-500 hover:text-gray-300">Privacy Policy</Link>.
        </p>
      </form>

      <p className="text-center text-xs text-gray-600 mt-5">
        Already have an account?{" "}
        <Link href="/auth/login" className="text-ansys-yellow hover:underline font-semibold">Sign In</Link>
      </p>
    </div>
  );
}
