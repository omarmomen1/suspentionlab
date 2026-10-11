"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Search,
  Calculator,
  Activity,
  Settings2,
  BookOpen,
  LayoutDashboard,
  LogOut,
  Zap,
  GitBranch,
  Sliders,
  Radio,
  FileText,
  ShieldCheck,
  Cpu,
  Layers,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  LucideIcon,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { SearchApi, UniversalSearchResultItem } from "../lib/api_client";

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  vehicles: LayoutDashboard,
  setups: Sliders,
  telemetry: Radio,
  simulations: Cpu,
  experiments: Activity,
  optimizations: Sparkles,
  decisions: ShieldCheck,
  reports: FileText,
  parameters: Zap,
};

const CATEGORY_LABELS: Record<string, string> = {
  vehicles: "Vehicles & Models",
  setups: "Suspension Setups",
  telemetry: "Telemetry Runs",
  simulations: "Physics Simulations",
  experiments: "Engineering Experiments",
  optimizations: "Multi-Objective Optimizations",
  decisions: "Engineering Decisions & Approvals",
  reports: "Engineering Reports",
  parameters: "Domain Parameters & Ontologies",
};

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<UniversalSearchResultItem[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { user, logout } = useAuth();

  // Debounced search when query changes
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const resp = await SearchApi.search(query.trim(), { limit: 25 });
        setResults(resp.results || []);
      } catch (err) {
        console.warn("Universal search query failed:", err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  // Dialog semantics: Escape closes, Tab is trapped inside
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        return;
      }
      if (e.key === "Tab") {
        const container = containerRef.current;
        if (!container) return;
        const focusables = Array.from(
          container.querySelectorAll<HTMLElement>(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => !el.hasAttribute("disabled"));
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  // Toggle the menu when ⌘K is pressed
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const runCommand = (command: () => void) => {
    setOpen(false);
    setQuery("");
    command();
  };

  if (!open) return null;

  // Group search results by category
  const groupedResults = results.reduce<Record<string, UniversalSearchResultItem[]>>(
    (acc, item) => {
      const cat = item.category || "general";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(item);
      return acc;
    },
    {}
  );

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] sm:pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Universal Engineering Command Palette"
    >
      {/* Blurred overlay */}
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* CMDK Window */}
      <Command
        className="relative z-10 w-full max-w-[680px] overflow-hidden rounded-2xl border border-zinc-700 bg-zinc-950 shadow-2xl shadow-black ring-1 ring-zinc-800 animate-in fade-in zoom-in-95 duration-150"
      >
        <div className="flex items-center border-b border-zinc-800 px-4">
          <Search className="h-5 w-5 text-zinc-400 mr-2 shrink-0" />
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="Search setups, telemetry, experiments, decisions, CAE..."
            className="flex h-14 w-full rounded-md bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:ring-0 border-none"
            autoFocus
          />
          {loading && <Loader2 className="h-4 w-4 text-ansys-yellow animate-spin ml-2" />}
        </div>

        <Command.List className="max-h-[380px] overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent">
          <Command.Empty className="py-8 text-center text-sm text-zinc-500">
            {loading ? "Searching across engineering domains..." : "No engineering artifacts found."}
          </Command.Empty>

          {/* If query entered: Render Universal Search Results */}
          {query.trim().length > 0 &&
            Object.entries(groupedResults).map(([cat, items]) => {
              const CatIcon = CATEGORY_ICONS[cat] || Layers;
              const catLabel = CATEGORY_LABELS[cat] || cat.toUpperCase();

              return (
                <Command.Group
                  key={cat}
                  heading={catLabel}
                  className="px-2 py-1 text-xs font-semibold text-zinc-400"
                >
                  {items.map((item) => (
                    <Command.Item
                      key={item.id}
                      value={`${item.title} ${item.subtitle} ${item.id}`}
                      onSelect={() => runCommand(() => router.push(item.url))}
                      className="flex items-center justify-between gap-3 px-3 py-2.5 my-1 text-sm text-zinc-200 rounded-lg cursor-pointer aria-selected:bg-zinc-800/80 aria-selected:text-white transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="p-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
                          <CatIcon size={14} />
                        </div>
                        <div className="min-w-0">
                          <div className="font-medium truncate text-zinc-100 text-xs">
                            {item.title}
                          </div>
                          <div className="text-[11px] text-zinc-400 truncate">
                            {item.subtitle}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {item.status && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-zinc-900 border border-zinc-800 text-zinc-400">
                            {item.status}
                          </span>
                        )}
                        <span className="text-[10px] font-mono text-zinc-500">
                          {item.id}
                        </span>
                      </div>
                    </Command.Item>
                  ))}
                </Command.Group>
              );
            })}

          {/* When query is empty: Default Quick Navigation Hub */}
          {query.trim().length === 0 && (
            <>
              <Command.Group heading="Engineering Workflow Hubs" className="px-2 py-1 text-xs font-semibold text-zinc-400">
                <Command.Item
                  onSelect={() => runCommand(() => router.push("/quarter-car"))}
                  className="flex items-center gap-2.5 px-3 py-2.5 my-0.5 text-xs text-zinc-200 rounded-lg cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-ansys-yellow transition-colors"
                >
                  <Calculator size={15} className="text-zinc-400" />
                  <div>
                    <span className="font-medium">Quarter Car Decision Sandbox</span>
                    <span className="text-[11px] text-zinc-500 block">Interactive forward ODE solver &amp; ride/handling analysis</span>
                  </div>
                </Command.Item>

                <Command.Item
                  onSelect={() => runCommand(() => router.push("/digital-twin"))}
                  className="flex items-center gap-2.5 px-3 py-2.5 my-0.5 text-xs text-zinc-200 rounded-lg cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-ansys-yellow transition-colors"
                >
                  <Radio size={15} className="text-cyan-400" />
                  <div>
                    <span className="font-medium">Digital Twin &amp; Telemetry Cockpit</span>
                    <span className="text-[11px] text-zinc-500 block">Measured vs simulated forward correlation &amp; model drift</span>
                  </div>
                </Command.Item>

                <Command.Item
                  onSelect={() => runCommand(() => router.push("/timeline"))}
                  className="flex items-center gap-2.5 px-3 py-2.5 my-0.5 text-xs text-zinc-200 rounded-lg cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-ansys-yellow transition-colors"
                >
                  <ShieldCheck size={15} className="text-emerald-400" />
                  <div>
                    <span className="font-medium">Engineering Timeline &amp; Decision OS</span>
                    <span className="text-[11px] text-zinc-500 block">Trace institutional memory: Question → Evidence → Approval</span>
                  </div>
                </Command.Item>

                <Command.Item
                  onSelect={() => runCommand(() => router.push("/cae"))}
                  className="flex items-center gap-2.5 px-3 py-2.5 my-0.5 text-xs text-zinc-200 rounded-lg cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-ansys-yellow transition-colors"
                >
                  <Layers size={15} className="text-purple-400" />
                  <div>
                    <span className="font-medium">Incumbent CAE Interoperability Hub</span>
                    <span className="text-[11px] text-zinc-500 block">MSC Adams, MATLAB/Simulink &amp; CarMaker solver comparison</span>
                  </div>
                </Command.Item>

                <Command.Item
                  onSelect={() => runCommand(() => router.push("/ai-engineer"))}
                  className="flex items-center gap-2.5 px-3 py-2.5 my-0.5 text-xs text-zinc-200 rounded-lg cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-ansys-yellow transition-colors"
                >
                  <Sparkles size={15} className="text-amber-400" />
                  <div>
                    <span className="font-medium">Engineering AI Copilot</span>
                    <span className="text-[11px] text-zinc-500 block">5-part evidence-backed root cause investigation</span>
                  </div>
                </Command.Item>
              </Command.Group>

              <Command.Group heading="General &amp; Documentation" className="px-2 py-1 text-xs font-semibold text-zinc-400 border-t border-zinc-800 mt-2 pt-2">
                <Command.Item
                  onSelect={() => runCommand(() => router.push("/garage"))}
                  className="flex items-center gap-2.5 px-3 py-2 text-xs text-zinc-300 rounded-lg cursor-pointer aria-selected:bg-zinc-800 transition-colors"
                >
                  <LayoutDashboard size={14} /> My Garage
                </Command.Item>
                <Command.Item
                  onSelect={() => runCommand(() => router.push("/settings"))}
                  className="flex items-center gap-2.5 px-3 py-2 text-xs text-zinc-300 rounded-lg cursor-pointer aria-selected:bg-zinc-800 transition-colors"
                >
                  <Settings2 size={14} /> Team Settings &amp; API Keys
                </Command.Item>
                <Command.Item
                  onSelect={() => runCommand(() => window.open("https://docs.suspensionlab.com", "_blank"))}
                  className="flex items-center gap-2.5 px-3 py-2 text-xs text-zinc-300 rounded-lg cursor-pointer aria-selected:bg-zinc-800 transition-colors"
                >
                  <BookOpen size={14} /> Documentation &amp; Physics Manual
                </Command.Item>
              </Command.Group>

              {user && (
                <Command.Group heading="Account" className="px-2 py-1 text-xs font-semibold text-zinc-400 border-t border-zinc-800 mt-2 pt-2">
                  <Command.Item
                    onSelect={() => runCommand(() => logout())}
                    className="flex items-center gap-2.5 px-3 py-2 text-xs text-red-400 rounded-lg cursor-pointer aria-selected:bg-red-950/30 aria-selected:text-red-300 transition-colors"
                  >
                    <LogOut size={14} /> Logout ({user.name || user.email})
                  </Command.Item>
                </Command.Group>
              )}
            </>
          )}
        </Command.List>

        <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-900/60 px-4 py-2.5 text-xs text-zinc-500 font-mono">
          <div className="flex items-center gap-2">
            <span>Navigate:</span>
            <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">↑</kbd>
            <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">↓</kbd>
          </div>
          <div className="flex items-center gap-2">
            <span>Select:</span>
            <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">Enter</kbd>
            <span>Close:</span>
            <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">Esc</kbd>
          </div>
        </div>
      </Command>
    </div>
  );
}
