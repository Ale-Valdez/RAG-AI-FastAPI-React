import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useSession } from "../auth/session";

export default function AppLayout() {
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
        <Outlet />
      </main>
    </div>
  );
}
