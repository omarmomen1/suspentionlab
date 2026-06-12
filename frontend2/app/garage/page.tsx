"use client";
import { useState, useEffect, useMemo } from "react";
import { Car, Search, Trash2, Plus, ArrowRight, X, Layers } from "lucide-react";
import Link from "next/link";

import { useAuth } from "../../contexts/AuthContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface VehicleProfile {
  id: string;
  name: string;
  vehicle_type: string;
  params: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

type Toast = { msg: string; type: "success" | "error" };

// Vehicle type metadata
const VEHICLE_META: Record<string, { label: string; color: string; href: string }> = {
  QUARTER_CAR: { label: "Quarter Car (2-DOF)", color: "text-ansys-yellow",   href: "/quarter-car" },
  HALF_CAR:    { label: "Half Car (4-DOF)",    color: "text-[#0af]",          href: "/half-car"    },
  FULL_CAR:    { label: "Full Car (7-DOF)",    color: "text-[#bf5af2]",       href: "/full-car"    },
};

function SkeletonCard() {
  return (
    <div className="bg-[#111113] border border-[#1e1e1e] rounded-xl p-5 flex flex-col h-[280px] animate-pulse">
      <div className="h-5 bg-[#222] rounded w-3/4 mb-2" />
      <div className="h-3 bg-[#1a1a1a] rounded w-1/2 mb-4" />
      <div className="flex-1 bg-[#0d0d0d] rounded-lg" />
      <div className="h-4 bg-[#1a1a1a] rounded w-1/3 mt-4" />
    </div>
  );
}

export default function GarageDashboard() {
  const { authHeader } = useAuth();
  const [profiles,     setProfiles]     = useState<VehicleProfile[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [searchQuery,  setSearchQuery]  = useState("");
  const [filterType,   setFilterType]   = useState("ALL");
  const [toast,        setToast]        = useState<Toast | null>(null);
  const [deletingId,   setDeletingId]   = useState<string | null>(null);

  const showToast = (msg: string, type: Toast["type"]) => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchProfiles = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/profiles`, {
        headers: authHeader(),
      });
      if (res.ok) setProfiles(await res.json());
      else showToast("Failed to load profiles — check API connection", "error");
    } catch {
      showToast("Cannot reach the API server", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProfiles(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const deleteProfile = async (id: string) => {
    setDeletingId(id);
    try {
      const res = await fetch(`${API_BASE}/profiles/${id}`, {
        method:  "DELETE",
        headers: authHeader(),
      });
      if (res.ok) {
        setProfiles((prev) => prev.filter((p) => p.id !== id));
        showToast("Profile deleted", "success");
      } else {
        showToast("Failed to delete profile", "error");
      }
    } catch {
      showToast("Delete request failed", "error");
    } finally {
      setDeletingId(null);
    }
  };

  // Live search + type filter — computed, no extra state needed
  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return profiles.filter((p) => {
      const matchesType  = filterType === "ALL" || p.vehicle_type === filterType;
      const matchesQuery = !q || p.name.toLowerCase().includes(q) || p.vehicle_type.toLowerCase().includes(q);
      return matchesType && matchesQuery;
    });
  }, [profiles, searchQuery, filterType]);

  const typeCounts = useMemo(() => {
    const c: Record<string, number> = { ALL: profiles.length };
    profiles.forEach((p) => { c[p.vehicle_type] = (c[p.vehicle_type] ?? 0) + 1; });
    return c;
  }, [profiles]);

  return (
    <div className="h-full flex flex-col pt-[44px]">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl
          shadow-2xl border text-sm font-medium transition-all
          ${toast.type === "success"
            ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300"
            : "bg-[#1f0a0a] border-red-800/50 text-red-300"}`}>
          {toast.msg}
          <button onClick={() => setToast(null)} className="opacity-50 hover:opacity-100 ml-1">
            <X size={13} />
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto custom-scrollbar p-6 md:p-10 max-w-7xl mx-auto w-full">

        {/* Header */}
        <div className="flex items-start justify-between mb-8 gap-6">
          <div className="flex flex-col">
            <span className="text-[10px] font-bold tracking-[0.2em] text-ansys-yellow uppercase mb-1">
              Fleet Management
            </span>
            <h1 className="text-4xl font-semibold tracking-tight text-white">Vehicle Garage</h1>
            <p className="text-gray-500 text-sm mt-1.5">
              {profiles.length} saved configuration{profiles.length !== 1 ? "s" : ""} · Click any card to load it into the simulator
            </p>
          </div>

          {/* Search + filter */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search setups…"
                className="bg-[#111113] border border-[#1e1e1e] text-sm rounded-xl pl-9 pr-9 py-2
                  text-white focus:outline-none focus:border-ansys-yellow/60 focus:ring-1
                  focus:ring-ansys-yellow/15 w-64 placeholder:text-gray-700 transition-all"
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-300">
                  <X size={13} />
                </button>
              )}
            </div>
            <Link href="/quarter-car"
              className="flex items-center gap-1.5 px-4 py-2 bg-ansys-yellow text-black text-xs font-bold
                rounded-xl hover:brightness-110 transition-all shadow-[0_0_16px_rgba(242,169,0,0.15)]">
              <Plus size={14} /> New Setup
            </Link>
          </div>
        </div>

        {/* Type filter pills */}
        {!loading && profiles.length > 0 && (
          <div className="flex gap-2 mb-6">
            {["ALL", "QUARTER_CAR", "HALF_CAR", "FULL_CAR"].map((type) => {
              const count = typeCounts[type] ?? 0;
              if (type !== "ALL" && count === 0) return null;
              const meta = VEHICLE_META[type];
              return (
                <button key={type} onClick={() => setFilterType(type)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all border ${
                    filterType === type
                      ? "bg-ansys-yellow text-black border-ansys-yellow"
                      : "bg-[#111113] border-[#1e1e1e] text-gray-500 hover:text-gray-300"
                  }`}>
                  {meta?.label ?? "All Types"} <span className="opacity-60 ml-1">({count})</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map((i) => <SkeletonCard key={i} />)}
          </div>
        )}

        {/* Empty state */}
        {!loading && profiles.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64
            border border-dashed border-[#252525] rounded-xl bg-[#0d0d0f] text-gray-500">
            <Car size={48} className="mb-4 opacity-20" />
            <h3 className="text-xl font-medium text-white mb-2">Your Garage is Empty</h3>
            <p className="mb-6 text-sm text-center max-w-sm">
              Save a vehicle configuration from any simulation module to store and reload it here.
            </p>
            <Link href="/quarter-car"
              className="px-4 py-2 bg-ansys-yellow text-black font-bold rounded-xl flex items-center gap-2 hover:brightness-110 transition-all">
              <Plus size={16} /> Create Your First Setup
            </Link>
          </div>
        )}

        {/* No search results */}
        {!loading && profiles.length > 0 && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-gray-600">
            <Layers size={40} className="mb-3 opacity-30" />
            <p className="text-sm">No profiles match &quot;<span className="text-gray-400">{searchQuery}</span>&quot;</p>
            <button onClick={() => { setSearchQuery(""); setFilterType("ALL"); }}
              className="mt-3 text-xs text-ansys-yellow hover:underline">
              Clear filters
            </button>
          </div>
        )}

        {/* Profile cards grid */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filtered.map((p) => {
              const meta = VEHICLE_META[p.vehicle_type] ?? { label: p.vehicle_type, color: "text-gray-400", href: "/" };
              return (
                <div key={p.id}
                  className="bg-[#111113] border border-[#1e1e1e] rounded-xl p-5
                    hover:border-[#333] transition-all group flex flex-col h-[280px]">
                  <div className="flex justify-between items-start mb-3">
                    <div className="min-w-0 pr-2">
                      <h3 className="text-base font-bold text-white mb-0.5 truncate">{p.name}</h3>
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${meta.color}`}>
                        {meta.label}
                      </span>
                    </div>
                    <button
                      onClick={() => deleteProfile(p.id)}
                      disabled={deletingId === p.id}
                      className="text-gray-600 hover:text-red-500 opacity-0 group-hover:opacity-100
                        transition-all p-1 rounded hover:bg-red-950/30 shrink-0 disabled:opacity-30">
                      {deletingId === p.id
                        ? <div className="w-4 h-4 border border-red-500 border-t-transparent rounded-full animate-spin" />
                        : <Trash2 size={14} />}
                    </button>
                  </div>

                  {/* Params preview */}
                  <div className="flex-1 bg-black/40 rounded-lg p-3 border border-white/5 overflow-hidden mb-3">
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                      {Object.entries(p.params).slice(0, 8).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-1 min-w-0">
                          <span className="text-[10px] text-gray-600 truncate">{k}:</span>
                          <span className="text-[10px] text-gray-300 font-mono shrink-0">{String(v)}</span>
                        </div>
                      ))}
                      {Object.keys(p.params).length > 8 && (
                        <div className="col-span-2 text-[9px] text-gray-700 text-center mt-1 italic">
                          +{Object.keys(p.params).length - 8} more parameters
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-700">
                      {new Date(p.updated_at).toLocaleDateString("en-GB", {
                        day: "numeric", month: "short", year: "numeric",
                      })}
                    </span>
                    <Link
                      href={`${meta.href}?load=${p.id}`}
                      className="flex items-center gap-1 text-xs font-bold text-gray-400
                        hover:text-ansys-yellow transition-colors">
                      Load Setup <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
