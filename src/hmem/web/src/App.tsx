import { useState, useCallback } from "react";
import { MainLayout } from "./components/layout/MainLayout";
import { HelpModal } from "./components/modals/HelpModal";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";

function App() {
  const [helpOpen, setHelpOpen] = useState(false);

  const handleToggleHelp = useCallback(() => {
    setHelpOpen((prev) => !prev);
  }, []);

  useKeyboardShortcuts({
    onToggleHelp: handleToggleHelp,
  });

  return (
    <>
      <MainLayout onHelpClick={handleToggleHelp} />
      <HelpModal isOpen={helpOpen} onClose={() => setHelpOpen(false)} />
    </>
  );
}

export default App;
