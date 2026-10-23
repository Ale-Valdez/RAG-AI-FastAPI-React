import type { LibraryDocument } from "../api";
import { canReingest } from "../documentStatus";

type DocumentsTableProps = {
  documents: LibraryDocument[];
  busy: boolean;
  onReingest: (document: LibraryDocument) => void;
  onDelete: (document: LibraryDocument) => void;
};

type StatusInfo = {
  title: string;
  color: string;
};

function StatusIcon({ status }: { status: LibraryDocument["status"] }) {
   const statusInfo: Record<LibraryDocument["status"], StatusInfo> = {
    "pending": {
        title: "Pending",
        color: "yellow",
    },
    "processing": {
        title: "Processing",
        color: "blue",
    },
    "ready": {
        title: "Ready",
        color: "green",
    },
    "failed": {
        title: "Failed",
        color: "red",
    },
   };
  return (
    <span title={statusInfo[status]?.title} className="inline-flex items-center gap-1">
      <span
        style={{ backgroundColor: `var(--tw-bg-${statusInfo[status]?.color})`, background: statusInfo[status]?.color.replace('-', ''), border: '1px solid var(--tw-border-color)', display: 'inline-block' }}
        className="w-4 h-4 rounded-full align-middle"
      />
      <span className="sr-only">{statusInfo[status]?.title}</span>
    </span>
  );
}

export default function DocumentsTableComponent({
  documents,
  busy,
  onReingest,
  onDelete,
}: DocumentsTableProps) {
  return (
   
    <table className="table-auto w-full border-separate border-spacing-2 border border-gray-200 rounded-md p-2">
        <thead>
            <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody className="border-spacing-2">
            {documents.map((document) => (
                <tr key={document.id} className="hover:bg-gray-100 dark:hover:bg-gray-800 hover:cursor-pointer hover:
             transition-colors duration-200 hover:text-gray-50 dark:hover:text-gray-50">
                    <td className="border border-x-0 border-gray-200 dark:border-gray-200  p-2">{document.filename}</td>
                    <td className="status status-icon text-center border border-x-0 border-gray-200 dark:border-gray-200 p-2">
                      <StatusIcon status={document.status} />
                    </td>
               
                    <td className="flex gap-2 border border-x-0 border-gray-200 dark:border-gray-200  p-2">
                        {canReingest(document.status) ? (
                            <button
                                type="button"
                                className="icon-button secondary border-none"
                                disabled={busy}
                                title="Reingest"
                                onClick={() => void onReingest(document)}
                            >
                                <span role="img" aria-label="Reingest">🔄</span>
                            </button>
                        ) : null}
                        <button
                            type="button"
                            className="icon-button secondary border-none"
                            disabled={busy}
                            title="Delete"
                            onClick={() => void onDelete(document)}
                        >
                            <span role="img" aria-label="Delete">🗑️</span>
                        </button>
                    </td>
               
                </tr>
            ))}
        </tbody>
    </table>

  );
}
