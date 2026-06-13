"use client";
import { useState, useRef, useEffect } from "react";
import { Brain, Send, Loader2, Sparkles, CheckCircle, TrendingUp, TrendingDown, Minus, Zap, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Recommendation {
  parameter: string;
  current_value: number;
  recommended_value: number;
  change_pct: number;
  reason: string;
  predicted_improvement: string;
}

interface ChatResponse {
  diagnosis: string;
  root_cause: string;
  recommendations: Recommendation[];
  setup_summary: string;
  confidence: "High" | "Medium" | "Low";
  simulated: boolean;
}

const PARAM_LABELS: Record<string, string> = {
  k_s: "Spring Rate",
  c: "Damping Coefficient",
  m_s: "Sprung Mass",
  m_u: "Unsprung Mass",
  k_t: "Tire Stiffness",
  MR: "Motion Ratio",
  c_t: "Tire Damping",
};

const PARAM_UNITS: Record<string, string> = {
  k_s: "N/m", c: "Ns/m", m_s: "kg", m_u: "kg", k_t: "N/m", MR: "", c_t: "Ns/m",
};

const EXAMPLE_PROBLEMS = [
  "My car bounces excessively over bumps and takes too long to settle. It feels like it's on a boat.",
  "The car feels very stiff and uncomfortable on rough roads but handles great on smooth tracks.",
  "After hitting a pothole, the car oscillates for a long time before settling. What's wrong?",
  "The tire is losing contact with the road on rough surfaces, causing understeer in corners.",
  "My suspension transmits too much road noise and vibration into the cabin at highway speeds.",
];

const CONFIDENCE_COLORS: Record<string, string> = {
  High: "text-green-400 border-green-400/30 bg-green-400/5",
  Medium: "text-yellow-400 border-yellow-400/30 bg-yellow-400/5",
  Low: "text-red-400 border-red-400/30 bg-red-400/5",
};

export default function AIEngineerPage() {
  const { token } = useAuth();
  const [problem, setProblem] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState("");
  const [expandedRec, setExpandedRec] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = textareaRef.current.scrollHeight + "px";
    }
  }, [problem]);

  const handleSubmit = async () => {
    if (!problem.trim() || loading) return;
    setLoading(true);
    setResult(null);
    setError("");

    try {
      const resp = await fetch(`${API_BASE}/ai/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ problem: problem.trim() }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || "AI Engine error. Please try again.");
      }

      const data: ChatResponse = await resp.json();
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const changePctIcon = (pct: number) => {
    if (Math.abs(pct) < 1) return <Minus size={14} className="text-gray-400" />;
    if (pct > 0) return <TrendingUp size={14} className="text-blue-400" />;
    return <TrendingDown size={14} className="text-orange-400" />;
  };

  return (
    <div className="min-h-full bg-black text-white">
      {/* Header */}
      <div className="border-b border-[#1a1a1a] px-8 py-6">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/20">
              <Brain size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">AI Race Engineer</h1>
              <p className="text-xs text-gray-500">Describe your handling problem — get physics-backed setup recommendations</p>
            </div>
            <div className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-purple-500/10 border border-purple-500/20">
              <Sparkles size={11} className="text-purple-400" />
              <span className="text-[11px] text-purple-400 font-medium">World&apos;s First</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-8 py-8 space-y-6">
        {/* Input */}
        <div className="rounded-2xl border border-[#222] bg-[#0a0a0a] p-6 space-y-4">
          <label className="text-sm font-medium text-gray-300">Describe your suspension problem in plain English</label>
          <textarea
            ref={textareaRef}
            value={problem}
            onChange={e => setProblem(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSubmit(); }}
            placeholder="e.g. My car bounces excessively over speed bumps and takes 4-5 oscillations to settle. Spring rate is 25,000 N/m, damping is 2050 Ns/m..."
            className="w-full bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none min-h-[100px] leading-relaxed"
          />
          <div className="flex items-center justify-between pt-2 border-t border-[#1a1a1a]">
            <span className="text-[11px] text-gray-600">Ctrl+Enter to submit</span>
            <button
              onClick={handleSubmit}
              disabled={loading || !problem.trim()}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition-all shadow-lg shadow-purple-500/20"
            >
              {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
              {loading ? "Analyzing..." : "Analyze Problem"}
            </button>
          </div>
        </div>

        {/* Example problems */}
        {!result && !loading && (
          <div className="space-y-2">
            <p className="text-xs text-gray-600 font-medium uppercase tracking-wider">Example problems</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_PROBLEMS.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => setProblem(ex)}
                  className="text-xs text-gray-500 border border-[#222] rounded-lg px-3 py-1.5 hover:border-purple-500/40 hover:text-gray-300 hover:bg-purple-500/5 transition-all text-left max-w-xs truncate"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl border border-red-500/20 bg-red-500/5">
            <AlertTriangle size={16} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="rounded-2xl border border-purple-500/20 bg-purple-500/5 p-8 text-center space-y-3">
            <Loader2 size={32} className="text-purple-400 animate-spin mx-auto" />
            <p className="text-sm text-purple-300 font-medium">Running physics simulations across 20 parameter variations...</p>
            <p className="text-xs text-gray-600">Analyzing spring rate, damping, tire stiffness, and motion ratio permutations</p>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-5 animate-in fade-in duration-500">
            {/* Diagnosis card */}
            <div className="rounded-2xl border border-[#222] bg-[#0a0a0a] p-6 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Zap size={15} className="text-yellow-400" />
                    <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Diagnosis</span>
                  </div>
                  <p className="text-base font-semibold text-white leading-relaxed">{result.diagnosis}</p>
                </div>
                <div className={`shrink-0 px-3 py-1 rounded-full border text-xs font-semibold ${CONFIDENCE_COLORS[result.confidence]}`}>
                  {result.confidence} Confidence
                </div>
              </div>

              <div className="pt-3 border-t border-[#1a1a1a]">
                <p className="text-xs text-gray-500 font-medium mb-1">Root Cause</p>
                <p className="text-sm text-gray-300 leading-relaxed">{result.root_cause}</p>
              </div>

              {result.simulated && (
                <div className="flex items-center gap-2 text-xs text-green-400">
                  <CheckCircle size={12} />
                  <span>Recommendations backed by real physics simulations</span>
                </div>
              )}
            </div>

            {/* Recommendations */}
            <div className="space-y-3">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Setup Recommendations</p>
              {result.recommendations.map((rec, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-[#222] bg-[#080808] overflow-hidden cursor-pointer hover:border-[#333] transition-colors"
                  onClick={() => setExpandedRec(expandedRec === i ? null : i)}
                >
                  <div className="flex items-center gap-4 px-5 py-4">
                    <div className="w-7 h-7 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center shrink-0">
                      <span className="text-xs font-bold text-purple-400">{i + 1}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white">{PARAM_LABELS[rec.parameter] || rec.parameter}</span>
                        <code className="text-xs text-gray-600 bg-[#111] px-1.5 py-0.5 rounded">{rec.parameter}</code>
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs text-gray-500 line-through">{rec.current_value.toLocaleString()} {PARAM_UNITS[rec.parameter]}</span>
                        <span className="text-xs">→</span>
                        <span className="text-xs font-bold text-white">{rec.recommended_value.toLocaleString()} {PARAM_UNITS[rec.parameter]}</span>
                        <div className="flex items-center gap-1">
                          {changePctIcon(rec.change_pct)}
                          <span className={`text-xs font-semibold ${Math.abs(rec.change_pct) < 1 ? "text-gray-400" : rec.change_pct > 0 ? "text-blue-400" : "text-orange-400"}`}>
                            {rec.change_pct > 0 ? "+" : ""}{rec.change_pct.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="shrink-0">
                      {expandedRec === i ? <ChevronUp size={14} className="text-gray-600" /> : <ChevronDown size={14} className="text-gray-600" />}
                    </div>
                  </div>
                  {expandedRec === i && (
                    <div className="px-5 pb-4 pt-0 border-t border-[#111] space-y-3">
                      <div>
                        <p className="text-xs text-gray-500 font-medium mb-1">Why this helps</p>
                        <p className="text-sm text-gray-300 leading-relaxed">{rec.reason}</p>
                      </div>
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-green-500/5 border border-green-500/15">
                        <TrendingUp size={12} className="text-green-400 shrink-0" />
                        <p className="text-xs text-green-300">{rec.predicted_improvement}</p>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Summary */}
            <div className="rounded-2xl border border-purple-500/20 bg-purple-500/5 p-5">
              <p className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">Setup Summary</p>
              <p className="text-sm text-gray-200 leading-relaxed">{result.setup_summary}</p>
            </div>

            {/* Try again */}
            <button
              onClick={() => { setResult(null); setProblem(""); }}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors underline underline-offset-2"
            >
              Ask another question
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
