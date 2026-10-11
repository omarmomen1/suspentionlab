"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  ChevronDown, 
  Sparkles, 
  Wrench, 
  Activity, 
  GitCompare, 
  Sliders, 
  ShieldCheck, 
  FileText,
  Layers,
  FlaskConical,
  Clock
} from "lucide-react";
import GlobalSearchTrigger from "./GlobalSearchTrigger";
import UserMenu from "./UserMenu";
import MobileNav from "./MobileNav";

interface NavDropdownItem {
  href: string;
  label: string;
  desc: string;
}

const ALL_SOLVER_ITEMS: NavDropdownItem[] = [
  { href: "/quarter-car", label: "Quarter Car (2-DOF)", desc: "Corner bounce, damping & ISO 2631 ride comfort" },
  { href: "/half-car",    label: "Half Car (4-DOF)",    desc: "Pitch & bounce pitch-center coupling solver" },
  { href: "/full-car",    label: "Full Car (7-DOF)",    desc: "4-corner multi-body dynamic chassis simulation" },
  { href: "/active",      label: "Active Suspension",   desc: "Skyhook / groundhook & LQR control systems" },
  { href: "/handling",    label: "Handling Dynamics",   desc: "Bicycle model, slip angles & transient yaw response" },
  { href: "/kinematics",  label: "Kinematics & Geometry", desc: "Roll centers, camber gain & bump steer curves" },
  { href: "/lap-sim",     label: "Lap Time Simulation", desc: "Quasi-static track solver & GG friction limits" },
  { href: "/yaw-dynamics",label: "Yaw Dynamics & MMM",  desc: "Milliken Moment Diagram & aerodynamic balance" },
  { href: "/nvh",         label: "NVH & Acoustics",     desc: "FFT frequency spectrum & cabin resonance isolation" },
];

const VALIDATION_ITEMS: NavDropdownItem[] = [
  { href: "/correlation", label: "Correlation Cockpit", desc: "Measured telemetry vs simulated physical correlation" },
  { href: "/digital-twin",label: "Digital Twin",        desc: "Virtual vehicle state observer & continuous calibration" },
  { href: "/timeline",    label: "Timeline & Decisions", desc: "Vehicle development history, diffs & cryptographic sign-off" },
  { href: "/vnv",         label: "V&V Evidence Suite",  desc: "Numerical solver validation & test benchmarks" },
  { href: "/cae",         label: "CAE Interoperability", desc: "MSC Adams, MATLAB & CarMaker import/export decks" },
  { href: "/audit",       label: "Audit & Governance",  desc: "Tamper-evident cryptographic ledger" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const navRef = useRef<HTMLDivElement>(null);

  // Close dropdown on route change
  useEffect(() => {
    setOpenMenu(null);
  }, [pathname]);

  // Close dropdown on outside click or Escape key
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenMenu(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const isSolversActive = ALL_SOLVER_ITEMS.some((item) => pathname === item.href || pathname.startsWith(item.href + "/"));
  const isValidationActive = VALIDATION_ITEMS.some((item) => pathname === item.href || pathname.startsWith(item.href + "/"));

  return (
    <nav 
      className="w-full h-[52px] bg-[rgba(10,10,12,0.95)] backdrop-blur-xl border-b border-white/[0.08] fixed top-0 z-50 px-4 sm:px-6 select-none" 
      ref={navRef}
      aria-label="Main Navigation"
    >
      <div className="max-w-[1560px] h-full mx-auto flex items-center justify-between gap-4">
        
        {/* Left: Brand Logo & Mobile Drawer */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="lg:hidden">
            <MobileNav />
          </div>
          <Link href="/" className="text-gray-300 hover:text-white transition-colors flex items-center gap-2 group">
            <div className="w-7 h-7 rounded-lg bg-ansys-yellow/10 border border-ansys-yellow/30 flex items-center justify-center group-hover:border-ansys-yellow/60 transition-colors">
              <svg viewBox="0 0 24 24" fill="none" height="15" width="15" role="img" aria-label="SuspensionLab logo">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="#f2a900" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
              </svg>
            </div>
            <span className="text-xs font-bold text-white tracking-tight">
              Suspension<span className="text-ansys-yellow">Lab</span>
              <span className="ml-1.5 px-1.5 py-0.5 rounded text-[9px] font-semibold bg-ansys-yellow/20 text-ansys-yellow border border-ansys-yellow/30 uppercase tracking-widest hidden sm:inline-block">
                PRO
              </span>
            </span>
          </Link>
        </div>

        {/* Center: Executive Engineering Workflow Navigation */}
        <div className="hidden lg:flex items-center space-x-1 text-xs font-medium">
          
          {/* Stage 1: Setup */}
          <Link
            href="/garage"
            aria-current={pathname === "/garage" ? "page" : undefined}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
              pathname === "/garage"
                ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
                : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            <Wrench size={13} className={pathname === "/garage" ? "text-ansys-yellow" : "text-zinc-500"} />
            <span>Setup</span>
          </Link>

          {/* Stage 2: Experiment */}
          <Link
            href="/experiment"
            aria-current={pathname === "/experiment" ? "page" : undefined}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
              pathname === "/experiment"
                ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
                : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            <FlaskConical size={13} className={pathname === "/experiment" ? "text-ansys-yellow" : "text-zinc-500"} />
            <span>Experiment</span>
          </Link>

          {/* Stage 3: Analyze & Solvers Suite */}
          <div className="relative">
            <div className={`flex items-center rounded-lg transition-all border ${
              isSolversActive || openMenu === "solvers"
                ? "bg-white/[0.08] border-white/10 text-white shadow-sm"
                : "border-transparent text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}>
              <Link
                href="/quarter-car"
                aria-current={isSolversActive ? "page" : undefined}
                className="flex items-center gap-1.5 pl-2.5 pr-1 py-1.5 font-medium"
              >
                <Activity size={13} className={isSolversActive ? "text-ansys-yellow" : "text-zinc-500"} />
                <span>Analyze</span>
              </Link>
              <button
                id="analyze-solvers-dropdown-btn"
                type="button"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setOpenMenu((prev) => (prev === "solvers" ? null : "solvers"));
                }}
                aria-expanded={openMenu === "solvers"}
                aria-haspopup="true"
                aria-controls="solvers-dropdown"
                aria-label="All Physics Solvers"
                className="pr-2 pl-1 py-1.5 text-zinc-400 hover:text-white"
                title="All Physics Solvers"
              >
                <ChevronDown size={11} className={`transition-transform duration-150 ${openMenu === "solvers" ? "rotate-180 text-ansys-yellow" : ""}`} />
              </button>
            </div>

            {openMenu === "solvers" && (
              <div id="solvers-dropdown" className="absolute left-0 top-full mt-2 w-80 bg-[#0e0e12] border border-white/10 rounded-xl shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95 duration-100">
                <div className="px-2.5 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                  Vehicle Physics Engines
                </div>
                <div className="grid grid-cols-1 gap-1 max-h-[380px] overflow-y-auto custom-scrollbar">
                  {ALL_SOLVER_ITEMS.map((item) => {
                    const active = pathname === item.href;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={`block px-3 py-2 rounded-lg transition-colors ${
                          active
                            ? "bg-ansys-yellow/10 text-ansys-yellow border border-ansys-yellow/20"
                            : "hover:bg-white/5 text-gray-300 hover:text-white"
                        }`}
                      >
                        <div className="font-semibold text-xs text-white">{item.label}</div>
                        <div className="text-[10px] text-gray-400 mt-0.5 leading-tight">{item.desc}</div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Stage 4: Compare */}
          <Link
            href="/compare"
            aria-current={pathname === "/compare" || pathname === "/setup-sensitivity" ? "page" : undefined}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
              pathname === "/compare" || pathname === "/setup-sensitivity"
                ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
                : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            <GitCompare size={13} className={pathname === "/compare" || pathname === "/setup-sensitivity" ? "text-ansys-yellow" : "text-zinc-500"} />
            <span>Compare</span>
          </Link>

          {/* Stage 5: Optimize */}
          <Link
            href="/optimize"
            aria-current={pathname === "/optimize" || pathname === "/ai-engineer" ? "page" : undefined}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
              pathname === "/optimize" || pathname === "/ai-engineer"
                ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
                : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            <Sparkles size={13} className={pathname === "/optimize" || pathname === "/ai-engineer" ? "text-ansys-yellow" : "text-zinc-500"} />
            <span>Optimize</span>
          </Link>

          {/* Stage 6: Validation & Fleet Intelligence Suite */}
          <div className="relative">
            <button
              id="validation-dropdown-btn"
              type="button"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setOpenMenu((prev) => (prev === "validation" ? null : "validation"));
              }}
              aria-expanded={openMenu === "validation"}
              aria-haspopup="true"
              aria-controls="validation-dropdown"
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
                isValidationActive || openMenu === "validation"
                  ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
                  : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
              }`}
            >
              <ShieldCheck size={13} className={isValidationActive ? "text-ansys-yellow" : "text-zinc-500"} />
              <span>Validation</span>
              <ChevronDown size={11} className={`transition-transform duration-150 ${openMenu === "validation" ? "rotate-180 text-ansys-yellow" : "text-zinc-500"}`} />
            </button>

            {openMenu === "validation" && (
              <div id="validation-dropdown" className="absolute left-0 top-full mt-2 w-80 bg-[#0e0e12] border border-white/10 rounded-xl shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95 duration-100">
                <div className="px-2.5 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                  Validation & Governance
                </div>
                <div className="grid grid-cols-1 gap-1">
                  {VALIDATION_ITEMS.map((item) => {
                    const active = pathname === item.href;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={`block px-3 py-2 rounded-lg transition-colors ${
                          active
                            ? "bg-ansys-yellow/10 text-ansys-yellow border border-ansys-yellow/20"
                            : "hover:bg-white/5 text-gray-300 hover:text-white"
                        }`}
                      >
                        <div className="font-semibold text-xs text-white">{item.label}</div>
                        <div className="text-[10px] text-gray-400 mt-0.5 leading-tight">{item.desc}</div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Stage 7: Report */}
          <Link
            href="/report"
            aria-current={pathname === "/report" ? "page" : undefined}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
              pathname === "/report"
                ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
                : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            <FileText size={13} className={pathname === "/report" ? "text-ansys-yellow" : "text-zinc-500"} />
            <span>Report</span>
          </Link>

        </div>

        {/* Right Side: Docs, Pricing, Global Search & User Menu */}
        <div className="flex items-center gap-2.5 shrink-0">
          <Link
            href="/docs"
            className={`hidden md:inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
              pathname === "/docs" ? "text-white bg-white/[0.08]" : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            Docs
          </Link>
          <Link
            href="/pricing"
            className={`hidden md:inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
              pathname === "/pricing" ? "text-white bg-white/[0.08]" : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            Pricing
          </Link>
          <div className="h-4 w-px bg-white/10 mx-0.5 hidden md:block" role="separator" aria-orientation="vertical" />
          <GlobalSearchTrigger />
          <UserMenu />
        </div>

      </div>
    </nav>
  );
}
