"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../contexts/AuthContext";
import { Eye, EyeOff, Loader2 } from "lucide-react";

const STRENGTH_LABELS = ["", "Weak", "Fair", "Good", "Strong"];
const STRENGTH_COLORS = ["", "bg-red-500", "bg-orange-400", "bg-yellow-400", "bg-emerald-500"];

function passwordChecks(p: string) {
  return {
    length: p.length >= 12,
    upper: /[A-Z]/.test(p),
    lower: /[a-z]/.test(p),
    digit: /[0-9]/.test(p),
    special: /[!@#$%^&*(),.?":{}|<>]/.test(p),
  };
}

function passwordStrength(p: string): number {
  const checks = passwordChecks(p);
  let s = 0;
  if (checks.length) s++;
  if (checks.upper && checks.lower) s++;
  if (checks.digit) s++;
  if (checks.special) s++;
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

  const checks = passwordChecks(password);
  const isPasswordValid = Object.values(checks).every(Boolean);
  const strength = passwordStrength(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError("Please enter your name."); return; }
    if (!checks.length) { setError("Password must be at least 12 characters long."); return; }
    if (!isPasswordValid) { setError("Password must include uppercase, lowercase, numbers, and special characters."); return; }
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
      <h1 className="text-xl font-bold text-white mb-6 text-center">Create your account</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="register-name" className="block text-xs font-medium text-gray-300 mb-1.5">Full Name</label>
          <input
            id="register-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="James Hunt"
            className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
              placeholder:text-gray-500 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
              focus:ring-ansys-yellow/15 transition-all"
          />
        </div>

        <div>
          <label htmlFor="register-email" className="block text-xs font-medium text-gray-300 mb-1.5">Work Email</label>
          <input
            id="register-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
              placeholder:text-gray-500 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
              focus:ring-ansys-yellow/15 transition-all"
          />
        </div>

        <div>
          <label htmlFor="register-password" className="block text-xs font-medium text-gray-300 mb-1.5">
            Password (Min 12 characters)
          </label>
          <div className="relative">
            <input
              id="register-password"
              type={showPwd ? "text" : "password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 12 characters"
              aria-describedby="pwd-criteria"
              className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
                placeholder:text-gray-400 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
                focus:ring-ansys-yellow/15 transition-all pr-12"
            />
            <button
              type="button"
              onClick={() => setShowPwd((v) => !v)}
              aria-label={showPwd ? "Hide password" : "Show password"}
              aria-pressed={showPwd}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white p-2 min-w-[28px] min-h-[28px] flex items-center justify-center rounded-lg"
            >
              {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {password.length > 0 && (
            <div id="pwd-criteria" className="mt-2 space-y-1.5">
              <div className="flex gap-1" role="progressbar" aria-valuenow={strength} aria-valuemin={0} aria-valuemax={4} aria-label={`Password strength: ${STRENGTH_LABELS[strength] || 'None'}`}>
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${
                    strength >= i ? STRENGTH_COLORS[strength] : "bg-[#252525]"
                  }`} />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-1 text-[10px]" role="status">
                <span className={checks.length ? "text-emerald-400" : "text-gray-400"}>
                  {checks.length ? "✓" : "○"} 12+ characters
                </span>
                <span className={checks.upper ? "text-emerald-400" : "text-gray-400"}>
                  {checks.upper ? "✓" : "○"} Uppercase (A-Z)
                </span>
                <span className={checks.lower ? "text-emerald-400" : "text-gray-400"}>
                  {checks.lower ? "✓" : "○"} Lowercase (a-z)
                </span>
                <span className={checks.digit && checks.special ? "text-emerald-400" : "text-gray-400"}>
                  {checks.digit && checks.special ? "✓" : "○"} Number & Symbol
                </span>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div
            role="alert"
            aria-live="assertive"
            className="text-xs text-red-400 bg-red-950/30 border border-red-900/30 rounded-lg px-3 py-2"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-ansys-yellow text-black text-sm font-bold rounded-xl
            hover:brightness-110 transition-all shadow-[0_0_16px_rgba(242,169,0,0.2)]
            disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? <><Loader2 size={14} className="animate-spin" /> Creating account…</> : "Create Account"}
        </button>

        <p className="text-[10px] text-gray-400 text-center">
          By registering you agree to our{" "}
          <Link href="/legal/terms" className="text-gray-300 hover:text-white underline">Terms of Service</Link>
          {" "}and{" "}
          <Link href="/legal/privacy" className="text-gray-300 hover:text-white underline">Privacy Policy</Link>.
        </p>
      </form>

      <p className="text-center text-xs text-gray-400 mt-5">
        Already have an account?{" "}
        <Link href="/auth/login" className="text-ansys-yellow hover:underline font-semibold inline-flex items-center min-h-[24px]">Sign In</Link>
      </p>
    </div>
  );
}
