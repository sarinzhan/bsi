import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from './api/client';
import type { User } from './api/types';

interface CurrentUser {
  user: User | null;
  /** Dev only: the "Viewing as" switcher. In prod the user comes from company SSO. */
  switchUser: (id: string) => Promise<void>;
  reload: () => Promise<void>;
}

const Ctx = createContext<CurrentUser>({ user: null, switchUser: async () => {}, reload: async () => {} });

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const reload = useCallback(async () => setUser(await api.getMe()), []);
  const switchUser = useCallback(async (id: string) => {
    await api.switchDevUser(id);
    await reload();
  }, [reload]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return <Ctx.Provider value={{ user, switchUser, reload }}>{children}</Ctx.Provider>;
}

export const useCurrentUser = () => useContext(Ctx);
