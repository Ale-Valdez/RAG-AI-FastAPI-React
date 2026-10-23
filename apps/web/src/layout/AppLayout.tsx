import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../auth/session";
import Header from "./Header";

export default function AppLayout() {
  const { token, me, logout } = useSession();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isChat = pathname.startsWith("/chat");

  function onSignOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className={isChat ? "flex h-dvh flex-col overflow-hidden" : "flex min-h-dvh flex-col"}>
      {token ? <Header token={token} me={me} onSignOut={onSignOut} /> : null}
      <div
        className={`mx-auto flex w-full flex-col px-4 sm:px-6 lg:px-8 ${
          isChat ? "min-h-0 max-w-none flex-1 overflow-hidden" : "max-w-7xl flex-1"
        }`}
      >
        <main className={isChat ? "flex min-h-0 flex-1 flex-col overflow-hidden py-4" : "py-16"}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
