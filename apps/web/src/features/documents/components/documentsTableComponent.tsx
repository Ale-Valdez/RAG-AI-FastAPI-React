import type { LibraryDocument } from "../api";
import { canReingest } from "../documentStatus";

type DocumentsTableProps = {
  documents: LibraryDocument[];
  busy: boolean;
  onReingest: (document: LibraryDocument) => void;
  onDelete: (document: LibraryDocument) => void;
};

export default function DocumentsTableComponent({
  documents,
  busy,
  onReingest,
  onDelete,
}: DocumentsTableProps) {
  return (
    <ul className="library">
      {documents.map((document) => (
        <li key={document.id}>
          <span className="name">{document.filename}</span>
          <span className={`status status-${document.status}`}>{document.status}</span>
          <span className="row-actions">
            {canReingest(document.status) ? (
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => void onReingest(document)}
              >
                Reingest
              </button>
            ) : null}
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void onDelete(document)}
            >
              Delete
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}
