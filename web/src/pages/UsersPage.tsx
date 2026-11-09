import { useEffect, useState } from 'react';
import { allPermissions, allRoles, can, permissionLabel, roleLabel, rolePermissions, rolesText } from '../api/access';
import { api } from '../api/client';
import type { Role, RoleChange, User } from '../api/types';
import { useCurrentUser } from '../auth';

/** Users and roles. Everyone can see it; only admins can change roles. */
export default function UsersPage() {
  const { user: me, reload: reloadMe } = useCurrentUser();
  const [users, setUsers] = useState<User[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Role[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [history, setHistory] = useState<Record<string, RoleChange[]>>({});
  const isAdmin = can(me, 'users.manage');

  const load = async () => {
    const list = await api.listUsers();
    setUsers(list);
    const entries = await Promise.all(list.map(async (u) => [u.id, await api.listRoleChanges(u.id)] as const));
    setHistory(Object.fromEntries(entries));
  };
  useEffect(() => {
    void load();
  }, []);

  const start = (u: User) => {
    setEditing(u.id);
    setDraft([...u.roles]);
    setReason('');
    setError('');
  };
  const toggle = (r: Role) => setDraft((d) => (d.includes(r) ? d.filter((x) => x !== r) : [...d, r]));
  const save = async (u: User) => {
    setError('');
    try {
      await api.setUserRoles(u.id, draft, reason.trim());
      setEditing(null);
      await load();
      if (u.id === me?.id) await reloadMe();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const same = (u: User) => draft.length === u.roles.length && draft.every((r) => u.roles.includes(r));

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Users and roles</h1>
          <p>A user can have several roles; they add up. Admin includes everything Developer and DevOps can do.</p>
        </div>
      </div>

      <section className="card settings-card" aria-labelledby="matrix-h">
        <h2 id="matrix-h">What each role can do</h2>
        <div className="table-scroll">
          <table className="tools-table roles-matrix">
            <thead>
              <tr>
                <th>Permission</th>
                {allRoles.map((r) => <th key={r}>{roleLabel[r]}</th>)}
              </tr>
            </thead>
            <tbody>
              {allPermissions.map((p) => (
                <tr key={p}>
                  <td>{permissionLabel[p]}</td>
                  {allRoles.map((r) => (
                    <td key={r} className="yes-no" aria-label={rolePermissions[r].includes(p) ? 'yes' : 'no'}>
                      {rolePermissions[r].includes(p) ? '✓' : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card settings-card" aria-labelledby="users-h">
        <h2 id="users-h">Users</h2>
        {!isAdmin && <p className="muted">Only admins can change roles.</p>}
        <ul className="user-list">
          {users.map((u) => (
            <li key={u.id}>
              <div className="user-row">
                <div className="avatar" aria-hidden="true">{u.name.split(' ').map((x) => x[0]).join('')}</div>
                <div className="user-main">
                  <b>{u.name}{u.id === me?.id ? ' (you)' : ''}</b>
                  <span className="role-chips">
                    {u.roles.map((r) => <span key={r} className={`role-chip ${r}`}>{roleLabel[r]}</span>)}
                  </span>
                </div>
                {isAdmin && editing !== u.id && (
                  <button type="button" className="btn" onClick={() => start(u)}>Change roles</button>
                )}
              </div>

              {editing === u.id && (
                <div className="role-edit">
                  <fieldset>
                    <legend>Roles of {u.name}</legend>
                    {allRoles.map((r) => (
                      <label key={r} className="role-check">
                        <input type="checkbox" checked={draft.includes(r)} onChange={() => toggle(r)} />
                        <span><b>{roleLabel[r]}</b></span>
                      </label>
                    ))}
                  </fieldset>
                  {draft.length === 0 && <p className="form-error">A user needs at least one role.</p>}
                  <div className="field">
                    <label htmlFor={`reason-${u.id}`}>Why?</label>
                    <input id={`reason-${u.id}`} value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="e.g. on call for releases this month" />
                  </div>
                  {error && <p className="form-error" role="alert">{error}</p>}
                  <div className="settings-actions">
                    <button type="button" className="btn primary" disabled={draft.length === 0 || same(u) || !reason.trim()} onClick={() => save(u)}>Save</button>
                    <button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button>
                    <span className="muted" style={{ fontSize: 12 }}>New: {rolesText(draft) || '—'}</span>
                  </div>
                </div>
              )}

              {(history[u.id] ?? []).length > 0 && (
                <ul className="access-history compact">
                  {history[u.id].map((c) => (
                    <li key={c.at + c.added.join() + c.removed.join()}>
                      <span className="mono muted">{new Date(c.at).toLocaleDateString()}</span>
                      <b>{c.by}</b>
                      {c.added.length > 0 && <span className="plus">+ {c.added.map((r) => roleLabel[r as Role]).join(', ')}</span>}
                      {c.removed.length > 0 && <span className="minus">− {c.removed.map((r) => roleLabel[r as Role]).join(', ')}</span>}
                      <span className="muted">“{c.reason}”</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
