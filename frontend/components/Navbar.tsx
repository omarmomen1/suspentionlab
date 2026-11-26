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
  STUDIO_PRICING_CTA,
  getNavGroups,
  isStudioModeEnabled,
  isToolGroupActive,
  matchesRoute,
  type NavDropdownItem,
  type StudioIconKey,
  type StudioToolGroup,
} from "../lib/navigation";

const STUDIO_ICONS: Record<StudioIconKey, LucideIcon> = {
  overview: Compass,
  studios: Wrench,
  apexsim: Car,
  telemetry: Activity,
  optimize: Sliders,
  reports: FileText,
  kinematics: Compass,
  quarter_car: Activity,
  full_car: Car,
  correlation: GitCompare,
  optimizer: Sliders,
  memory: FileText,
  ai: Sparkles,
};

function StudioToolLabel({ fallback }: { id: string; fallback: string }) {
  return <span className="whitespace-nowrap">{fallback}</span>;
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
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg whitespace-nowrap transition-all text-xs shrink-0 ${
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
            className="flex items-center gap-1.5 pl-2 pr-0.5 py-1.5 font-medium whitespace-nowrap text-xs"
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

        {/* Center: V2 workspace navigation (7 groups, fits 1024px+; dropdowns overflow-visible) */}
        <div
          data-nav-version="v2"
          data-studio-mode={studioMode ? "true" : undefined}
          className="hidden lg:flex flex-1 min-w-0 items-center justify-center gap-0.5 xl:gap-1.5 px-1 xl:px-2 text-[11px] xl:text-xs font-medium overflow-visible"
        >
          {getNavGroups().map(renderStudioTool)}
        </div>

        {/* Right Side: Docs & Pricing (standard) or highlighted Upgrade CTA (Studio Mode), Search & User Menu */}
        <div className="flex items-center gap-2.5 shrink-0">
          <Link
            href="/docs"
            className={`hidden xl:inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
              pathname === "/docs"
                ? "text-white bg-white/[0.08]"
                : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
            }`}
          >
            Docs
          </Link>
          {user?.plan !== "ENTERPRISE" && (
            <Link
              href={STUDIO_PRICING_CTA.href}
              aria-current={pathname === STUDIO_PRICING_CTA.href ? "page" : undefined}
              className={`hidden md:inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold transition-colors whitespace-nowrap border ${
                pathname === STUDIO_PRICING_CTA.href
                  ? "bg-[#C8F04B] text-[#0C0F12] border-[#C8F04B]"
                  : "bg-[#C8F04B] text-[#0C0F12] border-[#C8F04B] hover:bg-[#d6f56e]"
              }`}
            >
              <span>{STUDIO_PRICING_CTA.label}</span>
            </Link>
          )}
          <div className="h-4 w-px bg-white/10 mx-0.5 hidden md:block" role="separator" aria-orientation="vertical" />
          <GlobalSearchTrigger />
          <UserMenu />
        </div>
      </div>
    </nav>
  );
}
