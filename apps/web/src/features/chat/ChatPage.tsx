import { EmptyState } from "../../shared/states";

export default function ChatPage() {
  return (
    <EmptyState
      title="No conversations yet"
      detail="Chat will ask questions over ready documents and show source pages with the answer."
    />
  );
}
