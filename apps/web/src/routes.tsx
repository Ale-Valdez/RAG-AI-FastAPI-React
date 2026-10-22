import type { ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { useSession } from "./auth/session";
import LoginPage from "./features/auth/LoginPage";
import ChatPage from "./features/chat/ChatPage";
import DocumentsPage from "./features/documents/DocumentsPage";
import HealthPage from "./features/health/HealthPage";
import AppLayout from "./layout/AppLayout";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useSession();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { token } = useSession();
  if (token) return <Navigate to="/documents" replace />;
  return children;
}

function HomeRedirect() {
  const { token } = useSession();
  return <Navigate to={token ? "/documents" : "/login"} replace />;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        path: "login",
        element: (
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        ),
      },
      {
        path: "documents",
        element: (
          <RequireAuth>
            <DocumentsPage />
          </RequireAuth>
        ),
      },
      {
        path: "chat/:id?",
        element: (
          <RequireAuth>
            <ChatPage />
          </RequireAuth>
        ),
      },
      { path: "health", element: <HealthPage /> },
      { path: "*", element: <HomeRedirect /> },
    ],
  },
]);
