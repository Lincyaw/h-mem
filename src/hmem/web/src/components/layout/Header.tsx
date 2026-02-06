import { useGraphStore } from "../../store/graph-store";

const nodeTypeIcons: Record<string, string> = {
  entities: "tag",
  active_facts: "clipboard",
  active_processes: "cog",
  active_skills: "target",
  active_principles: "lightbulb",
  conversations: "message-circle",
};

const nodeTypeColors: Record<string, string> = {
  entities: "text-entity",
  active_facts: "text-fact",
  active_processes: "text-process",
  active_skills: "text-skill",
  active_principles: "text-principle",
  conversations: "text-conversation",
};

interface StatItemProps {
  label: string;
  value: number;
  icon: string;
  colorClass: string;
}

function StatItem({ label, value, icon, colorClass }: StatItemProps) {
  return (
    <button
      className={`flex items-center gap-1.5 px-2 py-1 rounded hover:bg-gray-800 transition-colors ${colorClass}`}
      title={`${value} ${label}`}
    >
      <Icon name={icon} className="w-4 h-4" />
      <span className="font-mono text-sm">{value}</span>
    </button>
  );
}

function Icon({ name, className }: { name: string; className?: string }) {
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
    "message-circle": (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
      />
    ),
    menu: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 6h16M4 12h16M4 18h16"
      />
    ),
    help: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    ),
    settings: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
      />
    ),
  };

  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      {paths[name]}
    </svg>
  );
}

export function Header({ onHelpClick }: { onHelpClick?: () => void }) {
  const { stats, toggleLeftPanel, leftPanelCollapsed } = useGraphStore();

  return (
    <header className="h-12 bg-gray-900 border-b border-gray-800 flex items-center px-4 gap-4">
      {/* Hamburger menu */}
      <button
        onClick={toggleLeftPanel}
        className="p-2 rounded hover:bg-gray-800 transition-colors text-gray-400 hover:text-white"
        title={leftPanelCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <Icon name="menu" className="w-5 h-5" />
      </button>

      {/* Logo */}
      <div className="flex items-center gap-2">
        <span className="text-xl">🧠</span>
        <span className="font-semibold text-white">h-mem</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Stats */}
      {stats && (
        <div className="flex items-center gap-1">
          <StatItem
            label="Entities"
            value={stats.entities}
            icon={nodeTypeIcons.entities}
            colorClass={nodeTypeColors.entities}
          />
          <StatItem
            label="Facts"
            value={stats.active_facts}
            icon={nodeTypeIcons.active_facts}
            colorClass={nodeTypeColors.active_facts}
          />
          <StatItem
            label="Processes"
            value={stats.active_processes}
            icon={nodeTypeIcons.active_processes}
            colorClass={nodeTypeColors.active_processes}
          />
          <StatItem
            label="Skills"
            value={stats.active_skills}
            icon={nodeTypeIcons.active_skills}
            colorClass={nodeTypeColors.active_skills}
          />
          <StatItem
            label="Principles"
            value={stats.active_principles}
            icon={nodeTypeIcons.active_principles}
            colorClass={nodeTypeColors.active_principles}
          />
          <StatItem
            label="Conversations"
            value={stats.conversations}
            icon={nodeTypeIcons.conversations}
            colorClass={nodeTypeColors.conversations}
          />
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Help button */}
      <button
        onClick={onHelpClick}
        className="p-2 rounded hover:bg-gray-800 transition-colors text-gray-400 hover:text-white"
        title="Help (press ?)"
      >
        <Icon name="help" className="w-5 h-5" />
      </button>

      {/* Settings button */}
      <button
        className="p-2 rounded hover:bg-gray-800 transition-colors text-gray-400 hover:text-white"
        title="Settings"
      >
        <Icon name="settings" className="w-5 h-5" />
      </button>
    </header>
  );
}
