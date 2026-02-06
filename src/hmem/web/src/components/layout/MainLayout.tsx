import { useEffect } from "react";
import { useGraphStore } from "../../store/graph-store";
import { Header } from "./Header";
import { SearchBar } from "../search/SearchBar";
import { GraphCanvas } from "../graph/GraphCanvas";
import { NodeDetailPanel } from "../detail/NodeDetailPanel";

interface MainLayoutProps {
  onHelpClick?: () => void;
}

export function MainLayout({ onHelpClick }: MainLayoutProps) {
  const {
    loadStats,
    error,
    setError,
    leftPanelCollapsed,
    selectedNodeId,
  } = useGraphStore();

  // Load stats on mount
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // Right panel auto-collapses when no node selected
  const rightPanelVisible = selectedNodeId !== null;

  return (
    <div className="flex flex-col h-screen bg-gray-950">
      {/* Header */}
      <Header onHelpClick={onHelpClick} />

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

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel - Search/Browse */}
        <div
          className={`
            bg-gray-900 border-r border-gray-800
            transition-all duration-300 ease-in-out overflow-hidden
            ${leftPanelCollapsed ? "w-12" : "w-80"}
          `}
        >
          {leftPanelCollapsed ? (
            <CollapsedLeftPanel />
          ) : (
            <SearchBar />
          )}
        </div>

        {/* Graph canvas */}
        <div className="flex-1 relative min-w-0">
          <GraphCanvas />
        </div>

        {/* Right panel - Detail */}
        <div
          className={`
            bg-gray-900 border-l border-gray-800
            transition-all duration-300 ease-in-out overflow-hidden
            ${rightPanelVisible ? "w-80" : "w-0"}
          `}
        >
          {rightPanelVisible && <NodeDetailPanel />}
        </div>
      </div>
    </div>
  );
}

// Collapsed left panel with icon strip
function CollapsedLeftPanel() {
  const { setBrowseMode, toggleLeftPanel } = useGraphStore();

  const iconButtons = [
    { icon: "search", title: "Search", action: () => { toggleLeftPanel(); setBrowseMode(false); } },
    { icon: "folder", title: "Browse", action: () => { toggleLeftPanel(); setBrowseMode(true); } },
  ];

  return (
    <div className="flex flex-col items-center pt-2 gap-2">
      {iconButtons.map(({ icon, title, action }) => (
        <button
          key={icon}
          onClick={action}
          className="w-8 h-8 flex items-center justify-center rounded hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          title={title}
        >
          <CollapsedIcon name={icon} />
        </button>
      ))}
    </div>
  );
}

function CollapsedIcon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    search: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
      />
    ),
    folder: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
      />
    ),
  };

  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      {paths[name]}
    </svg>
  );
}
