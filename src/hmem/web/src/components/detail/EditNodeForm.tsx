import { useState, useCallback } from "react";
import { updateNode, deprecateNode } from "../../lib/graphql-client";
import type { Node, NodeType } from "../../lib/graphql-client";
import { useGraphStore } from "../../store/graph-store";

interface EditNodeFormProps {
  node: Node;
  onClose: () => void;
}

export function EditNodeForm({ node, onClose }: EditNodeFormProps) {
  const { selectNode } = useGraphStore();
  const [qValue, setQValue] = useState(
    "qValue" in node ? node.qValue : 0.5
  );
  const [weight, setWeight] = useState(
    "weight" in node ? node.weight : 1.0
  );
  const [deprecateReason, setDeprecateReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = useCallback(async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      const input: { qValue?: number; weight?: number } = {};

      if ("qValue" in node) {
        input.qValue = qValue;
      }
      if ("weight" in node) {
        input.weight = weight;
      }

      await updateNode(node.id, node.nodeType as NodeType, input);

      // Refresh node detail
      await selectNode(node.id);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setIsSubmitting(false);
    }
  }, [node, qValue, weight, selectNode, onClose]);

  const handleDeprecate = useCallback(async () => {
    if (!deprecateReason.trim()) {
      setError("Please provide a reason for deprecation");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await deprecateNode(node.id, deprecateReason);

      // Refresh node detail
      await selectNode(node.id);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setIsSubmitting(false);
    }
  }, [node.id, deprecateReason, selectNode, onClose]);

  const showQValue = "qValue" in node;
  const showWeight = "weight" in node && node.__typename === "FactNode";
  const canDeprecate =
    node.__typename === "PrincipleNode" || node.__typename === "SkillNode";

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg border border-gray-700 w-96 max-w-full">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h3 className="text-lg font-medium">Edit Node</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
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

        {/* Form */}
        <div className="p-4 space-y-4">
          {error && (
            <div className="p-2 bg-red-900/50 border border-red-700 rounded text-sm text-red-200">
              {error}
            </div>
          )}

          <div className="text-xs text-gray-500 font-mono">{node.id}</div>

          {showQValue && (
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Q-Value
              </label>
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={qValue}
                onChange={(e) => setQValue(parseFloat(e.target.value))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                Higher values indicate more useful memories (0-1)
              </p>
            </div>
          )}

          {showWeight && (
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Weight
              </label>
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={weight}
                onChange={(e) => setWeight(parseFloat(e.target.value))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                Fact confidence/relevance (0-1)
              </p>
            </div>
          )}

          {canDeprecate && (
            <div className="pt-4 border-t border-gray-700">
              <label className="block text-sm text-gray-400 mb-1">
                Deprecation Reason
              </label>
              <textarea
                value={deprecateReason}
                onChange={(e) => setDeprecateReason(e.target.value)}
                placeholder="Why is this node no longer relevant?"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-red-500 h-20 resize-none"
              />
              <button
                onClick={handleDeprecate}
                disabled={isSubmitting}
                className="mt-2 w-full px-4 py-2 bg-red-900 hover:bg-red-800 disabled:opacity-50 rounded text-sm"
              >
                {isSubmitting ? "Deprecating..." : "Deprecate Node"}
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSubmitting}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm"
          >
            {isSubmitting ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
