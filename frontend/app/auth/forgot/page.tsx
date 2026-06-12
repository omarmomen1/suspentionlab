"use client";

import React, { useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/forgot-password?email=${encodeURIComponent(email)}`, {
        method: "POST",
      });
      if (res.ok) {
        setMessage("If an account with that email exists, a reset link has been sent.");
      } else {
        setMessage("An error occurred. Please try again later.");
      }
    } catch (err) {
      setMessage("A network error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-white tracking-tight">Reset Password</h1>
        <p className="text-sm text-zinc-400 mt-2">
          Enter your email and we'll send you a reset link.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {message && (
          <div className="p-3 bg-zinc-800/50 border border-zinc-700 rounded-md text-sm text-ansys-yellow text-center">
            {message}
          </div>
        )}
        <div className="space-y-2">
          <label htmlFor="email" className="text-sm font-medium text-zinc-300">
            Email address
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-2 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-ansys-gold"
            placeholder="name@example.com"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-black bg-ansys-gold hover:bg-ansys-yellow focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-ansys-gold focus:ring-offset-zinc-900 disabled:opacity-50 transition-all"
        >
          {loading ? "Sending..." : "Send Reset Link"}
        </button>
      </form>

      <div className="text-center text-sm">
        <span className="text-zinc-400">Remembered your password? </span>
        <Link href="/auth/login" className="text-ansys-gold hover:text-ansys-yellow transition-colors font-medium">
          Sign in
        </Link>
      </div>
    </div>
  );
}
