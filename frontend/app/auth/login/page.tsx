"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../contexts/AuthContext";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export default function LoginPage() {
  const { login, refreshSession } = useAuth();
  const router      = useRouter();
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [showPwd,  setShowPwd]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const userObj = await login(email, password);
      const searchParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
      const redirect = searchParams ? searchParams.get("redirect") : null;
      if (redirect) {
        router.push(redirect);
      } else {
        router.push(userObj?.redirect_url || "/quarter-car");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#111113] border border-[#252525] rounded-2xl p-8 shadow-2xl">
      <h1 className="text-xl font-bold text-white mb-1">Welcome back</h1>
      <p className="text-sm text-zinc-400 mb-6">Sign in to your SuspensionLab account</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="login-email" className="block text-xs font-medium text-gray-300 mb-1.5">Email</label>
          <input
            id="login-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
              placeholder:text-zinc-400 focus:outline-none focus:border-signal/60 focus:ring-1
              focus:ring-signal/15 transition-all"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="login-password" className="text-xs font-medium text-gray-300">Password</label>
            <Link href="/auth/forgot" className="text-xs text-signal hover:underline inline-flex items-center min-h-[24px]">
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <input
              id="login-password"
              type={showPwd ? "text" : "password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
                placeholder:text-gray-400 focus:outline-none focus:border-signal/60 focus:ring-1
                focus:ring-signal/15 transition-all pr-12"
            />
            <button
              type="button"
              onClick={() => setShowPwd((v) => !v)}
              aria-label={showPwd ? "Hide password" : "Show password"}
              aria-pressed={showPwd}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors p-2 min-w-[28px] min-h-[28px] flex items-center justify-center rounded-lg"
            >
              {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
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
          className="w-full py-2.5 bg-signal text-carbon border border-signal text-sm font-bold rounded-xl
            hover:bg-[#d6f56e] transition-colors
            disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? <><Loader2 size={14} className="animate-spin" /> Signing in…</> : "Sign In"}
        </button>
      </form>

      <p className="text-center text-xs text-gray-400 mt-6">
        No account?{" "}
        <Link href="/auth/register" className="text-signal hover:underline font-semibold inline-flex items-center min-h-[24px]">
          Create an account
        </Link>
      </p>

      {/* Dev quick-fill */}
      {process.env.NODE_ENV === "development" && (
        <button type="button" onClick={() => { setEmail("james@company.com"); setPassword("admin123!"); }}
          className="mt-4 w-full py-1.5 text-xs text-zinc-300 hover:text-gray-500 border border-dashed
            border-[#1e1e1e] rounded-lg transition-colors">
          [DEV] Fill demo credentials (james@company.com)
        </button>
      )}

    </div>
  );
}
