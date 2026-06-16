"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Search, Calculator, Activity, Settings2, ShieldAlert, BookOpen,
  LayoutDashboard, LogOut, Code2, Zap, GitBranch
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { user, logout } = useAuth();

  // Toggle the menu when ⌘K is pressed
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const runCommand = (command: () => void) => {
    setOpen(false);
    command();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] sm:pt-[20vh]">
      {/* Blurred overlay */}
      <div 
        className="fixed inset-0 bg-black/60 backdrop-blur-sm" 
        onClick={() => setOpen(false)}
      />

      {/* CMDK Window */}
      <Command 
        className="relative z-10 w-full max-w-[600px] overflow-hidden rounded-2xl border border-white/10 bg-[#0d0d0d] shadow-2xl shadow-black ring-1 ring-white/5 animate-in fade-in zoom-in-95 duration-200"
      >
        <div className="flex items-center border-b border-white/10 px-4">
          <Search className="h-5 w-5 text-gray-500 mr-2" />
          <Command.Input 
            placeholder="Search tools, settings, or simulations..." 
            className="flex h-14 w-full rounded-md bg-transparent text-sm text-white placeholder-gray-500 outline-none focus:ring-0 border-none"
            autoFocus
          />
        </div>

        <Command.List className="max-h-[300px] overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-[#333] scrollbar-track-transparent">
          <Command.Empty className="py-6 text-center text-sm text-gray-500">
            No results found.
          </Command.Empty>

          <Command.Group heading="Simulation Tools" className="px-2 py-2 text-xs font-medium text-gray-500">
            <Command.Item 
              onSelect={() => runCommand(() => router.push("/quarter-car"))}
              className="flex items-center gap-2 px-3 py-3 mt-1 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-ansys-yellow/10 aria-selected:text-ansys-yellow transition-colors"
            >
              <Calculator size={16} /> Quarter Car Sandbox
            </Command.Item>
            <Command.Item 
              onSelect={() => runCommand(() => router.push("/sensitivity"))}
              className="flex items-center gap-2 px-3 py-3 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-ansys-yellow/10 aria-selected:text-ansys-yellow transition-colors"
            >
              <Activity size={16} /> Sensitivity Sweep
            </Command.Item>
            <Command.Item 
              onSelect={() => runCommand(() => router.push("/nvh"))}
              className="flex items-center gap-2 px-3 py-3 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-ansys-yellow/10 aria-selected:text-ansys-yellow transition-colors"
            >
              <Zap size={16} /> Acoustics & NVH
            </Command.Item>
            <Command.Item 
              onSelect={() => runCommand(() => router.push("/handling"))}
              className="flex items-center gap-2 px-3 py-3 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-ansys-yellow/10 aria-selected:text-ansys-yellow transition-colors"
            >
              <GitBranch size={16} /> Full Car Handling
            </Command.Item>
          </Command.Group>

          <Command.Group heading="General" className="px-2 py-2 text-xs font-medium text-gray-500 border-t border-white/5 mt-2 pt-3">
            <Command.Item 
              onSelect={() => runCommand(() => router.push("/garage"))}
              className="flex items-center gap-2 px-3 py-3 mt-1 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-white/10 aria-selected:text-white transition-colors"
            >
              <LayoutDashboard size={16} /> My Garage
            </Command.Item>
            <Command.Item 
              onSelect={() => runCommand(() => router.push("/settings"))}
              className="flex items-center gap-2 px-3 py-3 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-white/10 aria-selected:text-white transition-colors"
            >
              <Settings2 size={16} /> Team Settings
            </Command.Item>
            <Command.Item 
              onSelect={() => runCommand(() => window.open("https://docs.suspensionlab.com", "_blank"))}
              className="flex items-center gap-2 px-3 py-3 text-sm text-gray-300 rounded-lg cursor-pointer aria-selected:bg-white/10 aria-selected:text-white transition-colors"
            >
              <BookOpen size={16} /> Documentation
            </Command.Item>
          </Command.Group>

          {user && (
            <Command.Group heading="Account" className="px-2 py-2 text-xs font-medium text-gray-500 border-t border-white/5 mt-2 pt-3">
              <Command.Item 
                onSelect={() => runCommand(() => logout())}
                className="flex items-center gap-2 px-3 py-3 mt-1 text-sm text-red-400 rounded-lg cursor-pointer aria-selected:bg-red-500/10 aria-selected:text-red-300 transition-colors"
              >
                <LogOut size={16} /> Logout
              </Command.Item>
            </Command.Group>
          )}
        </Command.List>

        <div className="flex items-center justify-between border-t border-white/10 bg-[#0a0a0a] px-4 py-3 text-xs text-gray-500">
          <div className="flex items-center gap-2">
            Use <kbd className="rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 font-mono text-[10px] text-gray-300">↑</kbd> <kbd className="rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 font-mono text-[10px] text-gray-300">↓</kbd> to navigate
          </div>
          <div className="flex items-center gap-2">
            <kbd className="rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 font-mono text-[10px] text-gray-300">Enter</kbd> to select
          </div>
        </div>
      </Command>
    </div>
  );
}
