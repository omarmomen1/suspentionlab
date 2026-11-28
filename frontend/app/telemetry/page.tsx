"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Gauge,
  RefreshCw,
  ShieldAlert,
  Upload,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { isSampleTelemetryFilename } from "../../lib/sampleTelemetry";

/**
 * Wave 15 item 3: the telemetry home.
 *
 * Upload a session (same /telemetry/analyse contract the correlation cockpit
 * uses), then reopen it later and read every channel, QA row, health verdict and
 * lap segment the analysis produced. Nothing here is inferred: the tables are
 * the stored /analyse payload rendered as-is.
 */

interface SessionRow {
  session_id: string;
  name: string;
  filename: string;
  uploaded_at: string;
  pipeline_status: string;
  n_samples: number | null;
  duration_s: number | null;
  sample_rate_hz: number | null;
  n_channels: number;
  n_segments: number;
  health_status: string | null;
  blocking_reasons: string[];
}

function fmt(value: unknown, digits = 2, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toFixed(digits);
}

function StatusPill({ status }: { status?: string | null }) {
  const ok = status === "ACCEPTED";
  const warn = status === "ACCEPTED_WITH_WARNINGS";
  const cls = ok
    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
    : warn
    ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
    : "bg-rose-500/15 text-rose-300 border-rose-500/40";
  return (
    <span className={`px-2 py-0.5 rounded border text-[10px] font-bold font-mono ${cls}`}>
      {status || "UNKNOWN"}
    </span>
  );
}

export default function TelemetrySessionsPage() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [sessionName, setSessionName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSessions = useCallback(async () => {
    setLoadingList(true);
    try {
      const res = await apiFetch("/api/v1/telemetry/sessions");
      if (res.status === 401) {
        setSessions([]);
        setListError(null);
        return;
      }
      if (!res.ok) {
        throw new Error(`Could not load sessions (HTTP ${res.status})`);
      }
      const body = await res.json();
      setSessions(Array.isArray(body?.sessions) ? body.sessions : []);
      setListError(null);
    } catch (err: any) {
      setListError(err?.message || "Could not load sessions.");
    } finally {
      setLoadingList(false);
    }
  }, []);

  const openSession = useCallback(async (sessionId: string) => {
    setSelectedId(sessionId);
    setLoadingDetail(true);
    setDetailError(null);
    try {
      const res = await apiFetch(`/api/v1/telemetry/sessions/${encodeURIComponent(sessionId)}`);
      if (res.status === 401) {
        setDetail(null);
        setDetailError("Sign in to view stored session details.");
        return;
      }
      if (!res.ok) {
        throw new Error(`Could not open session (HTTP ${res.status})`);
      }
      setDetail(await res.json());
    } catch (err: any) {
      setDetail(null);
      setDetailError(err?.message || "Could not open session.");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setUploadError(`Rejected "${file.name}": only CSV telemetry logs are accepted.`);
      return;
    }
    setUploadError(null);
    setUploadNote(null);
    setIsUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (sessionName.trim()) {
        form.append("session_name", sessionName.trim());
      }
      const res = await apiFetch("/api/v1/telemetry/analyse", { method: "POST", body: form });
      if (res.status === 401) {
        setUploadError("Sign in to upload and store telemetry sessions.");
        return;
      }
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const reasons: string[] = body?.detail?.blocking_reasons ?? [];
        setUploadError(
          reasons.length > 0
            ? `Rejected "${file.name}": ${reasons.join("; ")}`
            : body?.detail?.error || body?.detail || `Analysis failed (HTTP ${res.status}).`
        );
        return;
      }
      setUploadNote(
        isSampleTelemetryFilename(file.name)
          ? `Analysed "${file.name}" - this is a bundled sample file, not your car.`
          : `Analysed and stored "${file.name}".`
      );
      await loadSessions();
      if (body?.session_id) {
        await openSession(body.session_id);
      }
    } catch (err: any) {
      setUploadError(err?.message || "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  };

  const channelRows = useMemo(() => {
    const map = detail?.channel_map ?? {};
    return Object.entries(map).map(([key, info]: [string, any]) => ({
      key,
      standard_key: info?.standard_key ?? key,
      raw_name: info?.raw_name ?? "-",
      unit: info?.inferred_unit ?? "-",
      confidence: info?.confidence,
      column_index: info?.column_index,
      warnings: info?.warnings ?? [],
    }));
  }, [detail]);

  const healthRows = useMemo(() => {
    const channels = detail?.health?.channels ?? {};
    return Object.entries(channels).map(([key, h]: [string, any]) => ({
      key,
      channel_name: h?.channel_name ?? key,
      units: h?.units ?? "-",
      quality_state: h?.quality_state ?? "UNKNOWN",
      sample_count: h?.sample_count,
      sample_rate_hz: h?.sample_rate_hz,
      missing_pct: h?.missing_pct,
      min_val: h?.min_val,
      max_val: h?.max_val,
      mean_val: h?.mean_val,
      std_val: h?.std_val,
      flatline: h?.flatline_detected,
      spikes: h?.spike_count,
      warnings: h?.warnings ?? [],
      blockers: h?.blockers ?? [],
    }));
  }, [detail]);

  const qa = detail?.qa;
  const summary = detail?.summary;
  const segments: any[] = Array.isArray(detail?.segments) ? detail.segments : [];

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 p-6 space-y-6">
      <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono uppercase tracking-wider">
            <Database className="w-3.5 h-3.5" />
            Telemetry
          </div>
          <h1 className="text-2xl font-bold text-neutral-100 mt-1">Sessions</h1>
          <p className="text-sm text-neutral-400 mt-1 max-w-2xl">
            Every uploaded session keeps its channel map, QA rows, health verdict and lap segments.
            Open one to inspect all of it.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => void loadSessions()}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold bg-neutral-900 border border-neutral-800 hover:border-neutral-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingList ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <Link
            href="/correlation"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold bg-neutral-900 border border-neutral-800 hover:border-neutral-700"
          >
            Correlation cockpit
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </header>

      {/* Upload - same /telemetry/analyse contract the correlation cockpit uses */}
      <section className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-neutral-100">
          <Upload className="w-4 h-4 text-cyan-400" />
          Upload a telemetry session
        </div>
        <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
          <input
            type="text"
            value={sessionName}
            onChange={(e) => setSessionName(e.target.value)}
            placeholder="Session label (optional)"
            className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white"
          >
            <FileSpreadsheet className="w-4 h-4" />
            {isUploading ? "Analysing..." : "Choose CSV and analyse"}
          </button>
          <input
            type="file"
            accept=".csv"
            ref={fileInputRef}
            className="hidden"
            onChange={handleUpload}
            data-testid="telemetry-upload-input"
          />
        </div>
        {uploadError && (
          <p className="text-xs text-rose-400 flex items-start gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            {uploadError}
          </p>
        )}
        {uploadNote && (
          <p className="text-xs text-emerald-400 flex items-start gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            {uploadNote}
          </p>
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Session list */}
        <section className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-4 space-y-3 lg:col-span-1">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-neutral-100">Your sessions</h2>
            <span className="text-[10px] font-mono text-neutral-500">{sessions.length} stored</span>
          </div>
          {listError && <p className="text-xs text-rose-400">{listError}</p>}
          {!listError && sessions.length === 0 && !loadingList && (
            <p className="text-xs text-neutral-500">
              No sessions yet. Upload a CSV above to inspect every channel and QA row.
            </p>
          )}
          <ul className="space-y-2">
            {sessions.map((row) => (
              <li key={row.session_id}>
                <button
                  onClick={() => void openSession(row.session_id)}
                  className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                    selectedId === row.session_id
                      ? "border-cyan-500/60 bg-cyan-500/10"
                      : "border-neutral-800 bg-neutral-950 hover:border-neutral-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-neutral-100 truncate">{row.name}</span>
                    <StatusPill status={row.health_status || row.pipeline_status} />
                  </div>
                  <div className="text-[10px] font-mono text-neutral-500 mt-1 flex flex-wrap gap-x-3">
                    <span>{row.n_channels} channels</span>
                    <span>{fmt(row.duration_s, 1)} s</span>
                    <span>{row.n_segments} segments</span>
                    <span>{row.uploaded_at}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {/* Session detail */}
        <section className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-4 space-y-4 lg:col-span-2">
          {!selectedId && (
            <p className="text-sm text-neutral-500">
              Select a session to see its channel map, QA, health and lap segments.
            </p>
          )}
          {loadingDetail && <p className="text-xs text-neutral-400">Loading session...</p>}
          {detailError && <p className="text-xs text-rose-400">{detailError}</p>}

          {detail && !loadingDetail && (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-sm font-semibold text-neutral-100">{detail.session_name || detail.name}</h2>
                <StatusPill status={detail.pipeline_status} />
                <span className="text-[10px] font-mono text-neutral-500">{detail.session_id}</span>
              </div>

              {Array.isArray(detail.blocking_reasons) && detail.blocking_reasons.length > 0 && (
                <div className="text-xs text-rose-300 flex items-start gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  {detail.blocking_reasons.join("; ")}
                </div>
              )}

              {/* Summary */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Samples", value: summary?.n_samples ?? "-" },
                  { label: "Duration (s)", value: fmt(summary?.duration_s, 1) },
                  { label: "Rate (Hz)", value: fmt(summary?.sample_rate_hz, 1) },
                  { label: "Channels", value: channelRows.length },
                  { label: "Mean speed (m/s)", value: fmt(summary?.mean_speed_ms, 2) },
                  { label: "Peak lat (g)", value: fmt(summary?.peak_lat_g, 2) },
                  { label: "Peak long (g)", value: fmt(summary?.peak_long_g, 2) },
                  { label: "Peak vert (g)", value: fmt(summary?.peak_vert_g, 2) },
                ].map((item) => (
                  <div key={item.label} className="bg-neutral-950 border border-neutral-800 rounded-lg p-2.5">
                    <div className="text-[10px] uppercase tracking-wide text-neutral-500">{item.label}</div>
                    <div className="text-sm font-mono font-semibold text-neutral-100 mt-0.5">{item.value}</div>
                  </div>
                ))}
              </div>

              {/* QA */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-2 flex items-center gap-1.5">
                  <Gauge className="w-3.5 h-3.5" /> QA
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] font-mono">
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-2">
                    Dropout intervals: {qa?.dropout_intervals ?? "-"}
                  </div>
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-2">
                    Dead sensors: {(qa?.dead_channels ?? []).join(", ") || "none"}
                  </div>
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-2">
                    Rate mismatch: {fmt(qa?.rate_mismatch_pct, 2)}%
                  </div>
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-2">
                    Missing channels: {(qa?.channels_missing ?? []).join(", ") || "none"}
                  </div>
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-2">
                    Warnings: {qa?.total_warnings ?? "-"}
                  </div>
                  <div className="bg-neutral-950 border border-neutral-800 rounded p-2">
                    Rate jitter: {fmt(detail?.health?.rate_jitter_pct, 2)}%
                  </div>
                </div>
              </div>

              {/* Channel map with aliases */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-2 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5" /> Channel map ({channelRows.length})
                </h3>
                <div className="overflow-x-auto border border-neutral-800 rounded-lg">
                  <table className="w-full text-[11px] font-mono">
                    <thead className="bg-neutral-950 text-neutral-500">
                      <tr>
                        <th className="text-left px-2 py-1.5">Standard key</th>
                        <th className="text-left px-2 py-1.5">Raw column (alias)</th>
                        <th className="text-left px-2 py-1.5">Unit</th>
                        <th className="text-left px-2 py-1.5">Col</th>
                        <th className="text-left px-2 py-1.5">Conf.</th>
                        <th className="text-left px-2 py-1.5">Warnings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {channelRows.map((row) => (
                        <tr key={row.key} className="border-t border-neutral-800/70">
                          <td className="px-2 py-1.5 text-cyan-300">{row.standard_key}</td>
                          <td className="px-2 py-1.5 text-neutral-200">{row.raw_name}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{row.unit}</td>
                          <td className="px-2 py-1.5 text-neutral-500">{row.column_index ?? "-"}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{fmt(row.confidence, 2)}</td>
                          <td className="px-2 py-1.5 text-amber-400">{(row.warnings || []).join("; ") || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Per-channel health */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-2 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5" /> Health per channel ({healthRows.length})
                </h3>
                <div className="overflow-x-auto border border-neutral-800 rounded-lg">
                  <table className="w-full text-[11px] font-mono">
                    <thead className="bg-neutral-950 text-neutral-500">
                      <tr>
                        <th className="text-left px-2 py-1.5">Channel</th>
                        <th className="text-left px-2 py-1.5">State</th>
                        <th className="text-left px-2 py-1.5">Samples</th>
                        <th className="text-left px-2 py-1.5">Missing %</th>
                        <th className="text-left px-2 py-1.5">Min</th>
                        <th className="text-left px-2 py-1.5">Max</th>
                        <th className="text-left px-2 py-1.5">Mean</th>
                        <th className="text-left px-2 py-1.5">Std</th>
                        <th className="text-left px-2 py-1.5">Flat</th>
                        <th className="text-left px-2 py-1.5">Spikes</th>
                        <th className="text-left px-2 py-1.5">Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {healthRows.map((row) => (
                        <tr key={row.key} className="border-t border-neutral-800/70">
                          <td className="px-2 py-1.5 text-neutral-200">
                            {row.channel_name}
                            <span className="text-neutral-600"> ({row.units})</span>
                          </td>
                          <td className={`px-2 py-1.5 ${row.quality_state === "GOOD" ? "text-emerald-300" : row.quality_state === "DEGRADED" ? "text-amber-300" : "text-rose-300"}`}>
                            {row.quality_state}
                          </td>
                          <td className="px-2 py-1.5 text-neutral-400">{row.sample_count ?? "-"}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{fmt(row.missing_pct, 2)}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{fmt(row.min_val, 2)}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{fmt(row.max_val, 2)}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{fmt(row.mean_val, 2)}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{fmt(row.std_val, 3)}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{row.flatline ? "yes" : "no"}</td>
                          <td className="px-2 py-1.5 text-neutral-400">{row.spikes ?? 0}</td>
                          <td className="px-2 py-1.5 text-amber-400">
                            {[...(row.warnings || []), ...(row.blockers || [])].join("; ") || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Lap segments */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-2">
                  Lap segments ({segments.length})
                </h3>
                {segments.length === 0 ? (
                  <p className="text-xs text-neutral-500">No segments were detected in this session.</p>
                ) : (
                  <div className="overflow-x-auto border border-neutral-800 rounded-lg">
                    <table className="w-full text-[11px] font-mono">
                      <thead className="bg-neutral-950 text-neutral-500">
                        <tr>
                          <th className="text-left px-2 py-1.5">Label</th>
                          <th className="text-left px-2 py-1.5">Start (s)</th>
                          <th className="text-left px-2 py-1.5">End (s)</th>
                          <th className="text-left px-2 py-1.5">Duration (s)</th>
                          <th className="text-left px-2 py-1.5">Peak lat (g)</th>
                          <th className="text-left px-2 py-1.5">Peak long (g)</th>
                          <th className="text-left px-2 py-1.5">Peak speed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {segments.map((seg, idx) => (
                          <tr key={`${seg.label}-${idx}`} className="border-t border-neutral-800/70">
                            <td className="px-2 py-1.5 text-neutral-200">{seg.label}</td>
                            <td className="px-2 py-1.5 text-neutral-400">{fmt(seg.t_start, 2)}</td>
                            <td className="px-2 py-1.5 text-neutral-400">{fmt(seg.t_end, 2)}</td>
                            <td className="px-2 py-1.5 text-neutral-400">{fmt(seg.duration_s, 2)}</td>
                            <td className="px-2 py-1.5 text-neutral-400">{fmt(seg.peak_lat_g, 2)}</td>
                            <td className="px-2 py-1.5 text-neutral-400">{fmt(seg.peak_long_g, 2)}</td>
                            <td className="px-2 py-1.5 text-neutral-400">{fmt(seg.peak_speed, 2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {detail?.model_note && (
                <p className="text-[11px] text-neutral-500 font-mono">{detail.model_note}</p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
