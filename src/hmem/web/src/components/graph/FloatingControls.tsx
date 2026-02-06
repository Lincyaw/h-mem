import { useState } from "react";

interface FloatingControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onLayoutChange: (layout: string) => void;
  currentLayout: string;
}

const layouts = [
  { id: "cose", label: "Force-directed" },
  { id: "circle", label: "Circle" },
  { id: "grid", label: "Grid" },
  { id: "dagre", label: "Hierarchy" },
];

export function FloatingControls({
  onZoomIn,
  onZoomOut,
  onFit,
  onLayoutChange,
  currentLayout,
}: FloatingControlsProps) {
  const [layoutDropdownOpen, setLayoutDropdownOpen] = useState(false);

  return (
    <>
      {/* Zoom controls - top left */}
      <div className="absolute top-4 left-4 flex flex-col gap-1 bg-gray-900/90 rounded-lg border border-gray-700 p-1 backdrop-blur-sm">
        <button
          onClick={onZoomIn}
          className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
          title="Zoom in"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
          </svg>
        </button>
        <button
          onClick={onZoomOut}
          className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
          title="Zoom out"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
          </svg>
        </button>
        <div className="h-px bg-gray-700 my-1" />
        <button
          onClick={onFit}
          className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
          title="Fit to view (F)"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
        </button>
      </div>

      {/* Layout picker - top right */}
      <div className="absolute top-4 right-4">
        <div className="relative">
          <button
            onClick={() => setLayoutDropdownOpen(!layoutDropdownOpen)}
            className="flex items-center gap-2 px-3 py-2 bg-gray-900/90 rounded-lg border border-gray-700 hover:bg-gray-800 transition-colors backdrop-blur-sm"
          >
            <span className="text-sm text-gray-300">
              {layouts.find((l) => l.id === currentLayout)?.label || "Layout"}
            </span>
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {layoutDropdownOpen && (
            <div className="absolute right-0 mt-1 w-40 bg-gray-900 rounded-lg border border-gray-700 shadow-lg z-10 overflow-hidden">
              {layouts.map((layout) => (
                <button
                  key={layout.id}
                  onClick={() => {
                    onLayoutChange(layout.id);
                    setLayoutDropdownOpen(false);
                  }}
                  className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-800 transition-colors ${
                    currentLayout === layout.id ? "text-blue-400 bg-gray-800" : "text-gray-300"
                  }`}
                >
                  {layout.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
