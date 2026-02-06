import type { ElementDefinition } from "cytoscape";

// Node type colors
const nodeColors: Record<string, string> = {
  CONVERSATION: "#64748b",
  EVENT: "#3b82f6",
  FACT: "#eab308",
  PRINCIPLE: "#a855f7",
  SKILL: "#22c55e",
  ENTITY: "#f97316",  // Orange
  PROCESS: "#06b6d4", // Cyan
};

// Node type shapes
const nodeShapes: Record<string, string> = {
  CONVERSATION: "round-rectangle",
  EVENT: "ellipse",
  FACT: "rectangle",
  PRINCIPLE: "diamond",
  SKILL: "hexagon",
  ENTITY: "octagon",
  PROCESS: "star",
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type CyStyle = Array<{ selector: string; style: Record<string, any> }>;

export const cytoscapeStylesheet: CyStyle = [
  // Base node style
  {
    selector: "node",
    style: {
      label: "data(label)",
      "text-valign": "center",
      "text-halign": "center",
      "font-size": "10px",
      color: "#fff",
      "text-wrap": "wrap",
      "text-max-width": "100px",
      "background-color": "#3b82f6",
      width: 60,
      height: 60,
    },
  },
  // Node type specific styles
  ...Object.entries(nodeColors).map(([type, color]) => ({
    selector: `node[nodeType="${type}"]`,
    style: {
      "background-color": color,
      shape: nodeShapes[type] || "ellipse",
    },
  })),
  // Deprecated/superseded nodes
  {
    selector: "node[?isDeprecated]",
    style: {
      opacity: 0.5,
      "border-style": "dashed",
      "border-width": 2,
      "border-color": "#dc2626",
    },
  },
  // Selected node
  {
    selector: "node:selected",
    style: {
      "border-width": 3,
      "border-color": "#fff",
      "border-style": "solid",
    },
  },
  // Edge style
  {
    selector: "edge",
    style: {
      width: 2,
      "line-color": "#4b5563",
      "target-arrow-color": "#4b5563",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      label: "data(relationship)",
      "font-size": "8px",
      color: "#9ca3af",
      "text-rotation": "autorotate",
    },
  },
  // Selected edge
  {
    selector: "edge:selected",
    style: {
      width: 3,
      "line-color": "#60a5fa",
      "target-arrow-color": "#60a5fa",
    },
  },
];

export const cytoscapeLayout = {
  name: "cose",
  animate: true,
  animationDuration: 500,
  nodeRepulsion: () => 8000,
  idealEdgeLength: () => 100,
  nodeOverlap: 20,
  refresh: 20,
  fit: true,
  padding: 30,
  randomize: false,
  componentSpacing: 100,
  edgeElasticity: () => 100,
  nestingFactor: 5,
  gravity: 80,
  numIter: 1000,
  initialTemp: 200,
  coolingFactor: 0.95,
  minTemp: 1.0,
};

export interface GraphNode {
  id: string;
  nodeType: string;
  label: string;
  qValue: number | null;
  isDeprecated: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export function toElements(
  nodes: GraphNode[],
  edges: GraphEdge[]
): ElementDefinition[] {
  const nodeElements: ElementDefinition[] = nodes.map((n) => ({
    data: {
      id: n.id,
      label: n.label.length > 20 ? n.label.slice(0, 20) + "..." : n.label,
      nodeType: n.nodeType,
      qValue: n.qValue,
      isDeprecated: n.isDeprecated,
    },
  }));

  const edgeElements: ElementDefinition[] = edges.map((e, i) => ({
    data: {
      id: `${e.source}-${e.relationship}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      relationship: e.relationship,
    },
  }));

  return [...nodeElements, ...edgeElements];
}
