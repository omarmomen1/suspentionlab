"use client";

/**
 * components/MobileNav.tsx (P0-UX-01)
 * Slide-out navigation drawer for screens below lg (1024px).
 * Categorized sections, Escape-to-close, backdrop click-to-close,
 * body scroll lock while open.
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

const SECTIONS: Array<{ title: string; links: Array<{ href: string; label: string }> }> = [
  {
    title: "Hypothesis & Decisions",
    links: [
      { href: "/experiment", label: "⚗ 1-Click Experiment" },
      { href: "/compare", label: "⇄ Deep Compare (A vs B)" },
      { href: "/optimize", label: "✦ Pareto Optimizer" },
      { href: "/correlation", label: "⚡ Correlation Cockpit" },
      { href: "/timeline", label: "⏱ Timeline & Decisions" },
      { href: "/cae", label: "⛭ CAE Interoperability Hub" },
    ],
  },
  {
    title: "Simulation",
    links: [
      { href: "/quarter-car", label: "Quarter Car" },
      { href: "/half-car", label: "Half Car" },
      { href: "/full-car", label: "Full Car" },
      { href: "/active", label: "Active" },
      { href: "/handling", label: "Handling" },
    ],
  },
  {
    title: "Analysis",
    links: [
      { href: "/kinematics", label: "Kinematics" },
      { href: "/lap-sim", label: "Lap Sim" },
      { href: "/setup-sensitivity", label: "Setup Sensitivity" },
      { href: "/yaw-dynamics", label: "Yaw / MMM" },
      { href: "/digital-twin", label: "Digital Twin" },
      { href: "/sensitivity", label: "Sensitivity" },
      { href: "/nvh", label: "NVH" },
      { href: "/durability", label: "Durability" },
    ],
  },
  {
    title: "Workspace",
    links: [
      { href: "/ai-engineer", label: "✦ AI Engineer" },
      { href: "/garage", label: "Garage" },
      { href: "/pricing", label: "Pricing" },
      { href: "/docs", label: "Docs" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/auth/login", label: "Sign In" },
      { href: "/auth/register", label: "Create Account" },
      { href: "/settings", label: "Settings" },
    ],
  },
];

export default function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const drawerRef = React.useRef<HTMLDivElement>(null);
  const closeButtonRef = React.useRef<HTMLButtonElement>(null);

  // Close on route change
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Focus trap, Escape to close, and body scroll lock
  useEffect(() => {
    if (!open) return;

    // Focus close button on open
    setTimeout(() => closeButtonRef.current?.focus(), 30);
    document.body.style.overflow = "hidden";

    const drawer = drawerRef.current;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        return;
      }
      if (e.key === "Tab" && drawer) {
        const focusables = Array.from(
          drawer.querySelectorAll<HTMLElement>(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
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

    const triggerEl = triggerRef.current;
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
      triggerEl?.focus();
    };
  }, [open]);

  return (
    <>
      {/* Hamburger — visible only below lg */}
      <button
        ref={triggerRef}
        onClick={() => setOpen(true)}
        className="lg:hidden p-1.5 text-gray-400 hover:text-white transition-colors"
        aria-label="Open navigation menu"
        aria-expanded={open}
      >
        <Menu size={18} />
      </button>

      {/* Drawer */}
      {open && (
        <div
          ref={drawerRef}
          className="fixed inset-0 z-[60] lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          {/* Panel */}
          <div className="absolute left-0 top-0 h-full w-[280px] bg-[#0d0d0f] border-r border-white/10 shadow-2xl overflow-y-auto custom-scrollbar">
            <div className="flex items-center justify-between px-4 h-[44px] border-b border-white/8">
              <span className="text-[11px] font-bold text-white tracking-tight">
                Suspension<span className="text-ansys-yellow">Lab</span>
              </span>
              <button
                ref={closeButtonRef}
                onClick={() => setOpen(false)}
                className="p-1 text-gray-400 hover:text-white transition-colors"
                aria-label="Close navigation menu"
              >
                <X size={16} />
              </button>
            </div>

            <nav className="py-2" aria-label="Mobile navigation links">
              {SECTIONS.map((section) => (
                <div key={section.title} className="mb-2">
                  <div className="px-4 pt-3 pb-1 text-[9px] font-bold uppercase tracking-[0.18em] text-gray-400">
                    {section.title}
                  </div>
                  {section.links.map((link) => {
                    const active = pathname === link.href;
                    return (
                      <Link
                        key={link.href}
                        href={link.href}
                        prefetch={true}
                        aria-current={active ? "page" : undefined}
                        className={`block px-4 py-2 text-sm transition-colors ${
                          active
                            ? "text-ansys-yellow bg-ansys-yellow/5 border-l-2 border-ansys-yellow font-semibold"
                            : "text-gray-300 hover:text-white hover:bg-white/5 border-l-2 border-transparent"
                        }`}
                      >
                        {link.label}
                      </Link>
                    );
                  })}
                </div>
              ))}
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
