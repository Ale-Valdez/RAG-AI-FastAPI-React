import { apiBytes, apiData } from "../../api/client";

export type SourceRef = {
  document_id: string;
  filename: string;
  page: number;
  chunk_index: number;
};

export type ChatMessage = {
  role: string;
  content: string;
  sources: SourceRef[];
};

export type ConversationDetail = {
  id: string;
  messages: ChatMessage[];
};

export type ConversationSummary = {
  id: string;
  created_at: string;
};

function questionBody(question: string, documentId?: string): string {
  const payload: { question: string; document_id?: string } = { question };
  if (documentId) payload.document_id = documentId;
  return JSON.stringify(payload);
}

export function getDocumentFile(documentId: string): Promise<Blob> {
  return apiBytes(`/api/v1/documents/${encodeURIComponent(documentId)}/file`);
}

export function listConversations(): Promise<ConversationSummary[]> {
  return apiData<{ conversations: ConversationSummary[] }>("/api/v1/conversations").then(
    (data) => data.conversations,
  );
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiData<ConversationDetail>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
  );
}

export function createConversation(
  question: string,
  documentId?: string,
): Promise<ConversationDetail> {
  return apiData<ConversationDetail>("/api/v1/conversations", {
    method: "POST",
    body: questionBody(question, documentId),
  });
}

export function appendMessage(
  conversationId: string,
  question: string,
  documentId?: string,
): Promise<ConversationDetail> {
  return apiData<ConversationDetail>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
    { method: "POST", body: questionBody(question, documentId) },
  );
}
