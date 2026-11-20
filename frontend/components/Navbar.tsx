"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../contexts/AuthContext";
import {
  ChevronDown,
  Sparkles,
  Wrench,
  Activity,
  GitCompare,
  Sliders,
  ShieldCheck,
  FileText,
  FlaskConical,
  Compass,
  Car,
  type LucideIcon,
} from "lucide-react";
import GlobalSearchTrigger from "./GlobalSearchTrigger";
import UserMenu from "./UserMenu";
import MobileNav from "./MobileNav";
import {
  ALL_SOLVER_ITEMS,
  STUDIO_PRICING_CTA,
  STUDIO_TOOLS,
  VALIDATION_ITEMS,
  isStudioModeEnabled,
  isToolGroupActive,
  matchesRoute,
  type NavDropdownItem,
  type StudioIconKey,
  type StudioToolGroup,
} from "../lib/navigation";

const STUDIO_ICONS: Record<StudioIconKey, LucideIcon> = {
  kinematics: Compass,
  quarter_car: Activity,
  full_car: Car,
  correlation: GitCompare,
  optimizer: Sliders,
  memory: FileText,
  ai: Sparkles,
};

function StudioToolLabel({ id, fallback }: { id: string; fallback: string }) {
  switch (id) {
    case "kinematics":
      return (
        <>
          3D Kinematics<span className="sr-only min-[1440px]:not-sr-only"> &amp; Hardpoints</span>
        </>
      );
    case "quarter-car":
      return (
        <>
          Quarter-Car<span className="sr-only min-[1440px]:not-sr-only"> &amp; Damper Studio</span>
        </>
      );
    case "full-car-handling":
      return (
        <>
          Full-Car<span className="sr-only xl:not-sr-only"> &amp; Handling</span>
        </>
      );
    case "correlation-compare":
      return (
        <>
          <span className="sr-only xl:not-sr-only">Telemetry &amp; </span>
          <span className="sr-only min-[1440px]:not-sr-only">Setup </span>
          Correlation
        </>
      );
    case "sensitivity-optimizer":
      return (
        <span className="whitespace-nowrap">
          <span className="sr-only min-[1440px]:not-sr-only">Setup &amp; </span>
          <span className="sr-only xl:not-sr-only">Optimize</span>
          <span className="xl:hidden">Optimizer</span>
          <span className="sr-only">Optimizer</span>
        </span>
      );
    case "memory-reports":
      return (
        <>
          <span className="sr-only min-[1440px]:not-sr-only">Engineering </span>
          <span className="sr-only xl:not-sr-only">Memory &amp; </span>
          Reports
        </>
      );
    case "ai-engineer":
      return (
        <>
          AI Race<span className="sr-only min-[1440px]:not-sr-only"> Engineer</span>
        </>
      );
    default:
      return <>{fallback}</>;
  }
}

export default function Navbar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const navRef = useRef<HTMLDivElement>(null);
  const studioMode = isStudioModeEnabled();

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

  const isSolversActive = ALL_SOLVER_ITEMS.some(
    (item) => pathname === item.href || pathname.startsWith(item.href + "/")
  );
  const isValidationActive = VALIDATION_ITEMS.some(
    (item) => pathname === item.href || pathname.startsWith(item.href + "/")
  );

  const renderDropdownPanel = (
    id: string,
    heading: string,
    items: NavDropdownItem[],
    align: "left" | "right" = "left",
    scrollable = false
  ) => (
    <div
      id={id}
      className={`absolute ${align === "right" ? "right-0" : "left-0"} top-full mt-2 w-80 bg-[#0e0e12] border border-white/10 rounded-xl shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95 duration-100`}
    >
      <div className="px-2.5 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
        {heading}
      </div>
      <div
        className={`grid grid-cols-1 gap-1 ${
          scrollable ? "max-h-[380px] overflow-y-auto custom-scrollbar" : ""
        }`}
      >
        {items.map((item) => {
          const active = matchesRoute(pathname, item.href, item.aliases);
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
  );

  const renderStudioTool = (tool: StudioToolGroup) => {
    const Icon = STUDIO_ICONS[tool.icon];
    const active = isToolGroupActive(pathname, tool.routes);
    const menuKey = `studio-${tool.id}`;
    const dropdownId = `${menuKey}-dropdown`;

    if (tool.routes.length === 1) {
      return (
        <Link
          key={tool.id}
          href={tool.href}
          title={tool.label}
          aria-current={active ? "page" : undefined}
          className={`flex items-center gap-1.5 px-2 min-[1440px]:px-2.5 py-1.5 rounded-lg whitespace-nowrap transition-all ${
            active
              ? "text-white bg-white/[0.08] font-semibold border border-white/10 shadow-sm"
              : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
          }`}
        >
          <Icon size={13} className={`shrink-0 ${active ? "text-ansys-yellow" : "text-zinc-500"}`} />
          <span>
            <StudioToolLabel id={tool.id} fallback={tool.label} />
          </span>
        </Link>
      );
    }

    const isOpen = openMenu === menuKey;
    return (
      <div key={tool.id} className="relative shrink-0">
        <div
          className={`flex items-center rounded-lg whitespace-nowrap transition-all border ${
            active || isOpen
              ? "bg-white/[0.08] border-white/10 text-white shadow-sm"
              : "border-transparent text-zinc-400 hover:text-white hover:bg-white/[0.04]"
          }`}
        >
          <Link
            href={tool.href}
            title={tool.label}
            aria-current={active ? "page" : undefined}
            className="flex items-center gap-1.5 pl-2 min-[1440px]:pl-2.5 pr-1 py-1.5 font-medium whitespace-nowrap"
          >
            <Icon size={13} className={`shrink-0 ${active ? "text-ansys-yellow" : "text-zinc-500"}`} />
            <span className="whitespace-nowrap">
              <StudioToolLabel id={tool.id} fallback={tool.label} />
            </span>
          </Link>
          <button
            id={`${menuKey}-dropdown-btn`}
            type="button"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setOpenMenu((prev) => (prev === menuKey ? null : menuKey));
            }}
            aria-expanded={isOpen}
            aria-haspopup="true"
            aria-controls={dropdownId}
            aria-label={`${tool.label} routes`}
            className="pr-1.5 pl-0.5 py-1.5 text-zinc-400 hover:text-white"
            title={`${tool.label} tools`}
          >
            <ChevronDown
              size={11}
              className={`transition-transform duration-150 ${
                isOpen ? "rotate-180 text-ansys-yellow" : ""
              }`}
            />
          </button>
        </div>

        {isOpen &&
          renderDropdownPanel(
            dropdownId,
            tool.label,
            tool.routes,
            tool.dropdownAlign ?? "left"
          )}
      </div>
    );
  };

  return (
    <nav
      className="w-full h-[52px] bg-[rgba(10,10,12,0.95)] backdrop-blur-xl border-b border-white/[0.08] fixed top-0 z-50 px-4 sm:px-6 select-none"
      ref={navRef}
      aria-label="Main Navigation"
    >
      <div className="max-w-[1560px] h-full mx-auto flex items-center justify-between gap-2 xl:gap-4">
        {/* Left: Brand Logo & Mobile Drawer */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="lg:hidden">
            <MobileNav />
          </div>
          <Link href="/" className="text-gray-300 hover:text-white transition-colors flex items-center gap-2 group">
            <div className="w-7 h-7 rounded-lg bg-ansys-yellow/10 border border-ansys-yellow/30 flex items-center justify-center group-hover:border-ansys-yellow/60 transition-colors">
              <svg viewBox="0 0 24 24" fill="none" height="15" width="15" role="img" aria-label="SuspensionLab logo">
                <path
                  d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="#f2a900"
                  strokeWidth="2.2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
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

        {/* Center: Navigation (Studio Mode = 6 core visual tools; Standard = 7-stage executive workflow) */}
        {studioMode ? (
          <div
            data-studio-mode="true"
            className="hidden lg:flex items-center space-x-0.5 xl:space-x-1 text-[11px] min-[1440px]:text-xs font-medium"
          >
            {STUDIO_TOOLS.map(renderStudioTool)}
          </div>
        ) : (
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
              <div
                className={`flex items-center rounded-lg transition-all border ${
                  isSolversActive || openMenu === "solvers"
                    ? "bg-white/[0.08] border-white/10 text-white shadow-sm"
                    : "border-transparent text-zinc-400 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
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
                  <ChevronDown
                    size={11}
                    className={`transition-transform duration-150 ${
                      openMenu === "solvers" ? "rotate-180 text-ansys-yellow" : ""
                    }`}
                  />
                </button>
              </div>

              {openMenu === "solvers" &&
                renderDropdownPanel("solvers-dropdown", "Vehicle Physics Engines", ALL_SOLVER_ITEMS, "left", true)}
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
              <GitCompare
                size={13}
                className={
                  pathname === "/compare" || pathname === "/setup-sensitivity" ? "text-ansys-yellow" : "text-zinc-500"
                }
              />
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
              <Sparkles
                size={13}
                className={pathname === "/optimize" || pathname === "/ai-engineer" ? "text-ansys-yellow" : "text-zinc-500"}
              />
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
                <ChevronDown
                  size={11}
                  className={`transition-transform duration-150 ${
                    openMenu === "validation" ? "rotate-180 text-ansys-yellow" : "text-zinc-500"
                  }`}
                />
              </button>

              {openMenu === "validation" &&
                renderDropdownPanel("validation-dropdown", "Validation & Governance", VALIDATION_ITEMS, "left")}
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
        )}

        {/* Right Side: Docs & Pricing (standard) or highlighted Upgrade CTA (Studio Mode), Search & User Menu */}
        <div className="flex items-center gap-2.5 shrink-0">
          {studioMode ? (
            user?.plan !== "ENTERPRISE" && (
              <>
                <Link
                  href={STUDIO_PRICING_CTA.href}
                  aria-current={pathname === STUDIO_PRICING_CTA.href ? "page" : undefined}
                  className={`hidden md:inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
                    pathname === STUDIO_PRICING_CTA.href
                      ? "bg-ansys-yellow text-black ring-2 ring-ansys-yellow/50 shadow-[0_0_12px_rgba(242,169,0,0.35)]"
                      : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_10px_rgba(242,169,0,0.2)]"
                  }`}
                >
                  <Sparkles size={12} className="shrink-0" />
                  <span>{STUDIO_PRICING_CTA.label}</span>
                </Link>
                <div className="h-4 w-px bg-white/10 mx-0.5 hidden md:block" role="separator" aria-orientation="vertical" />
              </>
            )
          ) : (
            <>
              <Link
                href="/docs"
                className={`hidden md:inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  pathname === "/docs"
                    ? "text-white bg-white/[0.08]"
                    : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
                Docs
              </Link>
              <Link
                href="/pricing"
                className={`hidden md:inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  pathname === "/pricing"
                    ? "text-white bg-white/[0.08]"
                    : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
                Pricing
              </Link>
              <div className="h-4 w-px bg-white/10 mx-0.5 hidden md:block" role="separator" aria-orientation="vertical" />
            </>
          )}
          <GlobalSearchTrigger />
          <UserMenu />
        </div>
      </div>
    </nav>
  );
}
