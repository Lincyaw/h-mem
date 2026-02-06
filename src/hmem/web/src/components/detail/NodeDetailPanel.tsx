import { useState, useCallback, useEffect } from "react";
import { useGraphStore } from "../../store/graph-store";
import type { Node } from "../../lib/graphql-client";
import { getLineage } from "../../lib/graphql-client";
import { EditNodeForm } from "./EditNodeForm";

// Node type colors for headers
const nodeTypeColors: Record<string, string> = {
  CONVERSATION: "border-conversation",
  ENTITY: "border-entity",
  FACT: "border-fact",
  PROCESS: "border-process",
  PRINCIPLE: "border-principle",
  SKILL: "border-skill",
};

const nodeTypeTextColors: Record<string, string> = {
  CONVERSATION: "text-conversation",
  ENTITY: "text-entity",
  FACT: "text-fact",
  PROCESS: "text-process",
  PRINCIPLE: "text-principle",
  SKILL: "text-skill",
};

interface CollapsibleSectionProps {
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function CollapsibleSection({
  title,
  badge,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-gray-800 last:border-b-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg
            className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-sm font-medium text-gray-200">{title}</span>
        </div>
        {badge && (
          <span className="text-xs text-gray-500">{badge}</span>
        )}
      </button>
      {isOpen && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

function DetailField({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex flex-col gap-1 mb-3 last:mb-0">
      <span className="text-xs text-gray-500 uppercase">{label}</span>
      <span className="text-sm text-gray-200">{value}</span>
    </div>
  );
}

function QValueBar({ value }: { value: number }) {
  const percentage = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-sm font-mono text-gray-300">{value.toFixed(2)}</span>
    </div>
  );
}

function renderNodeProperties(node: Node) {
  switch (node.__typename) {
    case "ConversationNode":
      return (
        <>
          <DetailField label="Session ID" value={node.sessionId} />
          <DetailField label="Created" value={formatDate(node.createdAt)} />
          {node.metadataJson && (
            <DetailField
              label="Metadata"
              value={
                <pre className="text-xs bg-gray-800 p-2 rounded overflow-x-auto">
                  {JSON.stringify(JSON.parse(node.metadataJson), null, 2)}
                </pre>
              }
            />
          )}
        </>
      );

    case "EntityNode":
      return (
        <>
          <DetailField label="Name" value={node.canonicalName} />
          <DetailField label="Type" value={node.entityType} />
          {node.aliases && node.aliases.length > 0 && (
            <DetailField
              label="Aliases"
              value={
                <div className="flex flex-wrap gap-1">
                  {node.aliases.map((alias: string) => (
                    <span
                      key={alias}
                      className="px-2 py-0.5 bg-gray-700 rounded text-xs"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              }
            />
          )}
          <DetailField
            label="Needs Resolution"
            value={node.needsResolution ? "Yes" : "No"}
          />
          <DetailField label="Created" value={formatDate(node.createdAt)} />
          {node.updatedAt && <DetailField label="Updated" value={formatDate(node.updatedAt)} />}
        </>
      );

    case "FactNode":
      return (
        <>
          {node.entityId && <DetailField label="Entity ID" value={node.entityId} />}
          {node.slot && <DetailField label="Slot" value={node.slot} />}
          {node.value && (
            <DetailField
              label="Value"
              value={<p className="whitespace-pre-wrap">{node.value}</p>}
            />
          )}
          {node.cardinality && <DetailField label="Cardinality" value={node.cardinality} />}
          {node.sourceRole && <DetailField label="Source" value={node.sourceRole} />}
          {node.importance !== null && <DetailField label="Importance" value={node.importance} />}
          {node.confidence !== null && (
            <DetailField label="Confidence" value={node.confidence.toFixed(3)} />
          )}
          <DetailField label="Q-Value" value={<QValueBar value={node.qValue} />} />
          <DetailField label="Version" value={node.version} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField
            label="Superseded"
            value={node.isSuperseded ? "Yes" : "No"}
          />
          <DetailField label="Created" value={formatDate(node.createdAt)} />
          {node.updatedAt && <DetailField label="Updated" value={formatDate(node.updatedAt)} />}
        </>
      );

    case "ProcessNode":
      return (
        <>
          <DetailField
            label="Trigger"
            value={<p className="whitespace-pre-wrap">{node.trigger}</p>}
          />
          <DetailField
            label="Action"
            value={<p className="whitespace-pre-wrap">{node.action}</p>}
          />
          {node.outcome && (
            <DetailField
              label="Outcome"
              value={<p className="whitespace-pre-wrap">{node.outcome}</p>}
            />
          )}
          <DetailField label="Confidence" value={node.confidence.toFixed(3)} />
          <DetailField label="Q-Value" value={<QValueBar value={node.qValue} />} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField
            label="Deprecated"
            value={node.isDeprecated ? "Yes" : "No"}
          />
          <DetailField label="Created" value={formatDate(node.createdAt)} />
          {node.updatedAt && <DetailField label="Updated" value={formatDate(node.updatedAt)} />}
        </>
      );

    case "PrincipleNode":
      return (
        <>
          <DetailField
            label="Content"
            value={<p className="whitespace-pre-wrap">{node.content}</p>}
          />
          <DetailField label="Evidence Count" value={node.evidenceCount} />
          <DetailField label="Confidence" value={node.confidence.toFixed(3)} />
          <DetailField label="Q-Value" value={<QValueBar value={node.qValue} />} />
          <DetailField label="Version" value={node.version} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField
            label="Deprecated"
            value={node.isDeprecated ? "Yes" : "No"}
          />
          <DetailField label="Created" value={formatDate(node.createdAt)} />
        </>
      );

    case "SkillNode":
      return (
        <>
          <DetailField label="Name" value={node.name} />
          {node.description && (
            <DetailField label="Description" value={node.description} />
          )}
          {node.triggerPattern && (
            <DetailField
              label="Trigger Pattern"
              value={<code className="text-xs bg-gray-800 px-1 rounded">{node.triggerPattern}</code>}
            />
          )}
          {node.actionTemplate && (
            <DetailField
              label="Action Template"
              value={<pre className="text-xs bg-gray-800 p-2 rounded overflow-x-auto whitespace-pre-wrap">{node.actionTemplate}</pre>}
            />
          )}
          {node.tags && node.tags.length > 0 && (
            <DetailField
              label="Tags"
              value={
                <div className="flex flex-wrap gap-1">
                  {node.tags.map((tag: string) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 bg-gray-700 rounded text-xs"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              }
            />
          )}
          <DetailField label="Q-Value" value={<QValueBar value={node.qValue} />} />
          <DetailField label="Version" value={node.version} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField
            label="Deprecated"
            value={node.isDeprecated ? "Yes" : "No"}
          />
          <DetailField label="Created" value={formatDate(node.createdAt)} />
          {node.updatedAt && <DetailField label="Updated" value={formatDate(node.updatedAt)} />}
        </>
      );

    default:
      return <div>Unknown node type</div>;
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours === 0) {
      const diffMins = Math.floor(diffMs / (1000 * 60));
      return diffMins <= 1 ? "just now" : `${diffMins} min ago`;
    }
    return `${diffHours} hour${diffHours > 1 ? "s" : ""} ago`;
  } else if (diffDays === 1) {
    return "yesterday";
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else {
    return date.toLocaleDateString();
  }
}

function getNodeLabel(node: Node): string {
  switch (node.__typename) {
    case "ConversationNode":
      return `Session: ${node.sessionId}`;
    case "EntityNode":
      return node.canonicalName;
    case "FactNode":
      return node.slot || node.value?.slice(0, 30) || "Fact";
    case "ProcessNode":
      return node.trigger.slice(0, 30);
    case "PrincipleNode":
      return node.content.slice(0, 30);
    case "SkillNode":
      return node.name;
    default:
      return "Unknown";
  }
}

interface LineageNodeProps {
  node: Node;
  isCurrentNode: boolean;
  onNodeClick: (nodeId: string) => void;
}

function LineageNode({ node, isCurrentNode, onNodeClick }: LineageNodeProps) {
  const colorClass = nodeTypeTextColors[node.nodeType] || "text-gray-400";

  return (
    <button
      onClick={() => onNodeClick(node.id)}
      className={`flex items-center gap-2 w-full text-left px-2 py-1.5 rounded transition-colors ${
        isCurrentNode ? "bg-blue-900/30 border border-blue-700" : "hover:bg-gray-800"
      }`}
    >
      <span className={`text-xs ${colorClass}`}>{node.nodeType}</span>
      <span className="text-sm text-gray-300 truncate">{getNodeLabel(node)}</span>
    </button>
  );
}

export function NodeDetailPanel() {
  const { selectedNodeDetail, selectedNodeId, selectNode, expandNode } = useGraphStore();
  const [lineage, setLineage] = useState<Node[]>([]);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);

  // Load lineage when node changes
  useEffect(() => {
    if (selectedNodeId) {
      setLineageLoading(true);
      getLineage(selectedNodeId, 5)
        .then(setLineage)
        .catch(console.error)
        .finally(() => setLineageLoading(false));
    } else {
      setLineage([]);
    }
  }, [selectedNodeId]);

  const handleExpandClick = useCallback(() => {
    if (selectedNodeId) {
      expandNode(selectedNodeId);
    }
  }, [selectedNodeId, expandNode]);

  const handleLineageNodeClick = useCallback((nodeId: string) => {
    expandNode(nodeId);
    selectNode(nodeId);
  }, [expandNode, selectNode]);

  const handleCopyId = useCallback(() => {
    if (selectedNodeId) {
      navigator.clipboard.writeText(selectedNodeId);
    }
  }, [selectedNodeId]);

  if (!selectedNodeDetail) {
    return null;
  }

  const borderColor =
    nodeTypeColors[selectedNodeDetail.nodeType] || "border-gray-600";
  const canDeprecate =
    selectedNodeDetail.__typename === "PrincipleNode" ||
    selectedNodeDetail.__typename === "SkillNode" ||
    selectedNodeDetail.__typename === "ProcessNode";

  return (
    <div className="w-80 flex flex-col h-full">
      {/* Header */}
      <div
        className={`p-4 border-b border-gray-800 border-l-4 ${borderColor}`}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500 uppercase">
            {selectedNodeDetail.nodeType}
          </span>
          <button
            onClick={() => selectNode(null)}
            className="text-gray-500 hover:text-white"
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
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className="font-mono text-xs text-gray-400 break-all flex-1">
            {selectedNodeId}
          </span>
          <button
            onClick={handleCopyId}
            className="p-1 text-gray-500 hover:text-white rounded hover:bg-gray-800"
            title="Copy ID"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Properties section */}
        <CollapsibleSection title="Properties" defaultOpen={true}>
          {renderNodeProperties(selectedNodeDetail)}
        </CollapsibleSection>

        {/* Lineage section */}
        <CollapsibleSection
          title="Lineage"
          badge={lineageLoading ? "Loading..." : `${lineage.length} nodes`}
          defaultOpen={false}
        >
          {lineageLoading ? (
            <div className="text-sm text-gray-500">Loading lineage...</div>
          ) : lineage.length === 0 ? (
            <div className="text-sm text-gray-500">No lineage found</div>
          ) : (
            <div className="space-y-1">
              {lineage.map((node, index) => (
                <div key={node.id}>
                  {index > 0 && (
                    <div className="flex items-center gap-2 pl-4 py-1">
                      <svg className="w-3 h-3 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                      </svg>
                      <span className="text-xs text-gray-600">GENERATES</span>
                    </div>
                  )}
                  <LineageNode
                    node={node}
                    isCurrentNode={node.id === selectedNodeId}
                    onNodeClick={handleLineageNodeClick}
                  />
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        {/* Actions section */}
        <CollapsibleSection title="Actions" defaultOpen={false}>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={handleExpandClick}
              className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
              Expand
            </button>
            <button
              onClick={() => setIsEditOpen(true)}
              className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Edit
            </button>
          </div>
          {canDeprecate && (
            <p className="mt-2 text-xs text-gray-600">
              Use Edit to deprecate this node with a reason
            </p>
          )}
        </CollapsibleSection>
      </div>

      {/* Edit modal */}
      {isEditOpen && (
        <EditNodeForm
          node={selectedNodeDetail}
          onClose={() => setIsEditOpen(false)}
        />
      )}
    </div>
  );
}
