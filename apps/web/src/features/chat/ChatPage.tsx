import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "../../shared/states";
import Composer from "./components/composer";
import ConversationRail, { RailToggleButton } from "./components/conversationRail";
import DocumentScopeRow from "./components/documentScopeRow";
import MessageThread from "./components/messageThread";
import SourcePanel, { type ActiveSource } from "./components/sourcePanel";
import { useChatSession } from "./useChatSession";

function chatGridClass(railOpen: boolean, panelOpen: boolean): string {
  const grid = "grid min-h-0 flex-1 gap-4";
  if (railOpen && panelOpen) {
    return `${grid} grid-rows-[auto_minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[minmax(12rem,16rem)_minmax(0,1fr)_minmax(16rem,22rem)] lg:grid-rows-1`;
  }
  if (railOpen) {
    return `${grid} grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(12rem,16rem)_minmax(0,1fr)] lg:grid-rows-1`;
  }
  if (panelOpen) {
    return `${grid} grid-rows-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)] lg:grid-rows-1`;
  }
  return "flex min-h-0 flex-1 flex-col";
}

export default function ChatPage() {
  const {
    id,
    documents,
    conversations,
    conversation,
    loadError,
    threadError,
    sendError,
    question,
    setQuestion,
    documentId,
    setDocumentId,
    readyDocuments,
    noReady,
    inputDisabled,
    sendDisabled,
    onSend,
  } = useChatSession();
  const [railOpen, setRailOpen] = useState(true);
  const [activeSource, setActiveSource] = useState<ActiveSource | null>(null);

  useEffect(() => {
    setActiveSource(null);
  }, [id]);

  if (loadError && conversations === null) {
    return <ErrorState message={loadError} />;
  }
  if (conversations === null || documents === null) {
    return <LoadingState label="Loading conversations…" />;
  }

  const startedAt = id ? (conversations.find((item) => item.id === id)?.created_at ?? null) : null;

  return (
    <div className={chatGridClass(railOpen, activeSource !== null)}>
      {railOpen ? (
        <ConversationRail conversations={conversations} onCollapse={() => setRailOpen(false)} />
      ) : null}
      <section className="mx-auto flex h-full min-h-0 w-full max-w-3xl min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-end gap-2">
          {railOpen ? null : (
            <div className="mb-1">
              <RailToggleButton expanded={false} onClick={() => setRailOpen(true)} />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <DocumentScopeRow
              documents={readyDocuments}
              value={documentId}
              disabled={inputDisabled}
              onChange={setDocumentId}
            />
          </div>
        </div>
        <MessageThread
          routeId={id}
          conversation={conversation}
          threadError={threadError}
          startedAt={startedAt}
          activeSource={activeSource}
          onSelectSource={setActiveSource}
        />
        {sendError ? <p className="error m-0">{sendError}</p> : null}
        {noReady ? (
          <p className="muted m-0">Send is unavailable until a document is ready.</p>
        ) : null}
        <Composer
          question={question}
          disabled={inputDisabled}
          sendDisabled={sendDisabled}
          onQuestionChange={setQuestion}
          onSubmit={onSend}
        />
      </section>
      {activeSource ? (
        <SourcePanel source={activeSource} onClose={() => setActiveSource(null)} />
      ) : null}
    </div>
  );
}
