"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  EvidenceGraphApi,
  EvidenceGraphTraversalResponse,
  EvidenceGraphNodeDTO,
  EvidenceGraphEdgeDTO,
  EvidenceGraphPathExplanationResponse,
} from "../../lib/api_client";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  Car,
  CheckCircle2,
  Compass,
  Copy,
  Disc,
  ExternalLink,
  Eye,
  FileQuestion,
  FileText,
  Filter,
  FlaskConical,
  Hash,
  Info,
  Layers,
  List,
  Loader2,
  Lock,
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Wrench,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

export interface EvidenceGraphProps {
  rootType?: string;
  rootId?: string;
  // Legacy / fallback props for backward compatibility
  vehicleRef?: string;
  setupRef?: string;
  runLabel?: string;
  initialDirection?: "FORWARD" | "BACKWARD";
  initialDepth?: number;
  className?: string;
  onSelectEntity?: (entityType: string, entityId: string) => void;
}

// Visual configuration per canonical SupportedEntityType
const ENTITY_CONFIG: Record<
  string,
  { label: string; bg: string; border: string; text: string; icon: React.ElementType }
> = {
  EngineeringDecision: {
    label: "Engineering Decision",
    bg: "bg-amber-500/15",
    border: "border-amber-500/50",
    text: "text-amber-400",
    icon: CheckCircle2,
  },
  Approval: {
    label: "Approval Record",
    bg: "bg-emerald-500/15",
    border: "border-emerald-500/50",
    text: "text-emerald-400",
    icon: ShieldCheck,
  },
  BlindValidation: {
    label: "Blind Validation",
    bg: "bg-teal-500/15",
    border: "border-teal-500/50",
    text: "text-teal-400",
    icon: ShieldCheck,
  },
  SetupComparison: {
    label: "Setup Comparison",
    bg: "bg-sky-500/15",
    border: "border-sky-500/50",
    text: "text-sky-400",
    icon: Sliders,
  },
  Optimization: {
    label: "Optimization",
    bg: "bg-fuchsia-500/15",
    border: "border-fuchsia-500/50",
    text: "text-fuchsia-400",
    icon: Sparkles,
  },
  SimulationRun: {
    label: "Simulation Run",
    bg: "bg-blue-500/15",
    border: "border-blue-500/50",
    text: "text-blue-400",
    icon: Activity,
  },
  SetupCandidate: {
    label: "Setup Candidate",
    bg: "bg-purple-500/15",
    border: "border-purple-500/50",
    text: "text-purple-400",
    icon: Wrench,
  },
  ControlledExperiment: {
    label: "Controlled Experiment",
    bg: "bg-indigo-500/15",
    border: "border-indigo-500/50",
    text: "text-indigo-400",
    icon: FlaskConical,
  },
  Experiment: {
    label: "Experiment",
    bg: "bg-indigo-500/15",
    border: "border-indigo-500/50",
    text: "text-indigo-400",
    icon: FlaskConical,
  },
  CausalHypothesis: {
    label: "Causal Hypothesis",
    bg: "bg-violet-500/15",
    border: "border-violet-500/50",
    text: "text-violet-400",
    icon: Sparkles,
  },
  EngineeringProblem: {
    label: "Engineering Problem",
    bg: "bg-rose-500/15",
    border: "border-rose-500/50",
    text: "text-rose-400",
    icon: AlertCircle,
  },
  EngineeringQuestion: {
    label: "Engineering Question",
    bg: "bg-orange-500/15",
    border: "border-orange-500/50",
    text: "text-orange-400",
    icon: FileQuestion,
  },
  Investigation: {
    label: "Investigation",
    bg: "bg-cyan-500/15",
    border: "border-cyan-500/50",
    text: "text-cyan-400",
    icon: Compass,
  },
  TelemetrySession: {
    label: "Telemetry Session",
    bg: "bg-emerald-500/15",
    border: "border-emerald-500/50",
    text: "text-emerald-400",
    icon: Disc,
  },
  TrackTestPrediction: {
    label: "Track Prediction",
    bg: "bg-yellow-500/15",
    border: "border-yellow-500/50",
    text: "text-yellow-400",
    icon: Activity,
  },
  PostTrackReconciliation: {
    label: "Post-Track Reconciliation",
    bg: "bg-lime-500/15",
    border: "border-lime-500/50",
    text: "text-lime-400",
    icon: Layers,
  },
  VehicleProfile: {
    label: "Vehicle Profile",
    bg: "bg-neutral-500/15",
    border: "border-neutral-500/50",
    text: "text-neutral-300",
    icon: Car,
  },
};

const DEFAULT_CONFIG = {
  label: "Engineering Entity",
  bg: "bg-neutral-800/40",
  border: "border-neutral-700",
  text: "text-neutral-300",
  icon: Layers,
};

export default function EvidenceGraph({
  rootType: propRootType,
  rootId: propRootId,
  vehicleRef,
  setupRef,
  runLabel,
  initialDirection,
  initialDepth = 4,
  className = "",
  onSelectEntity,
}: EvidenceGraphProps) {
  // Determine effective root type and identifier
  const effectiveRoot = useMemo(() => {
    if (propRootType && propRootId) {
      return { type: propRootType, id: propRootId };
    }
    if (runLabel) {
      return { type: "SimulationRun", id: runLabel };
    }
    if (setupRef) {
      return { type: "SetupCandidate", id: setupRef };
    }
    if (vehicleRef) {
      return { type: "VehicleProfile", id: vehicleRef };
    }
    // Default fallback to decision if nothing provided
    return { type: "EngineeringDecision", id: "DEC-P3K1-01" };
  }, [propRootType, propRootId, runLabel, setupRef, vehicleRef]);

  // Default direction: BACKWARD for decisions and approvals (tracing upstream evidence), FORWARD for questions/sessions
  const defaultDir: "FORWARD" | "BACKWARD" = useMemo(() => {
    if (initialDirection) return initialDirection;
    if (["EngineeringDecision", "Approval", "BlindValidation"].includes(effectiveRoot.type)) {
      return "BACKWARD";
    }
    return "FORWARD";
  }, [initialDirection, effectiveRoot.type]);

  const [direction, setDirection] = useState<"FORWARD" | "BACKWARD">(defaultDir);
  const [depth, setDepth] = useState<number>(initialDepth);
  const [relationshipFilter, setRelationshipFilter] = useState<string>("ALL");
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>("ALL");

  const [graphData, setGraphData] = useState<EvidenceGraphTraversalResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorStatus, setErrorStatus] = useState<
    "NONE" | "NOT_FOUND" | "UNAUTHORIZED" | "TENANT_BOUNDARY" | "SERVER_ERROR"
  >("NONE");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [selectedNode, setSelectedNode] = useState<EvidenceGraphNodeDTO | null>(null);
  const [viewMode, setViewMode] = useState<"graph" | "accessible_list">("graph");
  const [copiedHash, setCopiedHash] = useState<boolean>(false);

  // Path explanation state
  const [pathExplaining, setPathExplaining] = useState<boolean>(false);
  const [pathData, setPathData] = useState<EvidenceGraphPathExplanationResponse | null>(null);
  const [pathLoading, setPathLoading] = useState<boolean>(false);

  // Zoom / pan state
  const [zoom, setZoom] = useState<number>(1);

  // Fetch traversal from authoritative Phase 4.2 API
  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setErrorStatus("NONE");
    setErrorMessage(null);

    try {
      const res = await EvidenceGraphApi.traverseEvidenceGraph({
        root_type: effectiveRoot.type,
        root_id: effectiveRoot.id,
        direction,
        max_depth: depth,
        relationship: relationshipFilter !== "ALL" ? relationshipFilter : undefined,
        entity_type: entityTypeFilter !== "ALL" ? entityTypeFilter : undefined,
      });

      setGraphData(res);
      if (res.nodes.length > 0) {
        // Select root if present, or first node
        const rootNode = res.nodes.find(
          (n) => n.entity_type === effectiveRoot.type && n.entity_id === effectiveRoot.id
        );
        setSelectedNode(rootNode || res.nodes[0]);
      } else {
        setSelectedNode(null);
      }
    } catch (err: any) {
      const msg = err?.message || String(err);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        setErrorStatus("NOT_FOUND");
      } else if (msg.includes("401") || msg.includes("403") || msg.toLowerCase().includes("unauthorized")) {
        setErrorStatus("UNAUTHORIZED");
      } else if (msg.toLowerCase().includes("tenant") || msg.toLowerCase().includes("isolation")) {
        setErrorStatus("TENANT_BOUNDARY");
      } else {
        setErrorStatus("SERVER_ERROR");
      }
      setErrorMessage(msg);
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  }, [effectiveRoot.type, effectiveRoot.id, direction, depth, relationshipFilter, entityTypeFilter]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // Collect available filter options from the returned data
  const availableRelationships = useMemo(() => {
    if (!graphData) return [];
    const rels = new Set<string>();
    graphData.edges.forEach((e) => rels.add(e.relationship));
    return Array.from(rels).sort();
  }, [graphData]);

  const availableEntityTypes = useMemo(() => {
    if (!graphData) return [];
    const types = new Set<string>();
    graphData.nodes.forEach((n) => types.add(n.entity_type));
    return Array.from(types).sort();
  }, [graphData]);

  // Request deterministic path explanation between Root and Selected node
  const handleExplainPath = async (targetNode: EvidenceGraphNodeDTO) => {
    if (!targetNode) return;
    setPathLoading(true);
    setPathExplaining(true);
    try {
      const resolveTypeAndId = (x: { type?: string; entity_type?: string; id?: string; entity_id?: string }) => ({
        type: x.entity_type || x.type || "",
        id: x.entity_id || x.id || "",
      });
      // In backward traversal, path is Target -> Root. In forward traversal, Root -> Target.
      const rawSrc = direction === "BACKWARD" ? targetNode : effectiveRoot;
      const rawTgt = direction === "BACKWARD" ? effectiveRoot : targetNode;
      const s = resolveTypeAndId(rawSrc);
      const t = resolveTypeAndId(rawTgt);

      const res = await EvidenceGraphApi.explainEvidencePath({
        source_type: s.type,
        source_id: s.id,
        target_type: t.type,
        target_id: t.id,
        max_depth: 10,
      });
      setPathData(res);
    } catch (err: any) {
      setPathData(null);
    } finally {
      setPathLoading(false);
    }
  };

  // Deterministic topological layout computation
  const layout = useMemo(() => {
    if (!graphData || graphData.nodes.length === 0) {
      return { nodes: [], edges: [], width: 800, height: 400 };
    }

    // Group nodes by depth
    const nodesByDepth: Record<number, EvidenceGraphNodeDTO[]> = {};
    const seenNodeKeys = new Set<string>();
    const deduplicatedNodes: EvidenceGraphNodeDTO[] = [];

    // Deduplicate nodes while preserving depths
    for (const n of graphData.nodes) {
      const key = `${n.entity_type}:${n.entity_id}`;
      if (!seenNodeKeys.has(key)) {
        seenNodeKeys.add(key);
        deduplicatedNodes.push(n);
        const d = n.depth || 0;
        if (!nodesByDepth[d]) nodesByDepth[d] = [];
        nodesByDepth[d].push(n);
      }
    }

    const colWidth = 260;
    const rowHeight = 110;
    const depths = Object.keys(nodesByDepth)
      .map(Number)
      .sort((a, b) => a - b);

    const positionedNodes = deduplicatedNodes.map((node) => {
      const colIndex = depths.indexOf(node.depth);
      const rowList = nodesByDepth[node.depth] || [node];
      const rowIndex = rowList.findIndex(
        (item) => item.entity_type === node.entity_type && item.entity_id === node.entity_id
      );

      const x = 50 + colIndex * colWidth;
      const y = 50 + (rowIndex >= 0 ? rowIndex : 0) * rowHeight;
      return {
        ...node,
        key: `${node.entity_type}:${node.entity_id}`,
        x,
        y,
      };
    });

    const nodeCoordMap = new Map(positionedNodes.map((n) => [n.key, n]));

    const positionedEdges = graphData.edges
      .map((edge) => {
        const sKey = `${edge.source_type}:${edge.source_id}`;
        const tKey = `${edge.target_type}:${edge.target_id}`;
        const s = nodeCoordMap.get(sKey);
        const t = nodeCoordMap.get(tKey);
        if (!s || !t) return null;

        return {
          ...edge,
          sourceCoord: { x: s.x + 190, y: s.y + 35 },
          targetCoord: { x: t.x, y: t.y + 35 },
        };
      })
      .filter(Boolean) as Array<EvidenceGraphEdgeDTO & { sourceCoord: { x: number; y: number }; targetCoord: { x: number; y: number } }>;

    const maxX = Math.max(...positionedNodes.map((n) => n.x), 600) + colWidth;
    const maxY = Math.max(...positionedNodes.map((n) => n.y), 300) + rowHeight;

    return {
      nodes: positionedNodes,
      edges: positionedEdges,
      width: maxX,
      height: maxY,
    };
  }, [graphData]);

  // Edges connected to currently selected node
  const selectedNodeEdges = useMemo(() => {
    if (!selectedNode || !graphData) return { inbound: [], outbound: [] };
    const key = `${selectedNode.entity_type}:${selectedNode.entity_id}`;
    const inbound = graphData.edges.filter(
      (e) => `${e.target_type}:${e.target_id}` === key
    );
    const outbound = graphData.edges.filter(
      (e) => `${e.source_type}:${e.source_id}` === key
    );
    return { inbound, outbound };
  }, [selectedNode, graphData]);

  // Selected node artifact hash (if found in attached edges)
  const selectedArtifactHash = useMemo(() => {
    if (!selectedNode || !graphData) return null;
    for (const e of graphData.edges) {
      if (e.source_type === selectedNode.entity_type && e.source_id === selectedNode.entity_id) {
        if (e.source_artifact_hash) return e.source_artifact_hash;
      }
      if (e.target_type === selectedNode.entity_type && e.target_id === selectedNode.entity_id) {
        if (e.target_artifact_hash) return e.target_artifact_hash;
      }
    }
    return null;
  }, [selectedNode, graphData]);

  const copyHash = (hash: string) => {
    navigator.clipboard?.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  return (
    <div
      role="region"
      aria-label="Evidence Graph and Provenance"
      className={`flex flex-col bg-neutral-950 border border-neutral-800 rounded-2xl overflow-hidden shadow-2xl text-white font-sans ${className}`}
    >
      {/* ── TOOLBAR / CONTROLS ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-neutral-900/90 border-b border-neutral-800">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-rose-400 font-mono text-xs uppercase tracking-wider font-semibold">
            <Network size={16} />
            <span>EVIDENCE GRAPH</span>
          </div>

          {/* Root identifier badge */}
          <div className="px-2.5 py-1 rounded-lg bg-neutral-800/80 border border-neutral-700/80 text-xs font-mono flex items-center gap-1.5">
            <span className="text-neutral-400">ROOT:</span>
            <span className="text-amber-400 font-bold">{effectiveRoot.type}</span>
            <span className="text-neutral-300">{effectiveRoot.id}</span>
          </div>
        </div>

        {/* Direction Controls (Explicit Phase 4.4 Requirement) */}
        <div className="flex items-center gap-2">
          <div
            role="group"
            aria-label="Traversal Direction"
            className="flex bg-neutral-950 p-1 rounded-xl border border-neutral-800 text-xs font-mono"
          >
            <button
              type="button"
              onClick={() => setDirection("BACKWARD")}
              aria-pressed={direction === "BACKWARD"}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                direction === "BACKWARD"
                  ? "bg-rose-500 text-white font-bold shadow-md shadow-rose-500/20"
                  : "text-neutral-400 hover:text-white"
              }`}
              title="Trace upstream engineering support (Why was this created?)"
            >
              <ArrowLeft size={13} />
              <span>BACKWARD (Upstream Support)</span>
            </button>
            <button
              type="button"
              onClick={() => setDirection("FORWARD")}
              aria-pressed={direction === "FORWARD"}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                direction === "FORWARD"
                  ? "bg-rose-500 text-white font-bold shadow-md shadow-rose-500/20"
                  : "text-neutral-400 hover:text-white"
              }`}
              title="Trace downstream engineering consequences (What was derived from this?)"
            >
              <span>FORWARD (Consequences)</span>
              <ArrowRight size={13} />
            </button>
          </div>

          {/* Bounded Depth Control */}
          <div className="flex items-center gap-1.5 bg-neutral-950 px-2.5 py-1 rounded-xl border border-neutral-800 text-xs font-mono">
            <span className="text-neutral-400">DEPTH:</span>
            <button
              type="button"
              disabled={depth <= 1}
              onClick={() => setDepth((d) => Math.max(1, d - 1))}
              className="w-5 h-5 flex items-center justify-center rounded hover:bg-neutral-800 disabled:opacity-40"
              aria-label="Decrease depth"
            >
              -
            </button>
            <span className="text-white font-bold w-4 text-center">{depth}</span>
            <button
              type="button"
              disabled={depth >= 10}
              onClick={() => setDepth((d) => Math.min(10, d + 1))}
              className="w-5 h-5 flex items-center justify-center rounded hover:bg-neutral-800 disabled:opacity-40"
              aria-label="Increase depth"
            >
              +
            </button>
          </div>

          {/* View Mode Toggle (Visual Graph vs Accessible List) */}
          <div className="flex bg-neutral-950 p-1 rounded-xl border border-neutral-800 text-xs font-mono">
            <button
              type="button"
              onClick={() => setViewMode("graph")}
              aria-pressed={viewMode === "graph"}
              className={`p-1.5 rounded ${viewMode === "graph" ? "bg-neutral-800 text-white" : "text-neutral-400"}`}
              title="Visual graph view"
              aria-label="Visual graph view"
            >
              <Network size={14} />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("accessible_list")}
              aria-pressed={viewMode === "accessible_list"}
              className={`p-1.5 rounded ${viewMode === "accessible_list" ? "bg-neutral-800 text-white" : "text-neutral-400"}`}
              title="Accessible linear list view"
              aria-label="Accessible linear list view"
            >
              <List size={14} />
            </button>
          </div>

          {/* Refresh */}
          <button
            type="button"
            onClick={fetchGraph}
            disabled={loading}
            className="p-2 rounded-xl bg-neutral-950 border border-neutral-800 hover:border-neutral-700 text-neutral-300 hover:text-white transition-all disabled:opacity-50"
            title="Refresh graph"
            aria-label="Refresh graph"
          >
            <RotateCcw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* ── FILTER & TRUNCATION ALERT BAR ──────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 bg-neutral-900/60 border-b border-neutral-800/80 text-xs">
        {/* Relationship & Entity Filter */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-neutral-400">
            <Filter size={12} />
            <span>Filter Relationship:</span>
            <select
              value={relationshipFilter}
              onChange={(e) => setRelationshipFilter(e.target.value)}
              className="bg-neutral-950 border border-neutral-800 rounded px-2 py-0.5 text-white font-mono text-[11px] focus:outline-none focus:border-rose-500"
              aria-label="Filter by relationship"
            >
              <option value="ALL">All Relationships ({availableRelationships.length})</option>
              {availableRelationships.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-neutral-400">
            <span>Entity Type:</span>
            <select
              value={entityTypeFilter}
              onChange={(e) => setEntityTypeFilter(e.target.value)}
              className="bg-neutral-950 border border-neutral-800 rounded px-2 py-0.5 text-white font-mono text-[11px] focus:outline-none focus:border-rose-500"
              aria-label="Filter by entity type"
            >
              <option value="ALL">All Entity Types ({availableEntityTypes.length})</option>
              {availableEntityTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Truncation & Limit UX (Explicit Requirement) */}
        {graphData?.traversal.limit_reached && (
          <div className="flex items-center gap-1.5 text-amber-400 font-mono text-[11px] bg-amber-500/10 px-2.5 py-1 rounded border border-amber-500/30">
            <AlertTriangle size={13} />
            <span>
              TRUNCATED: Limit reached ({graphData.traversal.limit_type || "LIMIT_EXCEEDED"}). Returned{" "}
              {graphData.traversal.nodes_returned} nodes, {graphData.traversal.edges_returned} edges.
            </span>
          </div>
        )}

        {/* Stats */}
        {graphData && (
          <div className="text-neutral-400 font-mono text-[11px] flex items-center gap-2">
            <span>Nodes: {graphData.nodes.length}</span>
            <span>•</span>
            <span>Edges: {graphData.edges.length}</span>
          </div>
        )}
      </div>

      {/* ── MAIN CONTENT AREA ──────────────────────────────────────────── */}
      <div className="relative flex-1 flex flex-col md:flex-row min-h-[460px] max-h-[700px] overflow-hidden">
        {/* Loading State */}
        {loading && (
          <div
            role="status"
            className="absolute inset-0 z-30 bg-neutral-950/80 backdrop-blur-sm flex flex-col items-center justify-center gap-3 text-neutral-300"
          >
            <Loader2 size={32} className="animate-spin text-rose-500" />
            <span className="font-mono text-xs tracking-wider">TRAVERSING EVIDENCE GRAPH...</span>
          </div>
        )}

        {/* Error States */}
        {!loading && errorStatus !== "NONE" && (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
            {errorStatus === "NOT_FOUND" && (
              <div className="max-w-md space-y-3">
                <AlertCircle size={40} className="mx-auto text-amber-500" />
                <h3 className="text-base font-bold text-white">Entity Not Found in Evidence Graph</h3>
                <p className="text-xs text-neutral-400 leading-relaxed font-mono">
                  {effectiveRoot.type}:{effectiveRoot.id} does not exist in the authoritative database.
                </p>
              </div>
            )}
            {errorStatus === "UNAUTHORIZED" && (
              <div className="max-w-md space-y-3">
                <Lock size={40} className="mx-auto text-rose-500" />
                <h3 className="text-base font-bold text-white">Authentication Required</h3>
                <p className="text-xs text-neutral-400 leading-relaxed">
                  Valid API key or bearer token required to query graph relationships.
                </p>
              </div>
            )}
            {errorStatus === "TENANT_BOUNDARY" && (
              <div className="max-w-md space-y-3">
                <ShieldAlert size={40} className="mx-auto text-rose-500" />
                <h3 className="text-base font-bold text-white">Workspace Isolation Boundary</h3>
                <p className="text-xs text-neutral-400 leading-relaxed font-mono">
                  Traversal rejected. Requested entity belongs to another tenant or private workspace.
                </p>
              </div>
            )}
            {errorStatus === "SERVER_ERROR" && (
              <div className="max-w-md space-y-3">
                <AlertTriangle size={40} className="mx-auto text-rose-500" />
                <h3 className="text-base font-bold text-white">Graph Service Error</h3>
                <p className="text-xs text-neutral-400 leading-relaxed font-mono">{errorMessage}</p>
                <button
                  type="button"
                  onClick={fetchGraph}
                  className="px-4 py-2 rounded-xl bg-rose-500 text-white font-mono text-xs font-bold hover:bg-rose-600 transition-all"
                >
                  Retry Traversal
                </button>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!loading && errorStatus === "NONE" && (!graphData || graphData.nodes.length === 0) && (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-neutral-400">
            <Network size={40} className="mx-auto text-neutral-600 mb-3" />
            <h3 className="text-base font-bold text-white mb-1">No Evidence Relationships Recorded</h3>
            <p className="text-xs max-w-sm leading-relaxed">
              No authoritative relationships originate from or target {effectiveRoot.type}:{effectiveRoot.id} within
              the current workspace scope.
            </p>
          </div>
        )}

        {/* ── GRAPH VISUAL CANVAS ──────────────────────────────────────── */}
        {!loading && errorStatus === "NONE" && graphData && graphData.nodes.length > 0 && viewMode === "graph" && (
          <div className="flex-1 relative overflow-auto bg-[#0a0a0d] p-6 select-none">
            {/* Zoom Controls */}
            <div className="absolute top-4 right-4 z-20 flex flex-col bg-neutral-900/90 border border-neutral-800 rounded-xl p-1 shadow-lg">
              <button
                type="button"
                onClick={() => setZoom((z) => Math.min(2, z + 0.15))}
                className="p-1.5 hover:bg-neutral-800 rounded text-neutral-300 hover:text-white"
                title="Zoom in"
                aria-label="Zoom in"
              >
                <ZoomIn size={14} />
              </button>
              <button
                type="button"
                onClick={() => setZoom((z) => Math.max(0.4, z - 0.15))}
                className="p-1.5 hover:bg-neutral-800 rounded text-neutral-300 hover:text-white"
                title="Zoom out"
                aria-label="Zoom out"
              >
                <ZoomOut size={14} />
              </button>
              <button
                type="button"
                onClick={() => setZoom(1)}
                className="p-1.5 hover:bg-neutral-800 rounded text-neutral-300 hover:text-white text-[10px] font-mono"
                title="Reset zoom"
                aria-label="Reset zoom"
              >
                1x
              </button>
            </div>

            <div
              style={{
                transform: `scale(${zoom})`,
                transformOrigin: "top left",
                width: layout.width,
                height: layout.height,
              }}
              className="relative transition-transform duration-150"
            >
              {/* SVG Edges Layer */}
              <svg
                width={layout.width}
                height={layout.height}
                className="absolute inset-0 pointer-events-none z-0"
              >
                <defs>
                  <marker
                    id="evidence-arrow"
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 1 L 10 5 L 0 9 z" fill="#f43f5e" />
                  </marker>
                </defs>

                {layout.edges.map((e, idx) => {
                  const sx = e.sourceCoord.x;
                  const sy = e.sourceCoord.y;
                  const tx = e.targetCoord.x;
                  const ty = e.targetCoord.y;

                  const midX = (sx + tx) / 2;
                  const midY = (sy + ty) / 2;
                  const path = `M ${sx} ${sy} C ${midX} ${sy}, ${midX} ${ty}, ${tx} ${ty}`;

                  return (
                    <g key={`${e.id}-${idx}`}>
                      <path
                        d={path}
                        fill="none"
                        stroke="#f43f5e"
                        strokeWidth="1.75"
                        strokeOpacity="0.65"
                        markerEnd="url(#evidence-arrow)"
                      />
                      {/* Relationship Pill Label */}
                      <g transform={`translate(${midX}, ${midY})`}>
                        <rect
                          x="-45"
                          y="-9"
                          width="90"
                          height="18"
                          rx="4"
                          fill="#18181b"
                          stroke="#3f3f46"
                          strokeWidth="1"
                        />
                        <text
                          x="0"
                          y="3"
                          textAnchor="middle"
                          fill="#f43f5e"
                          fontSize="9"
                          fontFamily="monospace"
                          fontWeight="bold"
                        >
                          {e.relationship}
                        </text>
                      </g>
                    </g>
                  );
                })}
              </svg>

              {/* DOM Nodes Layer */}
              {layout.nodes.map((node) => {
                const isRoot =
                  node.entity_type === effectiveRoot.type && node.entity_id === effectiveRoot.id;
                const isSelected =
                  selectedNode?.entity_type === node.entity_type &&
                  selectedNode?.entity_id === node.entity_id;

                const cfg = ENTITY_CONFIG[node.entity_type] || DEFAULT_CONFIG;
                const IconComponent = cfg.icon;

                return (
                  <div
                    key={node.key}
                    tabIndex={0}
                    role="button"
                    aria-label={`${node.entity_type}: ${node.entity_id}`}
                    onClick={() => setSelectedNode(node)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedNode(node);
                      }
                    }}
                    style={{ left: node.x, top: node.y, width: 200 }}
                    className={`absolute z-10 p-3 rounded-xl cursor-pointer transition-all border ${cfg.bg} ${
                      isSelected
                        ? "border-rose-500 shadow-lg shadow-rose-500/25 ring-2 ring-rose-500/50"
                        : isRoot
                        ? "border-amber-400 shadow-md shadow-amber-400/20 ring-1 ring-amber-400/40"
                        : `${cfg.border} hover:border-neutral-500`
                    }`}
                  >
                    <div className="flex items-center justify-between text-[10px] font-mono mb-1">
                      <div className="flex items-center gap-1 font-bold">
                        {isRoot && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[9px]">
                            ROOT
                          </span>
                        )}
                        <span className="text-neutral-400">DEPTH {node.depth}</span>
                      </div>
                      <IconComponent size={13} className={cfg.text} />
                    </div>

                    <div className="text-[11px] font-bold text-white truncate font-sans" title={node.entity_type}>
                      {cfg.label}
                    </div>

                    <div className="text-[11px] font-mono text-neutral-300 truncate mt-0.5" title={node.entity_id}>
                      {node.entity_id}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── ACCESSIBLE TEXT / LIST VIEW ───────────────────────────────── */}
        {!loading && errorStatus === "NONE" && graphData && viewMode === "accessible_list" && (
          <div className="flex-1 overflow-auto p-6 bg-[#0a0a0d] space-y-4">
            <div className="p-3 bg-neutral-900 border border-neutral-800 rounded-xl text-xs font-mono text-neutral-300">
              <span>Linear Provenance Chain ({direction} traversal from {effectiveRoot.type}:{effectiveRoot.id})</span>
            </div>

            <ol className="space-y-3 font-mono text-xs">
              {graphData.edges.map((edge, idx) => (
                <li
                  key={edge.id || idx}
                  className="p-3 bg-neutral-950 border border-neutral-800 rounded-xl flex items-center justify-between gap-4"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-neutral-500">{idx + 1}.</span>
                    <span className="text-amber-400 font-bold">{edge.source_type}</span>
                    <span className="text-neutral-300">{edge.source_id}</span>
                  </div>

                  <div className="px-2 py-0.5 rounded bg-rose-500/15 border border-rose-500/40 text-rose-400 font-bold text-[11px]">
                    -- {edge.relationship} --&gt;
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-cyan-400 font-bold">{edge.target_type}</span>
                    <span className="text-neutral-300">{edge.target_id}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* ── NODE DETAILS SIDEBAR ──────────────────────────────────────── */}
        {selectedNode && (
          <div className="w-full md:w-80 bg-neutral-900/95 border-t md:border-t-0 md:border-l border-neutral-800 p-4 flex flex-col justify-between overflow-auto z-20">
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
                <div className="flex items-center gap-2">
                  <Info size={14} className="text-rose-400" />
                  <span className="text-xs font-mono font-bold tracking-wider uppercase text-neutral-300">
                    ENTITY DETAILS
                  </span>
                </div>
                {selectedNode.entity_type === effectiveRoot.type &&
                  selectedNode.entity_id === effectiveRoot.id && (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold">
                      ROOT
                    </span>
                  )}
              </div>

              {/* Entity Type & ID */}
              <div className="space-y-2">
                <div>
                  <div className="text-[10px] font-mono text-neutral-400 uppercase">Entity Type</div>
                  <div className="text-xs font-bold text-white font-mono mt-0.5">
                    {selectedNode.entity_type}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] font-mono text-neutral-400 uppercase">Identifier</div>
                  <div className="text-xs font-mono text-neutral-200 break-all bg-neutral-950 p-2 rounded-lg border border-neutral-800 mt-0.5">
                    {selectedNode.entity_id}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] font-mono text-neutral-400 uppercase">Traversal Depth</div>
                  <div className="text-xs font-mono text-neutral-300 mt-0.5">{selectedNode.depth} hops from root</div>
                </div>

                {/* Artifact Hash */}
                {selectedArtifactHash && (
                  <div>
                    <div className="text-[10px] font-mono text-neutral-400 uppercase flex items-center justify-between">
                      <span>Artifact SHA-256</span>
                      <button
                        type="button"
                        onClick={() => copyHash(selectedArtifactHash)}
                        className="text-neutral-400 hover:text-white flex items-center gap-1 text-[9px]"
                      >
                        <Copy size={10} />
                        <span>{copiedHash ? "COPIED" : "COPY"}</span>
                      </button>
                    </div>
                    <div
                      className="text-[11px] font-mono text-emerald-400 break-all bg-neutral-950 p-2 rounded-lg border border-neutral-800 mt-0.5"
                      title={selectedArtifactHash}
                    >
                      {selectedArtifactHash.slice(0, 24)}...
                    </div>
                  </div>
                )}
              </div>

              {/* Upstream & Downstream Counts */}
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-neutral-800 text-xs font-mono">
                <div className="p-2 rounded bg-neutral-950 border border-neutral-800/80">
                  <div className="text-[10px] text-neutral-500">INBOUND</div>
                  <div className="text-sm font-bold text-white">{selectedNodeEdges.inbound.length}</div>
                </div>
                <div className="p-2 rounded bg-neutral-950 border border-neutral-800/80">
                  <div className="text-[10px] text-neutral-500">OUTBOUND</div>
                  <div className="text-sm font-bold text-white">{selectedNodeEdges.outbound.length}</div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="space-y-2 pt-4 border-t border-neutral-800">
              {/* Explain Provenance Path to/from Root */}
              {selectedNode.entity_id !== effectiveRoot.id && (
                <button
                  type="button"
                  onClick={() => handleExplainPath(selectedNode)}
                  disabled={pathLoading}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-neutral-800 hover:bg-neutral-700 text-white font-mono text-xs font-semibold transition-all disabled:opacity-50"
                >
                  <ArrowDownRight size={13} className="text-rose-400" />
                  <span>Explain Provenance Path</span>
                </button>
              )}

              {/* Open Authoritative Entity View */}
              {onSelectEntity && (
                <button
                  type="button"
                  onClick={() => onSelectEntity(selectedNode.entity_type, selectedNode.entity_id)}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500 hover:bg-rose-600 text-white font-mono text-xs font-bold transition-all shadow-md shadow-rose-500/20"
                >
                  <ExternalLink size={13} />
                  <span>Open Engineering Object</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── PROVENANCE PATH EXPLANATION MODAL ─────────────────────────── */}
      {pathExplaining && (
        <div
          role="dialog"
          aria-labelledby="provenance-path-title"
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
        >
          <div className="bg-neutral-900 border border-neutral-800 rounded-2xl max-w-xl w-full p-6 text-white space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
              <div className="flex items-center gap-2">
                <Compass size={18} className="text-rose-400" />
                <h3 id="provenance-path-title" className="text-base font-bold text-white">
                  Deterministic Provenance Path
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setPathExplaining(false)}
                className="text-neutral-400 hover:text-white font-mono text-sm px-2 py-1 rounded hover:bg-neutral-800"
              >
                ✕
              </button>
            </div>

            {pathLoading ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3">
                <Loader2 size={24} className="animate-spin text-rose-500" />
                <span className="font-mono text-xs text-neutral-400">Reconstructing shortest directed path...</span>
              </div>
            ) : pathData && pathData.path_found ? (
              <div className="space-y-4">
                <div className="p-3 rounded-xl bg-neutral-950 border border-neutral-800 text-xs font-mono flex items-center justify-between text-neutral-300">
                  <span>Path Length: {pathData.length} hops</span>
                  <span className="text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCircle2 size={13} /> VERIFIED DIRECTED PROVENANCE
                  </span>
                </div>

                <div className="space-y-2 max-h-72 overflow-auto">
                  {pathData.edges.map((edge, idx) => (
                    <div
                      key={edge.id || idx}
                      className="p-3 bg-neutral-950/80 border border-neutral-800 rounded-xl text-xs font-mono space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-[11px] text-neutral-400">
                        <span>STEP {idx + 1}</span>
                        <span className="text-rose-400 font-bold">{edge.relationship}</span>
                      </div>
                      <div className="flex items-center justify-between text-white font-bold">
                        <span>
                          {edge.source_type} ({edge.source_id})
                        </span>
                        <span className="text-neutral-500">→</span>
                        <span className="text-teal-400">
                          {edge.target_type} ({edge.target_id})
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-neutral-400 text-xs font-mono">
                No directed provenance path exists between the selected entities.
              </div>
            )}

            <div className="pt-3 border-t border-neutral-800 flex justify-end">
              <button
                type="button"
                onClick={() => setPathExplaining(false)}
                className="px-4 py-2 rounded-xl bg-neutral-800 hover:bg-neutral-700 text-white text-xs font-mono font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
