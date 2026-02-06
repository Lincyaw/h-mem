import { useState } from "react";
import { nodeColors, nodeShapes, nodeTypeLabels } from "../../lib/cytoscape-config";

const shapeSymbols: Record<string, string> = {
  "round-rectangle": "▭",
  octagon: "◇",
  rectangle: "▢",
  star: "☆",
  diamond: "◆",
  hexagon: "⬡",
};

export function GraphLegend() {
  const [isVisible, setIsVisible] = useState(true);

  if (!isVisible) {
    return (
      <button
        onClick={() => setIsVisible(true)}
        className="absolute bottom-4 left-4 px-3 py-1.5 bg-gray-900/90 rounded-lg border border-gray-700 text-sm text-gray-400 hover:text-white transition-colors backdrop-blur-sm"
      >
        Show Legend
      </button>
    );
  }

  return (
    <div className="absolute bottom-4 left-4 right-4 flex items-center justify-center gap-6 px-4 py-2 bg-gray-900/90 rounded-lg border border-gray-700 backdrop-blur-sm">
      {Object.entries(nodeTypeLabels).map(([type, label]) => (
        <div key={type} className="flex items-center gap-2">
          <span
            className="text-lg"
            style={{ color: nodeColors[type] }}
          >
            {shapeSymbols[nodeShapes[type]] || "●"}
          </span>
          <span className="text-xs text-gray-400">{label}</span>
        </div>
      ))}
      <button
        onClick={() => setIsVisible(false)}
        className="ml-4 p-1 text-gray-500 hover:text-white rounded hover:bg-gray-800"
        title="Hide legend"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}
