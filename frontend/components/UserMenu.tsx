"use client";
import { useState, useRef, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import Link from "next/link";
import { User, Settings, LogOut, CreditCard, Key, ChevronDown } from "lucide-react";

const PLAN_STYLES: Record<string, string> = {
  FREE:       "text-gray-500 bg-[#1e1e1e]",
  PRO:        "text-ansys-yellow bg-ansys-yellow/10",
  ENTERPRISE: "text-purple-400 bg-purple-900/20",
};

export default function UserMenu() {
  const { user, loading, logout } = useAuth();
  const [open, setOpen]           = useState(false);
  const ref                       = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (loading) {
    return <div className="w-7 h-7 rounded-full bg-[#252525] animate-pulse" suppressHydrationWarning />;
  }

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Link href="/auth/login"
          className="text-xs text-gray-400 hover:text-white transition-colors font-medium">
          Sign In
        </Link>
        <Link href="/auth/register"
          className="text-xs px-3 py-1.5 bg-ansys-yellow text-black font-bold rounded-lg
            hover:brightness-110 transition-all">
          Get Started
        </Link>
      </div>
    );
  }

  const initials = (user.name || user.email || "?")
    .split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const planBadge = PLAN_STYLES[user.plan] ?? PLAN_STYLES.FREE;

  return (
    <div className="relative" ref={ref} suppressHydrationWarning>
      <button onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 hover:opacity-80 transition-opacity">
        <div className="w-7 h-7 rounded-full bg-ansys-yellow/20 border border-ansys-yellow/30
          flex items-center justify-center text-[10px] font-bold text-ansys-yellow">
          {initials}
        </div>
        <ChevronDown size={11} className={`text-gray-600 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-[#0d0d0f] border border-[#252525]
          rounded-xl shadow-2xl overflow-hidden z-50">
          {/* User info */}
          <div className="px-4 py-3 border-b border-[#1e1e1e]">
            <p className="text-xs font-semibold text-white truncate">{user.name || user.email}</p>
            <p className="text-[10px] text-gray-600 truncate mt-0.5">{user.email}</p>
            <span className={`mt-1.5 inline-flex text-[9px] font-bold uppercase tracking-wider
              px-2 py-0.5 rounded-full ${planBadge}`}>
              {user.plan}
            </span>
          </div>

          {/* Menu items */}
          <div className="py-1">
            {[
              { href: "/settings",          icon: Settings,    label: "Settings"       },
              { href: "/settings#billing",  icon: CreditCard,  label: "Billing & Plan" },
              { href: "/settings#api-keys", icon: Key,         label: "API Keys"       },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} onClick={() => setOpen(false)}
                  className="flex items-center gap-2.5 px-4 py-2 text-xs text-gray-400
                    hover:text-white hover:bg-[#161618] transition-colors">
                  <Icon size={13} /> {item.label}
                </Link>
              );
            })}
          </div>

          <div className="border-t border-[#1e1e1e] py-1">
            <button onClick={() => { logout(); setOpen(false); }}
              className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-red-500
                hover:bg-red-950/20 transition-colors">
              <LogOut size={13} /> Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
