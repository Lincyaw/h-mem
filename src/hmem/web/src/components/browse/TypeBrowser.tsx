import { useState, useCallback } from "react";
import { useGraphStore } from "../../store/graph-store";
import type { Node, NodeType } from "../../lib/graphql-client";
import { listByType } from "../../lib/graphql-client";

// Node type configuration
const nodeTypes: {
  type: NodeType;
  label: string;
  icon: string;
  statsKey: keyof typeof statsKeyMap;
}[] = [
  { type: "ENTITY", label: "Entity", icon: "tag", statsKey: "entities" },
  { type: "FACT", label: "Fact", icon: "clipboard", statsKey: "active_facts" },
  { type: "PROCESS", label: "Process", icon: "cog", statsKey: "active_processes" },
  { type: "SKILL", label: "Skill", icon: "target", statsKey: "active_skills" },
  { type: "PRINCIPLE", label: "Principle", icon: "lightbulb", statsKey: "active_principles" },
  { type: "CONVERSATION", label: "Conversation", icon: "chat", statsKey: "conversations" },
];

const statsKeyMap = {
  entities: true,
  active_facts: true,
  active_processes: true,
  active_skills: true,
  active_principles: true,
  conversations: true,
};

const nodeTypeColors: Record<NodeType, string> = {
  ENTITY: "text-entity",
  FACT: "text-fact",
  PROCESS: "text-process",
  SKILL: "text-skill",
  PRINCIPLE: "text-principle",
  CONVERSATION: "text-conversation",
};

function getNodeLabel(node: Node): string {
  switch (node.__typename) {
    case "ConversationNode":
      return `Session: ${node.sessionId}`;
    case "EntityNode":
      return node.canonicalName;
    case "FactNode":
      return node.slot && node.value
        ? `${node.slot}: ${node.value.slice(0, 40)}`
        : node.value?.slice(0, 40) || node.slot || "Fact";
    case "ProcessNode":
      return node.trigger.slice(0, 40) + (node.trigger.length > 40 ? "..." : "");
    case "PrincipleNode":
      return node.content.slice(0, 40) + (node.content.length > 40 ? "..." : "");
    case "SkillNode":
      return node.name;
    default:
      return "Unknown";
  }
}

interface TypeAccordionProps {
  type: NodeType;
  label: string;
  icon: string;
  count: number;
  isExpanded: boolean;
  onToggle: () => void;
  items: Node[];
  isLoading: boolean;
  onItemClick: (node: Node) => void;
}

function TypeAccordion({
  type,
  label,
  icon,
  count,
  isExpanded,
  onToggle,
  items,
  isLoading,
  onItemClick,
}: TypeAccordionProps) {
  const colorClass = nodeTypeColors[type];

  return (
    <div className="border-b border-gray-800">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800 transition-colors"
      >
        <div className="flex items-center gap-3">
          <TypeIcon name={icon} className={`w-4 h-4 ${colorClass}`} />
          <span className="text-gray-200">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-mono ${colorClass}`}>{count}</span>
          <svg
            className={`w-4 h-4 text-gray-500 transition-transform ${isExpanded ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {isExpanded && (
        <div className="bg-gray-950 border-t border-gray-800">
          {isLoading ? (
            <div className="px-4 py-3 text-gray-500 text-sm">Loading...</div>
          ) : items.length === 0 ? (
            <div className="px-4 py-3 text-gray-500 text-sm">No items</div>
          ) : (
            <div className="max-h-64 overflow-y-auto">
              {items.map((node) => (
                <button
                  key={node.id}
                  onClick={() => onItemClick(node)}
                  className="w-full px-4 py-2 text-left hover:bg-gray-800 transition-colors border-b border-gray-800/50 last:border-b-0"
                >
                  <div className="text-sm text-gray-300 truncate">
                    {getNodeLabel(node)}
                  </div>
                  <div className="text-xs text-gray-600 font-mono truncate mt-0.5">
                    {node.id}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TypeIcon({ name, className }: { name: string; className?: string }) {
  const paths: Record<string, React.ReactNode> = {
    tag: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
      />
    ),
    clipboard: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
      />
    ),
    cog: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
      />
    ),
    target: (
      <>
        <circle cx="12" cy="12" r="10" strokeWidth={2} fill="none" stroke="currentColor" />
        <circle cx="12" cy="12" r="6" strokeWidth={2} fill="none" stroke="currentColor" />
        <circle cx="12" cy="12" r="2" strokeWidth={2} fill="none" stroke="currentColor" />
      </>
    ),
    lightbulb: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
      />
    ),
    chat: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
      />
    ),
  };

  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      {paths[name]}
    </svg>
  );
}

export function TypeBrowser() {
  const { stats, expandNode, selectNode } = useGraphStore();
  const [expandedType, setExpandedType] = useState<NodeType | null>(null);
  const [typeItems, setTypeItems] = useState<Record<NodeType, Node[]>>({
    ENTITY: [],
    FACT: [],
    PROCESS: [],
    SKILL: [],
    PRINCIPLE: [],
    CONVERSATION: [],
  });
  const [loadingType, setLoadingType] = useState<NodeType | null>(null);

  const handleToggle = useCallback(async (type: NodeType) => {
    if (expandedType === type) {
      setExpandedType(null);
      return;
    }

    setExpandedType(type);

    // Load items if not already loaded
    if (typeItems[type].length === 0) {
      setLoadingType(type);
      try {
        const items = await listByType(type, 50);
        setTypeItems((prev) => ({ ...prev, [type]: items }));
      } catch (error) {
        console.error(`Failed to load ${type}:`, error);
      } finally {
        setLoadingType(null);
      }
    }
  }, [expandedType, typeItems]);

  const handleItemClick = useCallback((node: Node) => {
    expandNode(node.id);
    selectNode(node.id);
  }, [expandNode, selectNode]);

  return (
    <div className="flex-1 overflow-y-auto">
      {nodeTypes.map(({ type, label, icon, statsKey }) => (
        <TypeAccordion
          key={type}
          type={type}
          label={label}
          icon={icon}
          count={stats?.[statsKey] ?? 0}
          isExpanded={expandedType === type}
          onToggle={() => handleToggle(type)}
          items={typeItems[type]}
          isLoading={loadingType === type}
          onItemClick={handleItemClick}
        />
      ))}
    </div>
  );
}
