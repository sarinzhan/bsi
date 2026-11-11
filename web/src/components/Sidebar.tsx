import { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { rolesText } from '../api/access';
import type { ChatSummary, SystemInfo } from '../api/types';
import { rememberSystem } from '../App';
import { useCurrentUser } from '../auth';
import { statusColor } from './StatusBadge';

export default function Sidebar() {
  const params = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [systems, setSystems] = useState<SystemInfo[]>([]);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const { user, logout } = useCurrentUser();
  // On platform pages (servers, users) there is no system in the URL: keep showing the first one's chats.
  const systemId = params.systemId ?? systems[0]?.id;

  useEffect(() => {
    api.listSystems().then(setSystems).catch(() => setSystems([]));
  }, [location.pathname]); // a server added on the Servers page can bring a new system

  useEffect(() => {
    if (params.systemId) rememberSystem(params.systemId);
  }, [params.systemId]);

  // Refresh on navigation and every 2 s (titles and statuses change while the agent works).
  useEffect(() => {
    if (!systemId) {
      setChats([]);
      return;
    }
    const load = () => api.listChats(systemId).then(setChats).catch(() => setChats([]));
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [systemId, location.pathname]);

  const navClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'nav-link active' : 'nav-link');
  const subClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'nav-sub active' : 'nav-sub');

  return (
    <nav className="sidebar" aria-label="Main">
      <div className="logo">
        <div className="logo-mark">&lt;/&gt;</div>
        <span>BSI</span>
      </div>

      {systemId ? (
        <>
          <label className="nav-label" htmlFor="system" style={{ paddingTop: 0 }}>System</label>
          <select id="system" className="system-select" value={systemId} onChange={(e) => navigate(`/${e.target.value}/chats/new`)}>
            {systems.map((s) => (
              <option key={s.id} value={s.id}>{s.id}</option>
            ))}
          </select>

          <NavLink to={`/${systemId}/chats/new`} end className="btn-primary-dark">+ New chat</NavLink>

          <div className="nav-label">Chats</div>
          <div className="nav-group">
            {chats.map((c) => (
              <NavLink key={c.id} to={`/${systemId}/chats/${c.id}`} className={subClass}>
                <span className="dot" style={{ background: statusColor[c.status], width: 6, height: 6 }} />
                <span className="title">{c.title}</span>
              </NavLink>
            ))}
            {chats.length === 0 && <span className="muted" style={{ fontSize: 12, padding: '4px 18px' }}>No chats yet</span>}
          </div>
        </>
      ) : (
        <p className="muted" style={{ fontSize: 12.5, padding: '0 18px', lineHeight: 1.5 }}>
          No systems yet. A system appears when a server for it is added.
        </p>
      )}

      <div className="nav-label">Platform</div>
      <NavLink to="/servers" className={navClass}>Servers</NavLink>
      <NavLink to="/users" className={navClass}>Users and roles</NavLink>

      <div className="sidebar-user">
        <div className="avatar" aria-hidden="true">{user?.name.split(/[\s._-]+/).map((x) => x[0]?.toUpperCase()).join('').slice(0, 2)}</div>
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.3, minWidth: 0, flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{user?.name}</span>
          <span className="muted" style={{ fontSize: 12 }}>{user ? rolesText(user.roles) || 'no role yet' : ''}</span>
          <span className="user-actions">
            <NavLink to="/account/password" className="link-btn">Password</NavLink>
            <button type="button" className="link-btn" onClick={() => void logout().then(() => navigate('/'))}>Sign out</button>
          </span>
        </div>
      </div>
    </nav>
  );
}
