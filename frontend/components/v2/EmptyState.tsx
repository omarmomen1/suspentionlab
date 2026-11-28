import React from "react";

export interface EmptyStateProps {
  /** "unavailable" renders "Not available"; "not_run" renders "Not run". */
  kind?: "unavailable" | "not_run";
  /** Why, in plain words. Optional. */
  reason?: string;
  className?: string;
}

/**
 * Honest placeholder for a value that does not exist. Use it instead of printing
 * 0.00 or +0.0% for a missing or unrun result.
 */
export default function EmptyState({ kind = "unavailable", reason, className = "" }: EmptyStateProps) {
  return (
    <span data-testid="empty-state" data-kind={kind} className={`text-zinc-400 ${className}`}>
      <span className="text-sm">{kind === "not_run" ? "Not run" : "Not available"}</span>
      {reason && <span className="ml-2 text-xs text-zinc-300">{reason}</span>}
    </span>
  );
}

/** Returns the formatted number, or the EmptyState when the value is null, undefined or not finite. */
export function valueOrEmpty(
  v: number | null | undefined,
  format: (n: number) => string,
  kind: "unavailable" | "not_run" = "unavailable",
): React.ReactNode {
  return typeof v === "number" && Number.isFinite(v) ? format(v) : <EmptyState kind={kind} />;
}
