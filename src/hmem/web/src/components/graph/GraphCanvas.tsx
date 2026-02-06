import { useCallback, useRef, useEffect, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import type Cytoscape from "cytoscape";

import { useGraphStore } from "../../store/graph-store";
import {
  cytoscapeStylesheet,
  cytoscapeLayout,
  toElements,
} from "../../lib/cytoscape-config";
import { FloatingControls } from "./FloatingControls";
import { GraphLegend } from "./GraphLegend";

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  label: string;
  nodeType: string;
  qValue: number | null;
}

export function GraphCanvas() {
  const cyRef = useRef<Cytoscape.Core | null>(null);
  const layoutRef = useRef<Cytoscape.Layouts | null>(null);
  const mountedRef = useRef(true);
  const { nodes, edges, selectedNodeId, expandNode, selectNode } =
    useGraphStore();
  const [currentLayout, setCurrentLayout] = useState("cose");
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    x: 0,
    y: 0,
    label: "",
    nodeType: "",
    qValue: null,
  });

  const elements = toElements(Array.from(nodes.values()), edges);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      // Stop any running layout
      if (layoutRef.current) {
        layoutRef.current.stop();
        layoutRef.current = null;
      }
      // Destroy cytoscape instance
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, []);

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

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    if (cyRef.current) {
      cyRef.current.zoom(cyRef.current.zoom() * 1.2);
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    if (cyRef.current) {
      cyRef.current.zoom(cyRef.current.zoom() / 1.2);
    }
  }, []);

  const handleFit = useCallback(() => {
    if (cyRef.current) {
      cyRef.current.fit(undefined, 30);
    }
  }, []);

  const runLayout = useCallback((cy: Cytoscape.Core, layoutName: string) => {
    if (!mountedRef.current) return;

    // Stop previous layout if running
    if (layoutRef.current) {
      layoutRef.current.stop();
    }

    const layoutOptions = getLayoutOptions(layoutName);
    const layout = cy.layout(layoutOptions);
    layoutRef.current = layout;
    layout.run();
  }, []);

  const handleLayoutChange = useCallback((layoutName: string) => {
    setCurrentLayout(layoutName);
    if (cyRef.current) {
      runLayout(cyRef.current, layoutName);
    }
  }, [runLayout]);

  // Set up event handlers when cy is ready
  const handleCy = useCallback(
    (cy: Cytoscape.Core) => {
      if (!mountedRef.current) return;

      cyRef.current = cy;

      // Remove existing listeners
      cy.removeListener("tap", "node");
      cy.removeListener("dbltap", "node");
      cy.removeListener("tap"); // Background tap
      cy.removeListener("mouseover", "node");
      cy.removeListener("mouseout", "node");

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

      // Hover for tooltip
      cy.on("mouseover", "node", (evt) => {
        if (!mountedRef.current) return;
        const node = evt.target;
        const data = node.data();
        const pos = node.renderedPosition();
        node.addClass("hover");
        setTooltip({
          visible: true,
          x: pos.x,
          y: pos.y - 50,
          label: data.label,
          nodeType: data.nodeType,
          qValue: data.qValue,
        });
      });

      cy.on("mouseout", "node", (evt) => {
        if (!mountedRef.current) return;
        evt.target.removeClass("hover");
        setTooltip((prev) => ({ ...prev, visible: false }));
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
    if (cyRef.current && elements.length > 0 && mountedRef.current) {
      // Small delay to ensure elements are rendered
      const timer = setTimeout(() => {
        if (cyRef.current && mountedRef.current) {
          runLayout(cyRef.current, currentLayout);
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [elements.length, currentLayout, runLayout]);

  if (elements.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <div className="text-4xl mb-4">🧠</div>
          <p className="font-medium mb-2">Start exploring your memory</p>
          <p className="text-sm text-gray-600 mb-1">
            Search for concepts or entities
          </p>
          <p className="text-sm text-gray-600 mb-1">
            Browse by type in the left panel
          </p>
          <p className="text-sm text-gray-600">
            Double-click nodes to expand
          </p>
          <p className="text-xs text-gray-700 mt-4">
            Keyboard: Ctrl+K to search, ? for help
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      <CytoscapeComponent
        elements={elements}
        stylesheet={cytoscapeStylesheet}
        layout={{ name: "preset" }}
        cy={handleCy}
        className="cy-container"
        style={{ width: "100%", height: "100%" }}
      />
      <FloatingControls
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFit={handleFit}
        onLayoutChange={handleLayoutChange}
        currentLayout={currentLayout}
      />
      <GraphLegend />

      {/* Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute pointer-events-none z-10 px-3 py-2 bg-gray-900 rounded-lg border border-gray-700 shadow-lg"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: "translate(-50%, -100%)",
          }}
        >
          <div className="text-xs text-gray-500 uppercase mb-1">{tooltip.nodeType}</div>
          <div className="text-sm text-white font-medium">{tooltip.label}</div>
          {tooltip.qValue !== null && (
            <div className="text-xs text-gray-400 mt-1">Q: {tooltip.qValue.toFixed(2)}</div>
          )}
        </div>
      )}
    </div>
  );
}

// Layout options for different layout types
function getLayoutOptions(layoutName: string): Cytoscape.LayoutOptions {
  const baseOptions = {
    animate: true,
    animationDuration: 500,
    fit: true,
    padding: 30,
  };

  switch (layoutName) {
    case "circle":
      return {
        name: "circle",
        ...baseOptions,
      };
    case "grid":
      return {
        name: "grid",
        ...baseOptions,
        rows: undefined,
        cols: undefined,
      };
    case "dagre":
      return {
        name: "dagre",
        ...baseOptions,
        rankDir: "TB",
        nodeSep: 50,
        rankSep: 100,
      } as Cytoscape.LayoutOptions;
    case "cose":
    default:
      return cytoscapeLayout;
  }
}
