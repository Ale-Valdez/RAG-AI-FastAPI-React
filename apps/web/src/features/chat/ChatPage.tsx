import { useState } from "react";
import { ErrorState, LoadingState } from "../../shared/states";
import Composer from "./components/composer";
import ConversationRail, { RailToggleButton } from "./components/conversationRail";
import DocumentScopeRow from "./components/documentScopeRow";
import MessageThread from "./components/messageThread";
import SourcePanel, { type ActiveSource } from "./components/sourcePanel";
import { useChatSession } from "./useChatSession";

function chatGridClass(railOpen: boolean, reading: boolean): string {
  const grid = "grid min-h-0 flex-1 gap-4";
  if (reading) {
    return `${grid} grid-cols-1 grid-rows-1 lg:grid-cols-[minmax(20rem,26rem)_minmax(0,1fr)]`;
  }
  if (railOpen) {
    return `${grid} grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(12rem,16rem)_minmax(0,1fr)] lg:grid-rows-1`;
  }
  return "flex min-h-0 flex-1 flex-col";
}

function threadClass(reading: boolean): string {
  const base = "h-full min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden";
  if (reading) return `${base} hidden lg:flex`;
  return `${base} mx-auto flex max-w-3xl`;
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
  const [sourceConversationId, setSourceConversationId] = useState(id);
  if (sourceConversationId !== id) {
    setSourceConversationId(id);
    setActiveSource(null);
  }

  if (loadError && conversations === null) {
    return <ErrorState message={loadError} />;
  }
  if (conversations === null || documents === null) {
    return <LoadingState label="Loading conversations…" />;
  }

  const startedAt = id ? (conversations.find((item) => item.id === id)?.created_at ?? null) : null;
  const reading = activeSource !== null;

  return (
    <div className={chatGridClass(railOpen, reading)}>
      {railOpen ? (
        <ConversationRail
          conversations={conversations}
          hidden={reading}
          onCollapse={() => setRailOpen(false)}
        />
      ) : null}
      <section className={threadClass(reading)}>
        <div className="flex items-end gap-2">
          {!reading && !railOpen ? (
            <div className="mb-1">
              <RailToggleButton expanded={false} onClick={() => setRailOpen(true)} />
            </div>
          ) : null}
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
