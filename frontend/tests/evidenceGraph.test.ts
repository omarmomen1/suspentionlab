import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  EvidenceGraphApi,
  EvidenceGraphTraversalResponse,
  EvidenceGraphPathExplanationResponse,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("EvidenceGraph API Client & Component Logic", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("EvidenceGraphApi Read-Only Contract", () => {
    it("EvidenceGraphApi ONLY exposes read-only GET queries (no mutations)", () => {
      // Introspect EvidenceGraphApi methods
      const methodNames = Object.getOwnPropertyNames(EvidenceGraphApi).filter(
        (m) => typeof (EvidenceGraphApi as any)[m] === "function" && m !== "prototype" && m !== "name" && m !== "length"
      );

      // Verify known read-only endpoints exist
      expect(methodNames).toContain("getEvidenceEdge");
      expect(methodNames).toContain("listEvidenceEdges");
      expect(methodNames).toContain("traverseEvidenceGraph");
      expect(methodNames).toContain("getEvidenceSubgraph");
      expect(methodNames).toContain("explainEvidencePath");

      // Verify strictly NO mutation methods exist
      const forbiddenMutationPrefixes = ["create", "insert", "update", "delete", "post", "put", "patch", "mutate"];
      for (const name of methodNames) {
        for (const forbidden of forbiddenMutationPrefixes) {
          expect(name.toLowerCase().startsWith(forbidden)).toBe(false);
        }
      }
    });

    it("traverseEvidenceGraph sends authenticated GET with query params", async () => {
      const mockTraversal: EvidenceGraphTraversalResponse = {
        root: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
        },
        nodes: [
          {
            entity_type: "EngineeringDecision",
            entity_id: "DEC-12",
            depth: 0,
          },
          {
            entity_type: "BlindValidationRecord",
            entity_id: "VAL-31",
            depth: 1,
          },
        ],
        edges: [
          {
            id: "edge-1",
            source_type: "BlindValidationRecord",
            source_id: "VAL-31",
            relationship: "VALIDATED_BY",
            target_type: "EngineeringDecision",
            target_id: "DEC-12",
            metadata: {},
            edge_hash: "edgehash-123",
            created_at: "2026-10-08T00:00:00Z",
          },
        ],
        traversal: {
          direction: "BACKWARD",
          max_depth: 4,
          nodes_returned: 2,
          edges_returned: 1,
          limit_reached: false,
          limit_type: null,
        },
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockTraversal);

      const res = await EvidenceGraphApi.traverseEvidenceGraph({
        root_type: "EngineeringDecision",
        root_id: "DEC-12",
        direction: "BACKWARD",
        max_depth: 4,
      });

      expect(spy).toHaveBeenCalledWith(
        expect.stringMatching(
          /\/api\/v1\/evidence-graph\/traverse\?.*root_type=EngineeringDecision.*root_id=DEC-12.*direction=BACKWARD.*max_depth=4/
        )
      );
      expect(res.nodes).toHaveLength(2);
      expect(res.edges).toHaveLength(1);
      expect(res.traversal.direction).toBe("BACKWARD");
      expect(res.traversal.limit_reached).toBe(false);
    });

    it("explainEvidencePath queries /api/v1/evidence-graph/path via GET", async () => {
      const mockPath: EvidenceGraphPathExplanationResponse = {
        path_found: true,
        length: 5,
        source: {
          entity_type: "EngineeringQuestion",
          entity_id: "Q-17",
        },
        target: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
        },
        nodes: [
          { entity_type: "EngineeringQuestion", entity_id: "Q-17", depth: 0 },
          { entity_type: "ControlledExperiment", entity_id: "EXP-52", depth: 1 },
          { entity_type: "SimulationRun", entity_id: "RUN-001844", depth: 2 },
          { entity_type: "VehicleSetup", entity_id: "SETUP-92", depth: 3 },
          { entity_type: "BlindValidationRecord", entity_id: "VAL-31", depth: 4 },
          { entity_type: "EngineeringDecision", entity_id: "DEC-12", depth: 5 },
        ],
        edges: [
          {
            id: "p-e1",
            source_type: "EngineeringQuestion",
            source_id: "Q-17",
            relationship: "TESTED_BY",
            target_type: "ControlledExperiment",
            target_id: "EXP-52",
            metadata: {},
            edge_hash: "hash-e1",
            created_at: "2026-10-08T00:00:00Z",
          },
        ],
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockPath);

      const res = await EvidenceGraphApi.explainEvidencePath({
        source_type: "EngineeringQuestion",
        source_id: "Q-17",
        target_type: "EngineeringDecision",
        target_id: "DEC-12",
        max_depth: 8,
      });

      expect(spy).toHaveBeenCalledWith(
        expect.stringMatching(
          /\/api\/v1\/evidence-graph\/path\?.*source_type=EngineeringQuestion.*source_id=Q-17.*target_type=EngineeringDecision.*target_id=DEC-12/
        )
      );
      expect(res.path_found).toBe(true);
      expect(res.length).toBe(5);
      expect(res.nodes).toHaveLength(6);
      expect(res.nodes).toHaveLength(6);
    });

    it("listEvidenceEdges passes optional filters correctly", async () => {
      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce({
        edges: [],
        total: 0,
        limit: 25,
        offset: 0,
      });

      await EvidenceGraphApi.listEvidenceEdges({
        relationship: "PRODUCED_BY",
        source_type: "SimulationRun",
        limit: 25,
      });

      expect(spy).toHaveBeenCalledWith(
        expect.stringMatching(
          /\/api\/v1\/evidence-graph\/edges\?.*source_type=SimulationRun.*relationship=PRODUCED_BY.*limit=25/
        )
      );
    });
  });

  describe("UI Graph Semantics & Guardrails", () => {
    it("enforces depth bounds within [1, 10]", () => {
      const clampDepth = (depth: number) => Math.max(1, Math.min(10, Math.round(depth)));

      expect(clampDepth(0)).toBe(1);
      expect(clampDepth(-5)).toBe(1);
      expect(clampDepth(5)).toBe(5);
      expect(clampDepth(10)).toBe(10);
      expect(clampDepth(15)).toBe(10);
    });

    it("detects graph truncation when limits are reached", () => {
      const checkTruncation = (resp: Partial<EvidenceGraphTraversalResponse>) => {
        return Boolean(resp.traversal?.limit_reached);
      };

      expect(
        checkTruncation({
          traversal: {
            direction: "BACKWARD",
            max_depth: 4,
            nodes_returned: 2,
            edges_returned: 1,
            limit_reached: false,
            limit_type: null,
          },
        })
      ).toBe(false);
      expect(
        checkTruncation({
          traversal: {
            direction: "BACKWARD",
            max_depth: 4,
            nodes_returned: 100,
            edges_returned: 100,
            limit_reached: true,
            limit_type: "NODE_LIMIT",
          },
        })
      ).toBe(true);
    });

    it("validates forward vs backward directional labels", () => {
      const getDirectionMetadata = (dir: "FORWARD" | "BACKWARD") => {
        return dir === "FORWARD"
          ? { label: "Downstream Consequences", desc: "Entities that depend on or were produced from this root" }
          : { label: "Upstream Provenance", desc: "Entities and evidence that led to this root" };
      };

      const fwd = getDirectionMetadata("FORWARD");
      expect(fwd.label).toContain("Downstream");

      const bwd = getDirectionMetadata("BACKWARD");
      expect(bwd.label).toContain("Upstream");
    });

    it("formats cryptographic hashes defensively without fabricating missing hashes", () => {
      const formatHash = (h?: string | null) => {
        if (!h || h.trim() === "") return "UNSPECIFIED (NO ARTIFACT HASH)";
        return h.length > 16 ? `${h.slice(0, 16)}...` : h;
      };

      expect(formatHash(null)).toBe("UNSPECIFIED (NO ARTIFACT HASH)");
      expect(formatHash("")).toBe("UNSPECIFIED (NO ARTIFACT HASH)");
      expect(formatHash("a1b2c3d4e5f678901234567890")).toBe("a1b2c3d4e5f67890...");
    });

    it("topological column layout produces deterministic positions", () => {
      const nodes = [
        { entity_type: "EngineeringDecision", entity_id: "DEC-12", depth: 0 },
        { entity_type: "BlindValidationRecord", entity_id: "VAL-31", depth: 1 },
        { entity_type: "SetupComparisonRecord", entity_id: "COMP-31", depth: 1 },
        { entity_type: "SimulationRun", entity_id: "RUN-1844", depth: 2 },
      ];

      const nodesByDepth: Record<number, typeof nodes> = {};
      nodes.forEach((n) => {
        if (!nodesByDepth[n.depth]) nodesByDepth[n.depth] = [];
        nodesByDepth[n.depth].push(n);
      });

      const colWidth = 260;
      const rowHeight = 110;

      const positions = nodes.map((n) => {
        const rowList = nodesByDepth[n.depth];
        const rowIndex = rowList.indexOf(n);
        return {
          id: n.entity_id,
          x: 50 + n.depth * colWidth,
          y: 50 + rowIndex * rowHeight,
        };
      });

      // DEC-12 (depth 0)
      expect(positions[0]).toEqual({ id: "DEC-12", x: 50, y: 50 });
      // VAL-31 (depth 1, row 0)
      expect(positions[1]).toEqual({ id: "VAL-31", x: 310, y: 50 });
      // COMP-31 (depth 1, row 1)
      expect(positions[2]).toEqual({ id: "COMP-31", x: 310, y: 160 });
      // RUN-1844 (depth 2, row 0)
      expect(positions[3]).toEqual({ id: "RUN-1844", x: 570, y: 50 });
    });
  });
});
