import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams, NavLink } from "react-router-dom";
import { ApiError, apiErrorMessage } from "../../api/client";
import { listDocuments, type LibraryDocument } from "../documents/api";
import { EmptyState, ErrorState, LoadingState } from "../../shared/states";
import {
  appendMessage,
  createConversation,
  getConversation,
  listConversations,
  type ChatMessage,
  type ConversationDetail,
  type ConversationSummary,
} from "./api";

const POLL_MS = 3000;

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

function roleLabel(role: string): string {
  if (role === "user") return "You";
  if (role === "assistant") return "Assistant";
  return role;
}

function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="messages">
      {messages.map((message, index) => (
        <article key={`${message.role}-${index}`} className="message">
          <p className="eyebrow">{roleLabel(message.role)}</p>
          <p>{message.content}</p>
          {message.sources.length > 0 ? (
            <ul className="sources">
              {message.sources.map((source, sourceIndex) => (
                <li key={`${source.document_id}-${source.chunk_index}-${sourceIndex}`}>
                  {source.filename}, page {source.page}
                </li>
              ))}
            </ul>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const mountedRef = useRef(true);
  const routeIdRef = useRef(id);
  const conversationRef = useRef<ConversationDetail | null>(null);
  routeIdRef.current = id;
  const [documents, setDocuments] = useState<LibraryDocument[] | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [sending, setSending] = useState(false);
  conversationRef.current = conversation;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [docs, threads] = await Promise.all([listDocuments(), listConversations()]);
        if (cancelled) return;
        setDocuments(docs);
        setConversations(threads);
      } catch (reason: unknown) {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        setLoadError(apiErrorMessage(reason));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const noReadyDocs = documents !== null && documents.every((item) => item.status !== "ready");

  useEffect(() => {
    if (!noReadyDocs) return;
    let cancelled = false;
    let timer = 0;

    const poll = async () => {
      try {
        const docs = await listDocuments();
        if (cancelled) return;
        setDocuments(docs);
        if (docs.some((item) => item.status === "ready")) return;
      } catch (reason: unknown) {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) return;
      }
      if (cancelled) return;
      timer = window.setTimeout(() => {
        void poll();
      }, POLL_MS);
    };

    timer = window.setTimeout(() => {
      void poll();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [noReadyDocs]);

  useEffect(() => {
    setSendError(null);
    setThreadError(null);
    if (!id) {
      setConversation(null);
      return;
    }
    if (conversationRef.current?.id === id) return;
    let cancelled = false;
    setConversation(null);
    void (async () => {
      try {
        const next = await getConversation(id);
        if (!cancelled) setConversation(next);
      } catch (reason: unknown) {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        setConversation(null);
        setThreadError(apiErrorMessage(reason));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const readyDocuments = (documents ?? []).filter((item) => item.status === "ready");
  const noReady = documents !== null && readyDocuments.length === 0;
  const threadLoading = Boolean(id) && conversation === null && !threadError;
  const inputDisabled = sending || documents === null || noReady || threadLoading;
  const sendDisabled = inputDisabled || question.trim() === "";

  async function onSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text || noReady || sending || threadLoading) return;
    const scope = documentId || undefined;
    const startedOn = id;
    setSending(true);
    setSendError(null);
    try {
      if (startedOn) {
        const next = await appendMessage(startedOn, text, scope);
        if (!mountedRef.current || routeIdRef.current !== startedOn) return;
        setConversation(next);
        setQuestion("");
        return;
      }
      const created = await createConversation(text, scope);
      if (!mountedRef.current) return;
      try {
        const threads = await listConversations();
        if (!mountedRef.current) return;
        setConversations(threads);
      } catch (reason: unknown) {
        if (!mountedRef.current) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        setConversations((current) => [
          { id: created.id, created_at: new Date().toISOString() },
          ...(current ?? []).filter((item) => item.id !== created.id),
        ]);
      }
      if (!mountedRef.current || routeIdRef.current !== startedOn) return;
      setConversation(created);
      setQuestion("");
      navigate(`/chat/${created.id}`);
    } catch (reason: unknown) {
      if (!mountedRef.current || routeIdRef.current !== startedOn) return;
      if (reason instanceof ApiError && reason.status === 401) return;
      setSendError(apiErrorMessage(reason));
    } finally {
      if (mountedRef.current) setSending(false);
    }
  }

  if (loadError && conversations === null) {
    return <ErrorState message={loadError} />;
  }
  if (conversations === null || documents === null) {
    return <LoadingState label="Loading conversations…" />;
  }

  return (
    <div className="thread-layout">
      <aside className="panel">
        <h2>Conversations</h2>
        {conversations.length === 0 ? (
          <EmptyState
            title="No conversations yet"
            detail="Ask a question once a document is ready."
          />
        ) : (
          <ul className="conversation-list">
            {conversations.map((item) => (
              <li key={item.id}>
                <NavLink to={`/chat/${item.id}`}>{formatTimestamp(item.created_at)}</NavLink>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <section className="panel">
        <h2>Chat</h2>
        {id ? (
          threadError && !conversation ? (
            <ErrorState message={threadError} />
          ) : conversation ? (
            <MessageList messages={conversation.messages} />
          ) : (
            <LoadingState label="Loading conversation…" />
          )
        ) : (
          <p className="muted">Ask a question to start a conversation.</p>
        )}
        {sendError ? <p className="error">{sendError}</p> : null}
        {noReady ? (
          <p className="muted">Send is unavailable until a document is ready.</p>
        ) : null}
        <form className="composer" onSubmit={onSend}>
          <label>
            Document
            <select
              value={documentId}
              disabled={inputDisabled}
              onChange={(event) => setDocumentId(event.target.value)}
            >
              <option value="">All ready documents</option>
              {readyDocuments.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.filename}
                </option>
              ))}
            </select>
          </label>
          <label>
            Question
            <textarea
              value={question}
              rows={4}
              disabled={inputDisabled}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </label>
          <button type="submit" disabled={sendDisabled}>
            Send
          </button>
        </form>
      </section>
    </div>
  );
}
