import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from './api/client';
import { ApiError, SIGNED_OUT_EVENT } from './api/http';
import type { User } from './api/types';

interface CurrentUser {
  /** undefined: still asking; null: not signed in (show the sign-in page). */
  user: User | null | undefined;
  /** Why the session check failed, other than "not signed in" (e.g. platform-api is down). */
  error: string;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const Ctx = createContext<CurrentUser>({
  user: undefined, error: '', login: async () => {}, logout: async () => {}, reload: async () => {},
});

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    try {
      setUser(await api.getMe());
      setError('');
    } catch (e) {
      setUser(null);
      setError(e instanceof ApiError && e.status === 401 ? '' : e instanceof Error ? e.message : String(e));
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setUser(await api.login(username, password));
    setError('');
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    void reload();
    // any 401 (session expired, signed out in another tab, password reset by an admin): ask again
    const onSignedOut = () => void reload();
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, [reload]);

  return <Ctx.Provider value={{ user, error, login, logout, reload }}>{children}</Ctx.Provider>;
}

export const useCurrentUser = () => useContext(Ctx);
