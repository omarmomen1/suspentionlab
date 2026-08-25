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
];

export default function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close on route change
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Escape to close + body scroll lock
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      {/* Hamburger — visible only below lg */}
      <button
        onClick={() => setOpen(true)}
        className="lg:hidden p-1.5 text-gray-400 hover:text-white transition-colors"
        aria-label="Open navigation menu"
        aria-expanded={open}
      >
        <Menu size={18} />
      </button>

      {/* Drawer */}
      {open && (
        <div className="fixed inset-0 z-[60] lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
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
                onClick={() => setOpen(false)}
                className="p-1 text-gray-500 hover:text-white transition-colors"
                aria-label="Close navigation menu"
              >
                <X size={16} />
              </button>
            </div>

            <nav className="py-2">
              {SECTIONS.map((section) => (
                <div key={section.title} className="mb-2">
                  <div className="px-4 pt-3 pb-1 text-[9px] font-bold uppercase tracking-[0.18em] text-gray-600">
                    {section.title}
                  </div>
                  {section.links.map((link) => {
                    const active = pathname === link.href;
                    return (
                      <Link
                        key={link.href}
                        href={link.href}
                        className={`block px-4 py-2 text-sm transition-colors ${
                          active
                            ? "text-ansys-yellow bg-ansys-yellow/5 border-l-2 border-ansys-yellow"
                            : "text-gray-400 hover:text-white hover:bg-white/5 border-l-2 border-transparent"
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
