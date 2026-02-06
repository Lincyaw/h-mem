import { useState, useCallback } from "react";
import { useGraphStore } from "../../store/graph-store";
import type { Node } from "../../lib/graphql-client";
import { TypeBrowser } from "../browse/TypeBrowser";

// Node type badge colors
const nodeTypeColors: Record<string, string> = {
  CONVERSATION: "bg-conversation",
  ENTITY: "bg-entity",
  FACT: "bg-fact",
  PROCESS: "bg-process",
  PRINCIPLE: "bg-principle",
  SKILL: "bg-skill",
};

function getNodeLabel(node: Node): string {
  switch (node.__typename) {
    case "ConversationNode":
      return `Session: ${node.sessionId}`;
    case "EntityNode":
      return node.canonicalName;
    case "FactNode":
      return node.slot && node.value
        ? `${node.slot}: ${node.value}`
        : node.value || node.slot || "Fact";
    case "ProcessNode":
      return node.trigger.slice(0, 60) + (node.trigger.length > 60 ? "..." : "");
    case "PrincipleNode":
      return node.content.slice(0, 60) + (node.content.length > 60 ? "..." : "");
    case "SkillNode":
      return node.name;
    default:
      return "Unknown";
  }
}

export function SearchBar() {
  const [query, setQuery] = useState("");
  const { search, searchResults, expandNode, selectNode, isLoading, browseMode, setBrowseMode } =
    useGraphStore();

  const handleSearch = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      search(query);
    },
    [query, search]
  );

  const handleResultClick = useCallback(
    (node: Node) => {
      // Add node to graph and select it
      expandNode(node.id);
      selectNode(node.id);
    },
    [expandNode, selectNode]
  );

  return (
    <div className="w-full h-full flex flex-col">
      {/* Tab bar */}
      <div className="flex border-b border-gray-800">
        <button
          onClick={() => setBrowseMode(false)}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm transition-colors ${
            !browseMode
              ? "text-blue-400 border-b-2 border-blue-400 bg-gray-800/50"
              : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/30"
          }`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          Search
        </button>
        <button
          onClick={() => setBrowseMode(true)}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm transition-colors ${
            browseMode
              ? "text-blue-400 border-b-2 border-blue-400 bg-gray-800/50"
              : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/30"
          }`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          Browse
        </button>
      </div>

      {browseMode ? (
        <TypeBrowser />
      ) : (
        <>
          {/* Search input */}
          <form onSubmit={handleSearch} className="p-4 border-b border-gray-800">
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search memories..."
                className="w-full px-4 py-2 pr-10 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                type="submit"
                disabled={isLoading}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-white disabled:opacity-50"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </button>
            </div>
          </form>

          {/* Search results */}
          <div className="flex-1 overflow-y-auto">
            {searchResults.length === 0 && query && !isLoading && (
              <div className="p-4 text-gray-500 text-center">
                No results found for "{query}"
              </div>
            )}

            {searchResults.length === 0 && !query && (
              <div className="p-4 text-gray-500 text-center text-sm">
                <p className="mb-2">Search for memories by keyword</p>
                <p className="text-xs text-gray-600">
                  Or switch to Browse to explore by type
                </p>
              </div>
            )}

            {searchResults.map((node) => (
              <button
                key={node.id}
                onClick={() => handleResultClick(node)}
                className="w-full p-3 text-left border-b border-gray-800 hover:bg-gray-800 transition-colors"
              >
                <div className="flex items-start gap-2">
                  <span
                    className={`px-2 py-0.5 text-xs rounded ${nodeTypeColors[node.nodeType] || "bg-gray-700"} text-white`}
                  >
                    {node.nodeType}
                  </span>
                  <span className="flex-1 text-sm text-gray-200">
                    {getNodeLabel(node)}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-500 font-mono">
                  {node.id}
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
