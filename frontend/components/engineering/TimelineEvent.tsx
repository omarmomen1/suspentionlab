"use client";

import React from "react";
import { Hash, Clock, User, ShieldCheck, CheckCircle2 } from "lucide-react";

interface TimelineEventProps {
  event: string;
  actor: string;
  timestamp: string;
  hash: string;
  description?: string;
  metadata?: Record<string, any>;
  entityType?: string;
  entityId?: string;
  onViewEvidenceGraph?: (entityType: string, entityId: string) => void;
  className?: string;
}

export default function TimelineEvent({
  event,
  actor,
  timestamp,
  hash,
  description,
  metadata,
  entityType,
  entityId,
  onViewEvidenceGraph,
  className = "",
}: TimelineEventProps) {
  return (
    <div className={`p-4 rounded-2xl bg-[#111116] border border-white/[0.08] font-mono text-xs space-y-2 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-ansys-yellow" />
          <span className="font-bold text-white text-sm font-sans">{event}</span>
        </div>
        <div className="flex items-center gap-1 text-[11px] text-gray-400">
          <Clock size={11} />
          <span>{new Date(timestamp).toLocaleTimeString()}</span>
        </div>
      </div>

      {description && <p className="text-xs text-gray-300 font-sans">{description}</p>}

      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-gray-500 pt-2 border-t border-white/[0.06]">
        <div className="flex items-center gap-1">
          <User size={11} /> <span>Actor:</span> <span className="text-gray-400">{actor}</span>
        </div>
        <div className="flex items-center gap-1 truncate max-w-[200px]" title={hash}>
          <Hash size={11} /> <span>Hash:</span> <span className="text-gray-400 font-mono truncate">{hash.slice(0, 16)}</span>
        </div>
        {onViewEvidenceGraph && (entityType || entityId) && (
          <button
            onClick={() => onViewEvidenceGraph(entityType || "", entityId || "")}
            className="flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 hover:bg-rose-500/20 text-[10px] font-sans font-medium transition-colors"
            title="View in Evidence Graph"
          >
            <ShieldCheck size={10} />
            <span>Provenance Graph</span>
          </button>
        )}
      </div>
    </div>
  );
}
