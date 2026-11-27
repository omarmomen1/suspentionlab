"use client";
import React, { createContext, useContext, useState } from "react";

export type ShellPane = "params" | "canvas" | "verdict";

const PaneContext = createContext<ShellPane>("canvas");

const PANE_LABEL: Record<ShellPane, string> = { params: "Parameters", canvas: "Results", verdict: "Verdict" };

export interface StudioShellProps {
  /** Start pane on screens below lg (single-column tabs). Default: results. */
  defaultPane?: ShellPane;
  className?: string;
  children: React.ReactNode;
}

/**
 * Three-column studio layout: Left parameters rail | centre canvas + tabs | right verdict rail.
 * Below the lg breakpoint it collapses to a single column with a 3-tab switcher
 * (Parameters / Results / Verdict), usable at 390 px. Compose with
 * ShellLeft, ShellCenter and ShellRight as direct children.
 */
export default function StudioShell({ defaultPane = "canvas", className = "", children }: StudioShellProps) {
  const [pane, setPane] = useState<ShellPane>(defaultPane);
  return (
    <PaneContext.Provider value={pane}>
      <div data-testid="studio-shell" data-pane={pane} className={`flex flex-1 min-h-0 flex-col gap-3 lg:flex-row lg:gap-4 ${className}`}>
        <div role="tablist" aria-label="Studio panes" className="flex shrink-0 gap-px rounded border border-hairline bg-hairline lg:hidden">
          {(Object.keys(PANE_LABEL) as ShellPane[]).map((p) => (
            <button
              key={p}
              role="tab"
              type="button"
              aria-selected={pane === p}
              data-pane-tab={p}
              onClick={() => setPane(p)}
              className={`flex-1 px-3 py-2 text-xs font-semibold ${pane === p ? "bg-signal text-carbon" : "bg-panel text-gray-300"}`}
            >
              {PANE_LABEL[p]}
            </button>
          ))}
        </div>
        {children}
      </div>
    </PaneContext.Provider>
  );
}

function usePane(): ShellPane {
  return useContext(PaneContext);
}

/** Left parameters rail (fixed width on desktop). */
export function ShellLeft({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const pane = usePane();
  return (
    <div data-shell-region="params" className={`${pane === "params" ? "block" : "hidden"} lg:block min-h-0 lg:shrink-0 ${className}`}>
      {children}
    </div>
  );
}

/** Centre hero canvas and secondary tabs. */
export function ShellCenter({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const pane = usePane();
  return (
    <div data-shell-region="canvas" className={`${pane === "canvas" ? "flex" : "hidden"} lg:flex min-h-0 min-w-0 flex-1 flex-col ${className}`}>
      {children}
    </div>
  );
}

/** Right verdict rail. */
export function ShellRight({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const pane = usePane();
  return (
    <div data-shell-region="verdict" className={`${pane === "verdict" ? "block" : "hidden"} lg:block min-h-0 lg:w-72 lg:shrink-0 ${className}`}>
      {children}
    </div>
  );
}
