import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from './api/client';
import { ApiError, hasToken, SIGNED_OUT_EVENT } from './api/http';
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
  // Bumped by sign-in and sign-out: an older /api/me answer that arrives later is ignored, so it can not
  // undo the sign-in that happened meanwhile.
  const generation = useRef(0);

  const reload = useCallback(async () => {
    const mine = generation.current;
    if (!hasToken()) {
      setUser(null); // never signed in here: no need to ask
      return;
    }
    try {
      const me = await api.getMe();
      if (generation.current === mine) {
        setUser(me);
        setError('');
      }
    } catch (e) {
      if (generation.current !== mine) return;
      setUser(null);
      setError(e instanceof ApiError && e.status === 401 ? '' : e instanceof Error ? e.message : String(e));
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const me = await api.login(username, password);
    generation.current += 1;
    setUser(me);
    setError('');
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      generation.current += 1;
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
