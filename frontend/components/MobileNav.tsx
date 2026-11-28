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
import { Menu, Sparkles, X } from "lucide-react";
import {
  STUDIO_PRICING_CTA,
  getNavGroups,
  isStudioModeEnabled,
  matchesRoute,
} from "../lib/navigation";

export default function MobileNav({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const pathname = usePathname();
  const studioMode = isStudioModeEnabled();
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

      {/* Drawer - kept mounted and visibility-toggled so the first open paints
          links immediately (no empty first paint while a fresh tree mounts) */}
      <div
          ref={drawerRef}
          className={`fixed inset-0 z-[60] lg:hidden transition-opacity duration-150 ${
            open ? "opacity-100" : "opacity-0 pointer-events-none invisible"
          }`}
          role="dialog"
          aria-modal={open ? "true" : undefined}
          aria-hidden={!open}
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
              <span className="text-xs font-bold text-white tracking-tight">
                Suspension<span className="text-signal">Lab</span>
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

            <nav
              className="py-2"
              aria-label="Mobile navigation links"
              data-studio-mode={studioMode ? "true" : undefined}
            >
              {(
                <div className="space-y-1">
                  <div className="px-4 pt-3 pb-1 text-xs font-bold uppercase tracking-[0.18em] text-signal">
                    Workspace
                  </div>
                  {getNavGroups().map((tool) => {
                    if (tool.routes.length === 1) {
                      const route = tool.routes[0];
                      const active = matchesRoute(pathname, route.href, route.aliases);
                      return (
                        <Link
                          key={tool.id}
                          href={route.href}
                          prefetch={true}
                          aria-current={active ? "page" : undefined}
                          className={`block px-4 py-2.5 text-sm transition-colors ${
                            active
                              ? "text-signal bg-signal/5 border-l-2 border-signal font-semibold"
                              : "text-gray-300 hover:text-white hover:bg-white/5 border-l-2 border-transparent"
                          }`}
                        >
                          <div>{tool.label}</div>
                          <div className="text-xs text-gray-400 mt-0.5 leading-tight">
                            {route.desc}
                          </div>
                        </Link>
                      );
                    }

                    return (
                      <div key={tool.id} className="pt-2">
                        <div className="px-4 pt-2 pb-1 text-xs font-bold uppercase tracking-[0.14em] text-gray-400">
                          {tool.label}
                        </div>
                        {tool.routes.map((route) => {
                          const active = matchesRoute(pathname, route.href, route.aliases);
                          return (
                            <Link
                              key={route.href}
                              href={route.href}
                              prefetch={true}
                              aria-current={active ? "page" : undefined}
                              className={`block pl-6 pr-4 py-2 text-sm transition-colors ${
                                active
                                  ? "text-signal bg-signal/5 border-l-2 border-signal font-semibold"
                                  : "text-gray-300 hover:text-white hover:bg-white/5 border-l-2 border-transparent"
                              }`}
                            >
                              {route.label}
                            </Link>
                          );
                        })}
                      </div>
                    );
                  })}
                  <div className="px-4 pt-4 pb-2 border-t border-white/10 mt-3">
                    <Link
                      href={STUDIO_PRICING_CTA.href}
                      prefetch={true}
                      aria-current={pathname === STUDIO_PRICING_CTA.href ? "page" : undefined}
                      className={`flex items-center justify-center gap-2 w-full px-3 py-2.5 rounded-lg text-xs font-bold transition-colors border border-signal ${
                        pathname === STUDIO_PRICING_CTA.href
                          ? "bg-signal text-carbon"
                          : "bg-signal text-carbon hover:bg-[#d6f56e]"
                      }`}
                    >
                      <Sparkles size={13} className="shrink-0" />
                      <span>{STUDIO_PRICING_CTA.mobileLabel}</span>
                    </Link>
                    <p className="text-xs text-gray-400 text-center mt-1.5">
                      {STUDIO_PRICING_CTA.subtitle}
                    </p>
                  </div>
                </div>
              )}
            </nav>
          </div>
        </div>
    </>
  );
}
