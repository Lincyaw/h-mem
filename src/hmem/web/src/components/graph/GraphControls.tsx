import { useGraphStore } from "../../store/graph-store";

export function GraphControls() {
  const { nodes, edges, clearGraph, isLoading, stats } = useGraphStore();

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-gray-900 border-b border-gray-800 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-gray-400">Nodes:</span>
        <span className="font-mono text-blue-400">{nodes.size}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-gray-400">Edges:</span>
        <span className="font-mono text-blue-400">{edges.length}</span>
      </div>

      {stats && (
        <>
          <div className="h-4 w-px bg-gray-700" />
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Total Events:</span>
            <span className="font-mono text-event">{stats.events}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Facts:</span>
            <span className="font-mono text-fact">{stats.active_facts}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Principles:</span>
            <span className="font-mono text-principle">
              {stats.active_principles}
            </span>
          </div>
        </>
      )}

      <div className="flex-1" />

      {isLoading && (
        <div className="flex items-center gap-2 text-yellow-400">
          <svg
            className="animate-spin h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Loading...</span>
        </div>
      )}

      <button
        onClick={clearGraph}
        disabled={nodes.size === 0}
        className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded border border-gray-700"
      >
        Clear Graph
      </button>
    </div>
  );
}
