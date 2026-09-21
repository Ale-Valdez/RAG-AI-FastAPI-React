import { NavLink, Route, Routes } from "react-router-dom";
import ChatPage from "./features/chat/ChatPage";
import DocumentsPage from "./features/documents/DocumentsPage";
import HealthPage from "./features/health/HealthPage";

export default function App() {
  return (
    <div className="shell">
      <header>
        <p className="eyebrow">ai-rag</p>
        <h1>AI-RAG</h1>
        <p className="lede">AI Knowledge Assistant grounded in organization documents.</p>
        <nav>
          <NavLink to="/">Health</NavLink>
          <NavLink to="/documents">Documents</NavLink>
          <NavLink to="/chat">Chat</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<HealthPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </main>
    </div>
  );
}
