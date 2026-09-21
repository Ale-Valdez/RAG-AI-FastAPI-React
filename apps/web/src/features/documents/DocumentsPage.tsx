import { EmptyState } from "../../shared/states";

export default function DocumentsPage() {
  return (
    <EmptyState
      title="No documents yet"
      detail="PDF upload lands in the documents slice. Files stay scoped to the authenticated tenant."
    />
  );
}
