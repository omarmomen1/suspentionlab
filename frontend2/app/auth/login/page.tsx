"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../contexts/AuthContext";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export default function LoginPage() {
  const { login }   = useAuth();
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
      await login(email, password);
      const params = new URLSearchParams(window.location.search);
      const redirectUrl = params.get("redirect") || "/garage";
      router.push(redirectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#111113] border border-[#252525] rounded-2xl p-8 shadow-2xl">
      <h1 className="text-xl font-bold text-white mb-1">Welcome back</h1>
      <p className="text-sm text-gray-500 mb-6">Sign in to your SuspensionLab account</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Email</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
              placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
              focus:ring-ansys-yellow/15 transition-all" />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium text-gray-400">Password</label>
            <Link href="/auth/forgot" className="text-[10px] text-ansys-yellow hover:underline">
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <input type={showPwd ? "text" : "password"} required value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder="••••••••"
              className="w-full bg-[#0d0d0f] border border-[#252525] rounded-xl px-3.5 py-2.5 text-sm text-white
                placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
                focus:ring-ansys-yellow/15 transition-all pr-10" />
            <button type="button" onClick={() => setShowPwd((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-300 transition-colors">
              {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
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
          {loading ? <><Loader2 size={14} className="animate-spin" /> Signing in…</> : "Sign In"}
        </button>
      </form>

      <p className="text-center text-xs text-gray-600 mt-6">
        No account?{" "}
        <Link href="/auth/register" className="text-ansys-yellow hover:underline font-semibold">
          Start your free 14-day trial
        </Link>
      </p>

      {/* Dev quick-fill */}
      {process.env.NODE_ENV === "development" && (
        <button type="button" onClick={() => { setEmail("demo@suspensionlab.io"); setPassword("demo1234"); }}
          className="mt-4 w-full py-1.5 text-[10px] text-gray-700 hover:text-gray-500 border border-dashed
            border-[#1e1e1e] rounded-lg transition-colors">
          [DEV] Fill demo credentials
        </button>
      )}
    </div>
  );
}
