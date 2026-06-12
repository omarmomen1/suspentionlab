"use client";
import { useState } from "react";
import { Users, Loader2, Link as LinkIcon, Check } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import PlanGate from "./PlanGate";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ShareSessionProps {
  currentParams: Record<string, any>;
  vehicleType: "QUARTER_CAR" | "FULL_CAR";
}

export default function ShareSession({ currentParams, vehicleType }: ShareSessionProps) {
  const { authHeader } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [sessionUrl, setSessionUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const createSession = async () => {
    setIsCreating(true);
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({
          params_snapshot: currentParams,
        }),
      });

      if (!res.ok) throw new Error("Failed to create session");

      const data = await res.json();
      const baseUrl = window.location.origin + window.location.pathname;
      setSessionUrl(`${baseUrl}?session=${data.session_id}`);
    } catch (err) {
      console.error(err);
      alert("Failed to create collaboration session.");
    } finally {
      setIsCreating(false);
    }
  };

  const copyLink = () => {
    if (sessionUrl) {
      navigator.clipboard.writeText(sessionUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (sessionUrl) {
    return (
      <PlanGate required="ENTERPRISE">
        <button
          onClick={copyLink}
          className="px-3 py-1.5 bg-[#00aeff]/10 border border-[#00aeff]/50 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors text-[#00aeff]"
        >
          {copied ? <Check size={13} /> : <LinkIcon size={13} />}
          {copied ? "Copied Link!" : "Copy Session Link"}
        </button>
      </PlanGate>
    );
  }

  return (
    <PlanGate required="ENTERPRISE">
      <button
        onClick={createSession}
        disabled={isCreating}
        className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] hover:border-[#00aeff]/50 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40"
      >
        {isCreating ? (
          <Loader2 size={13} className="text-[#00aeff] animate-spin" />
        ) : (
          <Users size={13} className="text-[#00aeff]" />
        )}
        Live Sync
      </button>
    </PlanGate>
  );
}
