import type { ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useSession } from "./auth/session";
import LoginPage from "./features/auth/LoginPage";
import ChatPage from "./features/chat/ChatPage";
import DocumentsPage from "./features/documents/DocumentsPage";
import HealthPage from "./features/health/HealthPage";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useSession();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { token } = useSession();
  if (token) return <Navigate to="/documents" replace />;
  return <>{children}</>;
}

function HomeRedirect() {
  const { token } = useSession();
  return <Navigate to={token ? "/documents" : "/login"} replace />;
}

export default function App() {
  const { token, me, logout } = useSession();
  const navigate = useNavigate();

  function onSignOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="shell">
      <header>
        <p className="eyebrow">ai-rag</p>
        <h1>AI-RAG</h1>
        {me ? (
          <>
            <p className="lede">{me.email}</p>
            <p className="muted">{me.tenant_id}</p>
          </>
        ) : (
          <p className="lede">AI Knowledge Assistant grounded in organization documents.</p>
        )}
        {token ? (
          <nav>
            <NavLink to="/documents">Documents</NavLink>
            <NavLink to="/chat">Chat</NavLink>
          </nav>
        ) : null}
        <div className="header-actions">
          {token ? (
            <button type="button" className="secondary sign-out" onClick={onSignOut}>
              Sign out
            </button>
          ) : null}
          <Link className="health-link" to="/health">
            Health
          </Link>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
          <Route path="/documents" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
          <Route path="/chat/:id?" element={<RequireAuth><ChatPage /></RequireAuth>} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="/" element={<HomeRedirect />} />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </main>
    </div>
  );
}
