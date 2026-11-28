"use client";
import React, { useState } from "react";
import { formatApiError } from "../../lib/api_client";

export interface ErrorCardProps {
  error: unknown;
  /** Short phrase for what failed, passed to formatApiError. */
  context: string;
  onRetry?: () => void;
  className?: string;
}

const isDev = (): boolean => process.env.NODE_ENV !== "production";

function rawTrace(err: unknown): string {
  if (err instanceof Error) return err.stack || `${err.name}: ${err.message}`;
  try {
    return JSON.stringify(err, null, 2) ?? String(err);
  } catch {
    return String(err);
  }
}

/** Wraps Wave 5B formatApiError (never replaces it). The raw trace toggle exists in development only. */
export default function ErrorCard({ error, context, onRetry, className = "" }: ErrorCardProps) {
  const [showRaw, setShowRaw] = useState(false);
  const message = formatApiError(error, context);
  return (
    <div role="alert" data-testid="error-card" className={`rounded border border-fault/50 bg-fault/10 p-3 text-sm ${className}`}>
      <p className="text-fault font-semibold">{message}</p>
      <div className="mt-2 flex items-center gap-3 text-xs">
        {onRetry && (
          <button type="button" onClick={onRetry} className="rounded border border-white/20 px-2 py-1 text-gray-200 hover:bg-white/5">
            Retry
          </button>
        )}
        {isDev() && (
          <button type="button" onClick={() => setShowRaw((v) => !v)} className="text-gray-400 underline" data-testid="error-card-raw-toggle">
            {showRaw ? "Hide raw trace" : "Show raw trace (dev only)"}
          </button>
        )}
      </div>
      {isDev() && showRaw && (
        <pre data-testid="error-card-raw" className="mt-2 max-h-48 overflow-auto text-xs text-gray-400 v2-num">{rawTrace(error)}</pre>
      )}
    </div>
  );
}
