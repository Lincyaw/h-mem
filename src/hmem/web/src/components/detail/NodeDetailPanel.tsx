import { useGraphStore } from "../../store/graph-store";
import type { Node } from "../../lib/graphql-client";

// Node type colors for headers
const nodeTypeColors: Record<string, string> = {
  CONVERSATION: "border-conversation",
  EVENT: "border-event",
  FACT: "border-fact",
  PRINCIPLE: "border-principle",
  SKILL: "border-skill",
};

function DetailField({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-gray-500 uppercase">{label}</span>
      <span className="text-sm text-gray-200">{value}</span>
    </div>
  );
}

function renderNodeDetail(node: Node) {
  switch (node.__typename) {
    case "ConversationNode":
      return (
        <>
          <DetailField label="Session ID" value={node.sessionId} />
          <DetailField label="Created" value={node.createdAt} />
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

    case "EventNode":
      return (
        <>
          <DetailField
            label="Content"
            value={<p className="whitespace-pre-wrap">{node.content}</p>}
          />
          {node.outcome && <DetailField label="Outcome" value={node.outcome} />}
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
          <DetailField label="Q-Value" value={node.qValue.toFixed(3)} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField label="Created" value={node.createdAt} />
        </>
      );

    case "FactNode":
      return (
        <>
          <DetailField label="Subject" value={node.subject} />
          <DetailField label="Predicate" value={node.predicate} />
          <DetailField label="Object" value={node.object} />
          <DetailField label="Weight" value={node.weight.toFixed(3)} />
          <DetailField label="Version" value={node.version} />
          <DetailField
            label="Superseded"
            value={node.isSuperseded ? "Yes" : "No"}
          />
          <DetailField label="Q-Value" value={node.qValue.toFixed(3)} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField label="Created" value={node.createdAt} />
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
          <DetailField label="Version" value={node.version} />
          <DetailField
            label="Deprecated"
            value={node.isDeprecated ? "Yes" : "No"}
          />
          <DetailField label="Q-Value" value={node.qValue.toFixed(3)} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField label="Created" value={node.createdAt} />
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
              value={<code className="text-xs">{node.triggerPattern}</code>}
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
          <DetailField label="Version" value={node.version} />
          <DetailField
            label="Deprecated"
            value={node.isDeprecated ? "Yes" : "No"}
          />
          <DetailField label="Q-Value" value={node.qValue.toFixed(3)} />
          <DetailField label="Updates" value={node.qUpdateCount} />
          <DetailField label="Created" value={node.createdAt} />
        </>
      );

    default:
      return <div>Unknown node type</div>;
  }
}

export function NodeDetailPanel() {
  const { selectedNodeDetail, selectedNodeId, selectNode } = useGraphStore();

  if (!selectedNodeDetail) {
    return (
      <div className="w-80 bg-gray-900 border-l border-gray-800 p-4">
        <div className="text-gray-500 text-center mt-8">
          <div className="text-2xl mb-2">👈</div>
          <p>Select a node to view details</p>
        </div>
      </div>
    );
  }

  const borderColor =
    nodeTypeColors[selectedNodeDetail.nodeType] || "border-gray-600";

  return (
    <div className="w-80 bg-gray-900 border-l border-gray-800 flex flex-col">
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
        <div className="mt-2 font-mono text-xs text-gray-400 break-all">
          {selectedNodeId}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {renderNodeDetail(selectedNodeDetail)}
      </div>
    </div>
  );
}
