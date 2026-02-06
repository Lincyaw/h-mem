import { useCallback, useRef, useEffect } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import type Cytoscape from "cytoscape";

import { useGraphStore } from "../../store/graph-store";
import {
  cytoscapeStylesheet,
  cytoscapeLayout,
  toElements,
} from "../../lib/cytoscape-config";

export function GraphCanvas() {
  const cyRef = useRef<Cytoscape.Core | null>(null);
  const { nodes, edges, selectedNodeId, expandNode, selectNode } =
    useGraphStore();

  const elements = toElements(Array.from(nodes.values()), edges);

  // Handle node click (select)
  const handleNodeClick = useCallback(
    (nodeId: string) => {
      selectNode(nodeId);
    },
    [selectNode]
  );

  // Handle double-click (expand)
  const handleNodeDoubleClick = useCallback(
    (nodeId: string) => {
      expandNode(nodeId);
    },
    [expandNode]
  );

  // Set up event handlers when cy is ready
  const handleCy = useCallback(
    (cy: Cytoscape.Core) => {
      cyRef.current = cy;

      // Remove existing listeners
      cy.removeListener("tap", "node");
      cy.removeListener("dbltap", "node");
      cy.removeListener("tap"); // Background tap

      // Single click to select
      cy.on("tap", "node", (evt) => {
        const nodeId = evt.target.id();
        handleNodeClick(nodeId);
      });

      // Double-click to expand
      cy.on("dbltap", "node", (evt) => {
        const nodeId = evt.target.id();
        handleNodeDoubleClick(nodeId);
      });

      // Click background to deselect
      cy.on("tap", (evt) => {
        if (evt.target === cy) {
          selectNode(null);
        }
      });
    },
    [handleNodeClick, handleNodeDoubleClick, selectNode]
  );

  // Highlight selected node
  useEffect(() => {
    if (cyRef.current && selectedNodeId) {
      const cy = cyRef.current;
      cy.nodes().removeClass("selected");
      const node = cy.getElementById(selectedNodeId);
      if (node.length) {
        node.addClass("selected");
      }
    }
  }, [selectedNodeId]);

  // Run layout when elements change
  useEffect(() => {
    if (cyRef.current && elements.length > 0) {
      const layout = cyRef.current.layout(cytoscapeLayout);
      layout.run();
    }
  }, [elements.length]);

  if (elements.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <div className="text-4xl mb-4">🔍</div>
          <p>Search for nodes to visualize the graph</p>
          <p className="text-sm mt-2 text-gray-600">
            Double-click nodes to expand their connections
          </p>
        </div>
      </div>
    );
  }

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={cytoscapeStylesheet}
      layout={cytoscapeLayout}
      cy={handleCy}
      className="cy-container"
      style={{ width: "100%", height: "100%" }}
    />
  );
}
