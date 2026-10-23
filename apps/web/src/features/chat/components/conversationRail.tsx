import { NavLink } from "react-router-dom";
import { EmptyState } from "../../../shared/states";
import type { ConversationSummary } from "../api";

type ConversationRailProps = {
  conversations: ConversationSummary[];
  hidden?: boolean;
  onCollapse: () => void;
};

export function RailToggleButton({
  expanded,
  onClick,
}: {
  expanded: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-expanded={expanded}
      aria-controls="conversation-rail"
      aria-label={expanded ? "Hide conversations" : "Show conversations"}
      onClick={onClick}
      className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        className="size-4"
        aria-hidden="true"
      >
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16" />
      </svg>
    </button>
  );
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

export default function ConversationRail({
  conversations,
  hidden = false,
  onCollapse,
}: ConversationRailProps) {
  return (
    <aside
      id="conversation-rail"
      className={`card h-full max-h-48 min-h-0 min-w-0 flex-col overflow-hidden lg:max-h-none ${
        hidden ? "hidden" : "flex"
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="m-0 text-lg font-bold">Conversations</h2>
        <RailToggleButton expanded onClick={onCollapse} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <EmptyState
            title="No conversations yet"
            detail="Ask a question once a document is ready."
          />
        ) : (
          <ul className="m-0 list-none p-0">
            {conversations.map((item) => (
              <li key={item.id} className="border-b border-gray-100 py-2">
                <NavLink
                  to={`/chat/${item.id}`}
                  className={({ isActive }) =>
                    `block text-blue-800 no-underline ${isActive ? "font-bold" : "font-normal"}`
                  }
                >
                  {formatTimestamp(item.created_at)}
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
