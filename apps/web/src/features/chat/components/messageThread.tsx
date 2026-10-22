import { useEffect, useRef, type ReactNode } from "react";
import { ErrorState, LoadingState } from "../../../shared/states";
import type { ChatMessage, ConversationDetail, SourceRef } from "../api";
import AssistantMarkdown from "./assistantMarkdown";
import { sourcePageLabel, type ActiveSource } from "./sourcePanel";

type MessageThreadProps = {
  routeId: string | undefined;
  conversation: ConversationDetail | null;
  threadError: string | null;
  startedAt: string | null;
  activeSource: ActiveSource | null;
  onSelectSource: (source: ActiveSource) => void;
};

function formatThreadTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function citationGroups(sources: SourceRef[]): ActiveSource[][] {
  const groups = new Map<string, ActiveSource[]>();
  for (const source of sources) {
    const pages = groups.get(source.document_id) ?? [];
    if (!pages.some((item) => item.page === source.page)) {
      pages.push({
        documentId: source.document_id,
        filename: source.filename,
        page: source.page,
      });
    }
    groups.set(source.document_id, pages);
  }
  return [...groups.values()].map((pages) => pages.sort((a, b) => a.page - b.page));
}

function SourceCitations({
  sources,
  activeSource,
  onSelectSource,
}: {
  sources: SourceRef[];
  activeSource: ActiveSource | null;
  onSelectSource: (source: ActiveSource) => void;
}) {
  const groups = citationGroups(sources);
  if (groups.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-2">
      {groups.map((pages) => (
        <div key={pages[0].documentId} className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-medium text-gray-600">{pages[0].filename}</span>
          {pages.map((source) => {
            const selected =
              activeSource?.documentId === source.documentId && activeSource.page === source.page;
            const label = sourcePageLabel(source.page);
            return (
              <button
                key={source.page}
                type="button"
                aria-pressed={selected}
                aria-label={`${source.filename}, page ${label}`}
                onClick={() => onSelectSource(source)}
                className={`rounded-full border px-2.5 py-0.5 text-xs shadow-sm transition ${
                  selected
                    ? "border-blue-500 bg-blue-50 text-blue-700"
                    : "border-gray-200 bg-white text-gray-700 hover:border-blue-300"
                }`}
              >
                p. {label}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function MessageList({
  messages,
  startedAt,
  activeSource,
  onSelectSource,
}: {
  messages: ChatMessage[];
  startedAt: string | null;
  activeSource: ActiveSource | null;
  onSelectSource: (source: ActiveSource) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  return (
    <div className="flex flex-col gap-6 py-4 px-2">
      {startedAt ? (
        <p className="m-0 text-center text-xs text-gray-500">{formatThreadTime(startedAt)}</p>
      ) : null}
      {messages.map((message, index) =>
        message.role === "user" ? (
          <article key={`${message.role}-${index}`} className="flex justify-end">
            <div className="max-w-[min(100%,36rem)]">
              <p className="m-0 rounded-[1.25rem] bg-blue-500 px-4 py-2 whitespace-pre-wrap text-white">
                {message.content}
              </p>
            </div>
          </article>
        ) : (
          <article key={`${message.role}-${index}`} className="max-w-3xl text-gray-900">
            <AssistantMarkdown content={message.content} />
            <SourceCitations
              sources={message.sources}
              activeSource={activeSource}
              onSelectSource={onSelectSource}
            />
          </article>
        ),
      )}
      <div ref={endRef} />
    </div>
  );
}

export default function MessageThread({
  routeId,
  conversation,
  threadError,
  startedAt,
  activeSource,
  onSelectSource,
}: MessageThreadProps) {
  let body: ReactNode;
  if (conversation) {
    body = (
      <MessageList
        messages={conversation.messages}
        startedAt={startedAt}
        activeSource={activeSource}
        onSelectSource={onSelectSource}
      />
    );
  } else if (!routeId) {
    body = (
      <div className="flex h-full items-center justify-center">
        <p className="muted m-0">Ask a question to start a conversation.</p>
      </div>
    );
  } else if (threadError) {
    body = <ErrorState message={threadError} />;
  } else {
    body = <LoadingState label="Loading conversation…" />;
  }

  return <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{body}</div>;
}
