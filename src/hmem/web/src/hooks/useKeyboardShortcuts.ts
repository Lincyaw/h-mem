import { useEffect, useCallback } from "react";
import { useGraphStore } from "../store/graph-store";

interface KeyboardShortcutHandlers {
  onFit?: () => void;
  onToggleHelp?: () => void;
}

export function useKeyboardShortcuts(handlers: KeyboardShortcutHandlers = {}) {
  const {
    selectedNodeId,
    selectNode,
    expandNode,
    clearGraph,
    setBrowseMode,
    toggleLeftPanel,
  } = useGraphStore();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Ignore if typing in an input
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      // Ctrl/Cmd + K: Focus search
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setBrowseMode(false);
        toggleLeftPanel(); // Open if collapsed
        // Focus the search input after a short delay
        setTimeout(() => {
          const searchInput = document.querySelector<HTMLInputElement>(
            'input[placeholder="Search memories..."]'
          );
          searchInput?.focus();
        }, 100);
        return;
      }

      // ?: Show help
      if (e.key === "?" && !e.shiftKey) {
        e.preventDefault();
        handlers.onToggleHelp?.();
        return;
      }

      // Escape: Deselect / close panels
      if (e.key === "Escape") {
        e.preventDefault();
        selectNode(null);
        return;
      }

      // Delete/Backspace: Remove selected node from graph (not from database)
      if ((e.key === "Delete" || e.key === "Backspace") && selectedNodeId) {
        e.preventDefault();
        // Could implement node removal from graph view here
        return;
      }

      // F: Fit graph to view
      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        handlers.onFit?.();
        return;
      }

      // E: Expand selected node
      if ((e.key === "e" || e.key === "E") && selectedNodeId) {
        e.preventDefault();
        expandNode(selectedNodeId);
        return;
      }

      // C: Clear graph
      if ((e.key === "c" || e.key === "C") && e.shiftKey) {
        e.preventDefault();
        clearGraph();
        return;
      }

      // 1-6: Switch to browse mode and expand that type
      if (e.key >= "1" && e.key <= "6") {
        e.preventDefault();
        setBrowseMode(true);
        // Could auto-expand the nth type accordion
        return;
      }
    },
    [
      selectedNodeId,
      selectNode,
      expandNode,
      clearGraph,
      setBrowseMode,
      toggleLeftPanel,
      handlers,
    ]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
