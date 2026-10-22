import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, apiErrorMessage } from "../../api/client";
import { listDocuments, type LibraryDocument } from "../documents/api";
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

export function useChatSession() {
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
    const previous = conversationRef.current;
    const outgoing: ChatMessage = { role: "user", content: text, sources: [] };
    setConversation({
      id: previous?.id ?? "",
      messages: [...(previous?.messages ?? []), outgoing],
    });
    setQuestion("");
    setSending(true);
    setSendError(null);

    const stillHere = () => mountedRef.current && routeIdRef.current === startedOn;
    const revertOutgoing = () => {
      if (!stillHere()) return;
      setConversation(previous);
      setQuestion(text);
    };

    try {
      if (startedOn) {
        const next = await appendMessage(startedOn, text, scope);
        if (!stillHere()) return;
        setConversation(next);
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
        if (reason instanceof ApiError && reason.status === 401) {
          revertOutgoing();
          return;
        }
        setConversations((current) => [
          { id: created.id, created_at: new Date().toISOString() },
          ...(current ?? []).filter((item) => item.id !== created.id),
        ]);
      }
      if (!stillHere()) return;
      setConversation(created);
      navigate(`/chat/${created.id}`);
    } catch (reason: unknown) {
      revertOutgoing();
      if (!stillHere()) return;
      if (reason instanceof ApiError && reason.status === 401) return;
      setSendError(apiErrorMessage(reason));
    } finally {
      if (mountedRef.current) setSending(false);
    }
  }

  return {
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
  };
}
