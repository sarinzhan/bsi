import { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { rolesText } from '../api/access';
import type { ChatSummary, ProjectSummary, SystemInfo, User } from '../api/types';
import { useCurrentUser } from '../auth';
import { statusColor } from './StatusBadge';

export default function Sidebar() {
  const { systemId = 'superapp' } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [systems, setSystems] = useState<SystemInfo[]>([]);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const { user, switchUser } = useCurrentUser();

  useEffect(() => {
    api.listSystems().then(setSystems);
  }, []);

  useEffect(() => {
    api.listUsers().then(setAllUsers);
  }, [user]);

  // Refresh on navigation and every 2 s (titles, statuses and new projects appear while the agent works).
  useEffect(() => {
    const load = () => {
      api.listChats(systemId).then(setChats);
      api.listProjects(systemId).then(setProjects);
    };
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
        <span>superAI</span>
      </div>

      <label className="nav-label" htmlFor="system" style={{ paddingTop: 0 }}>System</label>
      <select id="system" className="system-select" value={systemId} onChange={(e) => navigate(`/${e.target.value}/chats/new`)}>
        {systems.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
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
      </div>

      <div className="nav-label">Projects</div>
      <div className="nav-group">
        {projects.map((p) => (
          <NavLink key={p.id} to={`/${systemId}/projects/${p.id}`} className={subClass}>
            <span className="folder" aria-hidden="true">▣</span>
            <span className="title mono" style={{ fontSize: 12.5 }}>{p.name}</span>
          </NavLink>
        ))}
        {projects.length === 0 && <span className="muted" style={{ fontSize: 12, padding: '4px 18px' }}>Created by the agent from chats</span>}
      </div>

      <NavLink to={`/${systemId}/history`} className={navClass} style={{ marginTop: 6 }}>History</NavLink>
      <NavLink to={`/${systemId}/running`} className={navClass}>Running</NavLink>

      <div className="nav-label">Platform</div>
      <NavLink to={`/${systemId}/servers`} className={navClass}>Servers</NavLink>
      <NavLink to={`/${systemId}/skills`} className={navClass}>Skills</NavLink>
      <NavLink to={`/${systemId}/users`} className={navClass}>Users and roles</NavLink>

      <div className="sidebar-user">
        <div className="avatar" aria-hidden="true">{user?.name.split(' ').map((x) => x[0]).join('')}</div>
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.3, minWidth: 0, flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{user?.name}</span>
          <span className="muted" style={{ fontSize: 12 }}>{user ? rolesText(user.roles) : ''}</span>
          <label className="viewing-as">
            <span>Viewing as (dev)</span>
            <select value={user?.id ?? ''} onChange={(e) => void switchUser(e.target.value)}>
              {allUsers.map((u) => (
                <option key={u.id} value={u.id}>{u.name} · {rolesText(u.roles)}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </nav>
  );
}
