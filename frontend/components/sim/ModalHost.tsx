"use client";

/**
 * components/sim/ModalHost.tsx (P1-UX-02)
 * Themed replacements for native prompt()/alert().
 *
 * Usage:
 *   Mount <PromptModalHost /> once in the root layout.
 *   Then from anywhere:
 *     const name = await promptModal("Name this setup:", "Default");
 *     void alertModal("Something happened");
 */

import React, { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

type Mode = "prompt" | "alert";
interface ModalState {
  open: boolean;
  mode: Mode;
  title: string;
  defaultValue: string;
}

type Listener = (s: ModalState) => void;

let listener: Listener | null = null;
let currentState: ModalState = { open: false, mode: "alert", title: "", defaultValue: "" };
let resolver: ((v: string | null) => void) | null = null;

function publish(state: ModalState) {
  currentState = state;
  listener?.(state);
}

/** Themed prompt(). Resolves with the entered string, or null on cancel. */
export function promptModal(title: string, defaultValue = ""): Promise<string | null> {
  return new Promise((resolve) => {
    resolver = resolve;
    publish({ open: true, mode: "prompt", title, defaultValue });
  });
}

/** Themed alert(). Resolves when dismissed. */
export function alertModal(title: string): Promise<void> {
  return new Promise((resolve) => {
    resolver = (() => { resolve(); }) as unknown as (v: string | null) => void;
    publish({ open: true, mode: "alert", title, defaultValue: "" });
  });
}

function closeWith(value: string | null) {
  publish({ ...currentState, open: false });
  const r = resolver;
  resolver = null;
  r?.(value);
}

export default function PromptModalHost() {
  const [state, setState] = useState<ModalState>(currentState);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listener = setState;
    return () => { listener = null; };
  }, []);

  useEffect(() => {
    if (state.open && state.mode === "prompt") {
      setValue(state.defaultValue);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [state.open, state.mode, state.defaultValue]);

  if (!state.open) return null;

  const confirm = () => closeWith(state.mode === "prompt" ? (value.trim() || null) : null);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={state.mode === "prompt" ? "Input required" : "Notice"}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => closeWith(null)} />
      <div className="relative w-full max-w-sm bg-[#141416] border border-[#2a2a2a] rounded-xl shadow-2xl p-5">
        <button
          onClick={() => closeWith(null)}
          className="absolute top-3 right-3 text-gray-500 hover:text-white transition-colors"
          aria-label="Close"
        >
          <X size={15} />
        </button>
        <h3 className={`text-sm font-bold mb-4 ${state.mode === "alert" ? "text-amber-400" : "text-white"}`}>
          {state.title}
        </h3>

        {state.mode === "prompt" && (
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") confirm();
              if (e.key === "Escape") closeWith(null);
            }}
            className="w-full bg-[#0d0d0d] border border-[#2a2a2a] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/50 mb-4"
          />
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={() => closeWith(null)}
            className="px-3 py-1.5 text-xs font-bold rounded-lg bg-[#1e1e20] text-gray-400 hover:text-white transition-all"
          >
            Cancel
          </button>
          <button
            onClick={confirm}
            className="px-3 py-1.5 text-xs font-bold rounded-lg bg-ansys-yellow text-black hover:brightness-110 transition-all"
          >
            {state.mode === "prompt" ? "Save" : "OK"}
          </button>
        </div>
      </div>
    </div>
  );
}
