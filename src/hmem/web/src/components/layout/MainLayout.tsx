import { useEffect } from "react";
import { useGraphStore } from "../../store/graph-store";
import { SearchBar } from "../search/SearchBar";
import { GraphCanvas } from "../graph/GraphCanvas";
import { GraphControls } from "../graph/GraphControls";
import { NodeDetailPanel } from "../detail/NodeDetailPanel";

export function MainLayout() {
  const { loadStats, error, setError } = useGraphStore();

  // Load stats on mount
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  return (
    <div className="flex h-screen bg-gray-950">
      {/* Left sidebar - Search */}
      <SearchBar />

      {/* Main content - Graph */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Error banner */}
        {error && (
          <div className="bg-red-900/50 border-b border-red-800 px-4 py-2 flex items-center justify-between">
            <span className="text-red-200 text-sm">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-red-300 hover:text-white"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        )}

        {/* Controls bar */}
        <GraphControls />

        {/* Graph canvas */}
        <div className="flex-1 relative">
          <GraphCanvas />
        </div>
      </div>

      {/* Right sidebar - Detail panel */}
      <NodeDetailPanel />
    </div>
  );
}
