import { useEffect, useState } from 'react';
import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { api } from './api/client';
import { CurrentUserProvider, useCurrentUser } from './auth';
import Sidebar from './components/Sidebar';
import ChangePasswordPage from './pages/ChangePasswordPage';
import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import ServerSettingsPage from './pages/ServerSettingsPage';
import ServersPage from './pages/ServersPage';
import UsersPage from './pages/UsersPage';

const LAST_SYSTEM_KEY = 'bsi.lastSystem';

export function rememberSystem(id: string) {
  try {
    localStorage.setItem(LAST_SYSTEM_KEY, id);
  } catch {
    /* private mode */
  }
}

function lastSystem(): string | null {
  try {
    return localStorage.getItem(LAST_SYSTEM_KEY);
  } catch {
    return null;
  }
}

/** Start page: the last (or first) system's chats; no systems yet = no servers yet, so go add one. */
function Home() {
  const [target, setTarget] = useState<string | null>(null);
  useEffect(() => {
    api.listSystems()
      .then((systems) => {
        const last = lastSystem();
        const pick = systems.find((s) => s.id === last) ?? systems[0];
        setTarget(pick ? `/${pick.id}/chats/new` : '/servers');
      })
      .catch(() => setTarget('/servers'));
  }, []);
  return target ? <Navigate to={target} replace /> : <div className="page muted">Loading…</div>;
}

function NoRolesBanner() {
  const { user } = useCurrentUser();
  if (!user || user.roles.length > 0) return null;
  return (
    <div className="banner" role="status">
      You are signed in as <b className="mono">{user.id}</b>, but you have no role yet. Ask an admin to give you one
      on the Users and roles page.
    </div>
  );
}

function Layout() {
  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <NoRolesBanner />
        <Outlet />
      </div>
    </div>
  );
}

/** Not signed in: the sign-in page. Temporary password: pick your own first. Then the app. */
function Gate() {
  const { user } = useCurrentUser();
  if (user === undefined) return <div className="page muted">Loading…</div>;
  if (user === null) return <LoginPage />;
  if (user.mustChangePassword) return <ChangePasswordPage forced />;
  return (
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/servers/:serverName" element={<ServerSettingsPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/account/password" element={<ChangePasswordPage />} />
          <Route path="/:systemId/chats/:chatId" element={<ChatPage />} />
          <Route path="/:systemId/*" element={<Navigate to="chats/new" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
  );
}

export default function App() {
  return (
    <CurrentUserProvider>
      <Gate />
    </CurrentUserProvider>
  );
}
