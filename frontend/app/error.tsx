"use client";

import { useEffect } from "react";

/**
 * Global error boundary (P1-SEC-04): never render raw error.message to the
 * user — it can leak backend stack traces, connection strings, or internal
 * API paths. The full error goes to the console (and Sentry when wired);
 * the user sees a generic message plus the digest for support correlation.
 */
export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
    // TODO: forward `error` and `error.digest` to Sentry in production.
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4">
      <h2 className="text-2xl font-bold mb-4">Something went wrong!</h2>
      <p className="text-slate-400 mb-2">
        An unexpected error occurred. Our team has been notified.
      </p>
      {process.env.NODE_ENV !== "production" && error?.message && (
        <div className="max-w-xl my-3 px-3 py-2 rounded-lg bg-zinc-900/90 border border-red-500/30 text-red-300 font-mono text-xs text-left overflow-x-auto shadow-inner">
          <span className="text-red-400 font-bold block mb-0.5">Diagnostic Error:</span>
          <span className="break-words select-all">{error.message}</span>
        </div>
      )}
      {error?.digest && (
        <p className="text-xs font-mono text-zinc-400 mb-4">
          Error reference: {error.digest}
        </p>
      )}
      <button
        onClick={() => reset()}
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
      >
        Try again
      </button>
    </div>
  );
}
