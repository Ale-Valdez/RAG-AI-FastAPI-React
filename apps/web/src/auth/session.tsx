import {
  createContext,
  useCallback,
  useContext,
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

export function SessionProvider({ children }: { children: ReactNode }) {
  const tokenRef = useRef<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Member | null>(null);

  configureApi({
    getToken: () => tokenRef.current,
    onUnauthorized: (sentToken) => {
      if (sentToken !== tokenRef.current) return;
      tokenRef.current = null;
      setToken(null);
      setMe(null);
    },
  });

  const login = useCallback(async (email: string, password: string) => {
    const result = await apiData<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    tokenRef.current = result.access_token;
    try {
      const member = await apiData<Member>("/api/v1/me");
      tokenRef.current = result.access_token;
      setToken(result.access_token);
      setMe(member);
    } catch (error) {
      if (tokenRef.current === result.access_token) {
        tokenRef.current = null;
        setToken(null);
        setMe(null);
      }
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    tokenRef.current = null;
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
