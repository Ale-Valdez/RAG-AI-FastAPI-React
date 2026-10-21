import { apiData } from "../../api/client";

export type LibraryDocument = {
  id: string;
  filename: string;
  status: string;
};

export function listDocuments(): Promise<LibraryDocument[]> {
  return apiData<{ documents: LibraryDocument[] }>("/api/v1/documents").then(
    (data) => data.documents,
  );
}

export function uploadDocument(file: File): Promise<LibraryDocument> {
  const body = new FormData();
  body.append("file", file);
  return apiData<LibraryDocument>("/api/v1/documents", { method: "POST", body });
}

export function deleteDocument(documentId: string): Promise<{ id: string }> {
  return apiData<{ id: string }>(`/api/v1/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  });
}

export function reingestDocument(documentId: string): Promise<LibraryDocument> {
  return apiData<LibraryDocument>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/reingest`,
    { method: "POST" },
  );
}
