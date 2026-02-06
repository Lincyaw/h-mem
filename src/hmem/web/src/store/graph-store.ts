import { create } from "zustand";
import type { GraphNode, GraphEdge, Node, Stats } from "../lib/graphql-client";
import * as api from "../lib/graphql-client";

interface GraphState {
  // Graph data
  nodes: Map<string, GraphNode>;
  edges: GraphEdge[];

  // UI state
  selectedNodeId: string | null;
  selectedNodeDetail: Node | null;
  searchResults: Node[];
  stats: Stats | null;
  isLoading: boolean;
  error: string | null;

  // Panel state
  leftPanelCollapsed: boolean;
  browseMode: boolean; // false = search, true = browse

  // Actions
  search: (query: string) => Promise<void>;
  expandNode: (nodeId: string) => Promise<void>;
  selectNode: (nodeId: string | null) => Promise<void>;
  loadStats: () => Promise<void>;
  clearGraph: () => void;
  setError: (error: string | null) => void;
  toggleLeftPanel: () => void;
  setBrowseMode: (browse: boolean) => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  // Initial state
  nodes: new Map(),
  edges: [],
  selectedNodeId: null,
  selectedNodeDetail: null,
  searchResults: [],
  stats: null,
  isLoading: false,
  error: null,

  // Panel state
  leftPanelCollapsed: false,
  browseMode: false,

  // Search for nodes
  search: async (query: string) => {
    if (!query.trim()) {
      set({ searchResults: [] });
      return;
    }

    set({ isLoading: true, error: null });
    try {
      const results = await api.search(query, undefined, 20);
      set({ searchResults: results });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ isLoading: false });
    }
  },

  // Expand a node's neighborhood (lazy loading)
  expandNode: async (nodeId: string) => {
    set({ isLoading: true, error: null });
    try {
      const graphData = await api.expand(nodeId, "BOTH", 1);

      set((state) => {
        // Merge new nodes (dedup by ID)
        const newNodes = new Map(state.nodes);
        for (const node of graphData.nodes) {
          if (!newNodes.has(node.id)) {
            newNodes.set(node.id, node);
          }
        }

        // Merge new edges (dedup by source-relationship-target)
        const existingEdgeKeys = new Set(
          state.edges.map((e) => `${e.source}-${e.relationship}-${e.target}`)
        );
        const newEdges = [...state.edges];
        for (const edge of graphData.edges) {
          const key = `${edge.source}-${edge.relationship}-${edge.target}`;
          if (!existingEdgeKeys.has(key)) {
            existingEdgeKeys.add(key);
            newEdges.push(edge);
          }
        }

        return { nodes: newNodes, edges: newEdges };
      });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ isLoading: false });
    }
  },

  // Select a node and load its detail
  selectNode: async (nodeId: string | null) => {
    if (!nodeId) {
      set({ selectedNodeId: null, selectedNodeDetail: null });
      return;
    }

    set({ selectedNodeId: nodeId, isLoading: true, error: null });
    try {
      const detail = await api.getNodeDetail(nodeId);
      set({ selectedNodeDetail: detail });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ isLoading: false });
    }
  },

  // Load stats
  loadStats: async () => {
    try {
      const stats = await api.getStats();
      set({ stats });
    } catch (e) {
      // Stats are optional, don't show error
      console.error("Failed to load stats:", e);
    }
  },

  // Clear the graph
  clearGraph: () => {
    set({
      nodes: new Map(),
      edges: [],
      selectedNodeId: null,
      selectedNodeDetail: null,
    });
  },

  // Set error
  setError: (error: string | null) => {
    set({ error });
  },

  // Toggle left panel collapsed state
  toggleLeftPanel: () => {
    set((state) => ({ leftPanelCollapsed: !state.leftPanelCollapsed }));
  },

  // Set browse mode
  setBrowseMode: (browse: boolean) => {
    set({ browseMode: browse });
  },
}));
