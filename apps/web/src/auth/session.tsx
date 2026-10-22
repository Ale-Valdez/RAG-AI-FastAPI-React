import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiData, configureApi } from "../api/client";

export type Member = {
  user_id: string;
  tenant_id: string;
  email: string;
};

type SessionValue = {
  token: string | null;
  me: Member | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const SessionContext = createContext<SessionValue | null>(null);

const ACCESS_TOKEN_KEY = "ai-rag.access-token";

function readStoredAccessToken(): string | null {
  try {
    const stored = sessionStorage.getItem(ACCESS_TOKEN_KEY);
    return stored ? stored : null;
  } catch {
    return null;
  }
}

function writeStoredAccessToken(token: string): void {
  try {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  } catch {
    // A blocked write must not fail an otherwise successful sign-in.
  }
}

function clearStoredAccessToken(): void {
  try {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  } catch {
    // A blocked remove must not skip the in-memory sign-out.
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const tokenRef = useRef<string | null>(null);
  const [token, setToken] = useState<string | null>(() => {
    // Guards read `token` on the first render. A later effect would already have sent them to /login.
    const stored = readStoredAccessToken();
    tokenRef.current = stored;
    return stored;
  });
  const [me, setMe] = useState<Member | null>(null);

  configureApi({
    getToken: () => tokenRef.current,
    onUnauthorized: (sentToken) => {
      if (sentToken !== tokenRef.current) return;
      tokenRef.current = null;
      clearStoredAccessToken();
      setToken(null);
      setMe(null);
    },
  });

  useEffect(() => {
    const restored = tokenRef.current;
    if (!restored) return;

    let active = true;
    void apiData<Member>("/api/v1/me")
      .then((member) => {
        if (!active || tokenRef.current !== restored) return;
        setMe(member);
      })
      .catch(() => {
        // A 401 for this token clears the session in onUnauthorized. Any other failure keeps it.
      });

    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await apiData<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    tokenRef.current = result.access_token;
    try {
      const member = await apiData<Member>("/api/v1/me");
      tokenRef.current = result.access_token;
      writeStoredAccessToken(result.access_token);
      setToken(result.access_token);
      setMe(member);
    } catch (error) {
      if (tokenRef.current === result.access_token) {
        tokenRef.current = null;
        clearStoredAccessToken();
        setToken(null);
        setMe(null);
      }
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    tokenRef.current = null;
    clearStoredAccessToken();
    setToken(null);
    setMe(null);
  }, []);

  const value = useMemo(
    () => ({ token, me, login, logout }),
    [token, me, login, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("SessionProvider is missing");
  }
  return value;
}
