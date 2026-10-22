import { EmptyState, ErrorState, LoadingState } from "../../shared/states";
import DocumentsTableComponent from "./components/documentsTableComponent";
import UploadComponent from "./components/uploadComponent";
import { useDocumentLibrary } from "./useDocumentLibrary";

export default function DocumentsPage() {
  const { documents, loadError, actionError, busy, upload, reingest, remove } =
    useDocumentLibrary();

  return (
    <section className="panel">
      <h2>Documents</h2>
      <UploadComponent busy={busy} onUpload={upload} />
      {actionError ? <p className="error">{actionError}</p> : null}
      {documents === null && !loadError ? <LoadingState label="Loading documents…" /> : null}
      {documents === null && loadError ? <ErrorState message={loadError} /> : null}
      {documents && loadError ? <p className="error">{loadError}</p> : null}
      {documents && documents.length === 0 ? (
        <EmptyState
          title="No documents yet"
          detail="Upload a PDF. Files stay in this tenant's library."
        />
      ) : null}
      {documents && documents.length > 0 ? (
        <DocumentsTableComponent
          documents={documents}
          busy={busy}
          onReingest={reingest}
          onDelete={remove}
        />
      ) : null}
    </section>
  );
}
