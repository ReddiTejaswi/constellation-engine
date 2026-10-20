import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import type { DiscoveryReport, EvidenceStatus } from "../types";

const STATUS_COLOR: Record<EvidenceStatus, string> = {
  ESTABLISHED: "#4ade80",
  SUPPORTED: "#60a5fa",
  INFERRED: "#fbbf24",
  HYPOTHESIS: "#c084fc",
  UNKNOWN: "#94a3b8",
};

function layout(nodeIds: string[]): Record<string, { x: number; y: number }> {
  // simple radial layout
  const pos: Record<string, { x: number; y: number }> = {};
  const n = Math.max(nodeIds.length, 1);
  const R = Math.min(360, 120 + n * 14);
  nodeIds.forEach((id, i) => {
    const a = (2 * Math.PI * i) / n;
    pos[id] = { x: 400 + R * Math.cos(a), y: 300 + R * Math.sin(a) };
  });
  return pos;
}

export function Graph({
  report,
  onSelectEdge,
  selectedEdge,
}: {
  report: DiscoveryReport;
  onSelectEdge: (edgeId: string | null) => void;
  selectedEdge: string | null;
}) {
  const { nodes, edges } = useMemo(() => {
    const pos = layout(report.graph.nodes.map((n) => n.id));
    const nodes: Node[] = report.graph.nodes.map((n) => ({
      id: n.id,
      data: { label: `${n.label}\n(${n.type})` },
      position: pos[n.id],
      style: {
        background: "#192031",
        border: "1px solid #273048",
        color: "#e6eaf2",
        borderRadius: 8,
        padding: 8,
        fontSize: 11,
        width: 160,
        whiteSpace: "pre-wrap",
      },
    }));
    const edges: Edge[] = report.graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.relationship,
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 4,
      labelBgStyle: { fill: "#121722", color: "#e6eaf2" },
      labelStyle: { fill: "#e6eaf2", fontSize: 10 },
      style: {
        stroke: STATUS_COLOR[e.status] ?? "#94a3b8",
        strokeWidth: selectedEdge === e.id ? 3 : 1.5,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: STATUS_COLOR[e.status] ?? "#94a3b8",
      },
      animated: e.status === "INFERRED" || e.status === "HYPOTHESIS",
    }));
    return { nodes, edges };
  }, [report, selectedEdge]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      fitView
      onEdgeClick={(_, edge) => onSelectEdge(edge.id)}
      onPaneClick={() => onSelectEdge(null)}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#273048" gap={16} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
