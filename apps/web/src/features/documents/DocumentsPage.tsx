import { EmptyState, ErrorState, LoadingState } from "../../shared/states";
import DocumentsTableComponent from "./components/documentsTableComponent";
import UploadComponent from "./components/uploadComponent";
import { useDocumentLibrary } from "./useDocumentLibrary";

export default function DocumentsPage() {
  const { documents, loadError, actionError, busy, upload, reingest, remove } =
    useDocumentLibrary();

  return (
    <section className="flex flex-col gap-4">
      <section className="card-rounded-xl">
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
      </section>
      {documents && documents.length > 0 ? (
        <section className="card">
          <DocumentsTableComponent
            documents={documents}
            busy={busy}
            onReingest={reingest}
            onDelete={remove}
          />
        </section>
      ) : null}
    </section>
  );
}
