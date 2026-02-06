interface HelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const shortcuts = [
  { keys: ["Ctrl", "K"], description: "Focus search" },
  { keys: ["?"], description: "Show this help" },
  { keys: ["Esc"], description: "Deselect / close panels" },
  { keys: ["F"], description: "Fit graph to view" },
  { keys: ["E"], description: "Expand selected node" },
  { keys: ["Shift", "C"], description: "Clear graph" },
  { keys: ["1-6"], description: "Quick switch to browse type" },
];

const interactions = [
  { action: "Single click", description: "Select node and show details" },
  { action: "Double click", description: "Expand node connections" },
  { action: "Drag canvas", description: "Pan the view" },
  { action: "Scroll", description: "Zoom in/out" },
  { action: "Drag node", description: "Reposition node" },
];

export function HelpModal({ isOpen, onClose }: HelpModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 rounded-lg border border-gray-700 w-[480px] max-w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">Keyboard Shortcuts</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white rounded hover:bg-gray-800"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          {/* Keyboard shortcuts */}
          <div className="mb-6">
            <h3 className="text-sm font-medium text-gray-400 mb-3 uppercase">Keyboard</h3>
            <div className="space-y-2">
              {shortcuts.map((shortcut, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">{shortcut.description}</span>
                  <div className="flex items-center gap-1">
                    {shortcut.keys.map((key, j) => (
                      <span key={j}>
                        <kbd className="px-2 py-1 bg-gray-800 rounded text-xs font-mono text-gray-200 border border-gray-700">
                          {key}
                        </kbd>
                        {j < shortcut.keys.length - 1 && (
                          <span className="text-gray-600 mx-1">+</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Mouse interactions */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 mb-3 uppercase">Mouse Interactions</h3>
            <div className="space-y-2">
              {interactions.map((interaction, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">{interaction.description}</span>
                  <span className="text-xs text-gray-500">{interaction.action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 text-center">
          <p className="text-xs text-gray-500">
            Press <kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs font-mono border border-gray-700">?</kbd> anytime to show this help
          </p>
        </div>
      </div>
    </div>
  );
}
