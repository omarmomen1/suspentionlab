"use client";

import React, { useState } from "react";
import { Sparkles, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

interface ExperimentButtonProps {
  label: string;
  onClick: () => Promise<any> | void;
  variant?: "primary" | "secondary" | "danger";
  size?: "sm" | "md" | "lg";
  className?: string;
  disabled?: boolean;
}

export default function ExperimentButton({
  label,
  onClick,
  variant = "primary",
  size = "md",
  className = "",
  disabled = false,
}: ExperimentButtonProps) {
  const [running, setRunning] = useState(false);
  const [feedback, setFeedback] = useState<"success" | "error" | null>(null);

  const handleClick = async () => {
    if (running || disabled) return;
    setRunning(true);
    setFeedback(null);
    try {
      await onClick();
      setFeedback("success");
      setTimeout(() => setFeedback(null), 2500);
    } catch {
      setFeedback("error");
      setTimeout(() => setFeedback(null), 3500);
    } finally {
      setRunning(false);
    }
  };

  const sizeClasses = {
    sm: "px-3 py-1.5 text-xs gap-1.5",
    md: "px-4 py-2 text-xs gap-2",
    lg: "px-5 py-2.5 text-sm gap-2",
  }[size];

  const variantClasses = {
    primary: "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_15px_rgba(242,169,0,0.25)]",
    secondary: "bg-purple-950/60 hover:bg-purple-900/60 text-purple-200 border border-purple-500/40 shadow-[0_0_15px_rgba(168,85,247,0.2)]",
    danger: "bg-rose-950/60 hover:bg-rose-900/60 text-rose-200 border border-rose-500/40",
  }[variant];

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={running || disabled}
      className={`inline-flex items-center justify-center font-bold rounded-xl font-mono uppercase tracking-wider transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${sizeClasses} ${variantClasses} ${className}`}
    >
      {running ? (
        <>
          <Loader2 size={14} className="animate-spin" />
          <span>Solving ODE...</span>
        </>
      ) : feedback === "success" ? (
        <>
          <CheckCircle2 size={14} className="text-emerald-400" />
          <span>Completed</span>
        </>
      ) : feedback === "error" ? (
        <>
          <AlertCircle size={14} className="text-rose-400" />
          <span>Execution Failed</span>
        </>
      ) : (
        <>
          <Sparkles size={14} className={variant === "primary" ? "text-black" : "text-purple-400"} />
          <span>{label}</span>
        </>
      )}
    </button>
  );
}
