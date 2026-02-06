import type { ElementDefinition } from "cytoscape";

// Node type colors
export const nodeColors: Record<string, string> = {
  CONVERSATION: "#64748b",
  ENTITY: "#f97316",  // Orange
  FACT: "#eab308",
  PROCESS: "#06b6d4", // Cyan
  PRINCIPLE: "#a855f7",
  SKILL: "#22c55e",
};

// Node type shapes
export const nodeShapes: Record<string, string> = {
  CONVERSATION: "round-rectangle",
  ENTITY: "octagon",
  FACT: "rectangle",
  PROCESS: "star",
  PRINCIPLE: "diamond",
  SKILL: "hexagon",
};

// Node type labels for legend
export const nodeTypeLabels: Record<string, string> = {
  CONVERSATION: "Conversation",
  ENTITY: "Entity",
  FACT: "Fact",
  PROCESS: "Process",
  PRINCIPLE: "Principle",
  SKILL: "Skill",
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
      "font-size": "11px",
      color: "#fff",
      "text-wrap": "wrap",
      "text-max-width": "120px",
      "background-color": "#3b82f6",
      width: 80,
      height: 80,
      "text-outline-color": "#000",
      "text-outline-width": 1,
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
      "border-width": 3,
      "border-color": "#dc2626",
    },
  },
  // Selected node
  {
    selector: "node:selected",
    style: {
      "border-width": 4,
      "border-color": "#fff",
      "border-style": "solid",
      "box-shadow": "0 0 20px #60a5fa",
    },
  },
  // Hover effect (handled via js mouseover)
  {
    selector: "node.hover",
    style: {
      "border-width": 2,
      "border-color": "#60a5fa",
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
      "font-size": "9px",
      color: "#9ca3af",
      "text-rotation": "autorotate",
      "text-background-color": "#111827",
      "text-background-opacity": 0.8,
      "text-background-padding": "2px",
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
