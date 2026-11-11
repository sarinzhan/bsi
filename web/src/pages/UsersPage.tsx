import { useEffect, useState, type FormEvent } from 'react';
import { allPermissions, allRoles, can, permissionLabel, roleLabel, rolePermissions, rolesText } from '../api/access';
import { api } from '../api/client';
import type { Role, RoleChange, User } from '../api/types';
import { useCurrentUser } from '../auth';

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** A temporary password the admin hands over; the user must replace it at the first sign-in. */
function temporaryPassword(): string {
  const alphabet = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789';
  const bytes = crypto.getRandomValues(new Uint8Array(14));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}

/** Admins: a new user with a temporary password. */
function AddUserForm({ onAdded }: { onAdded: () => Promise<void> }) {
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [roles, setRoles] = useState<Role[]>(['developer']);
  const [password, setPassword] = useState(temporaryPassword);
  const [error, setError] = useState('');
  const [added, setAdded] = useState<{ id: string; password: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (r: Role) => setRoles((d) => (d.includes(r) ? d.filter((x) => x !== r) : [...d, r]));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const user = await api.addUser({ id: id.trim().toLowerCase(), name: name.trim(), roles, password });
      setAdded({ id: user.id, password });
      setId('');
      setName('');
      setPassword(temporaryPassword());
      await onAdded();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card settings-card" aria-labelledby="add-user-h">
      <h2 id="add-user-h">Add a user</h2>
      <form onSubmit={submit} className="add-user">
        <div className="form-grid">
          <div className="field">
            <label htmlFor="u-id">User name (to sign in)</label>
            <input id="u-id" className="mono" value={id} onChange={(e) => setId(e.target.value)} placeholder="aibek.t"
              autoCapitalize="none" spellCheck={false} required />
          </div>
          <div className="field">
            <label htmlFor="u-name">Full name</label>
            <input id="u-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Aibek T." />
          </div>
          <div className="field">
            <label htmlFor="u-pass">Temporary password</label>
            <input id="u-pass" className="mono" value={password} onChange={(e) => setPassword(e.target.value)} minLength={10} required />
          </div>
        </div>
        <fieldset>
          <legend>Roles</legend>
          <div className="role-row">
            {allRoles.map((r) => (
              <label key={r} className="role-check">
                <input type="checkbox" checked={roles.includes(r)} onChange={() => toggle(r)} />
                <span><b>{roleLabel[r]}</b></span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && <p className="form-error" role="alert">{error}</p>}
        {added && (
          <p className="ok-note" role="status">
            Added <b className="mono">{added.id}</b>. Give them the temporary password <b className="mono">{added.password}</b>;
            they choose their own at the first sign-in.
          </p>
        )}
        <div className="settings-actions">
          <button type="submit" className="btn primary" disabled={busy || !id.trim() || password.length < 10}>
            {busy ? 'Adding…' : 'Add user'}
          </button>
        </div>
      </form>
    </section>
  );
}

/** Users and roles. Everyone can see it; only admins can add users, change roles and reset passwords. */
export default function UsersPage() {
  const { user: me, reload: reloadMe } = useCurrentUser();
  const [users, setUsers] = useState<User[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Role[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [history, setHistory] = useState<Record<string, RoleChange[]>>({});
  const isAdmin = can(me, 'users.manage');
  const [reset, setReset] = useState<{ id: string; password: string } | null>(null);

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
  const resetPassword = async (u: User) => {
    setError('');
    const password = temporaryPassword();
    try {
      await api.resetPassword(u.id, password);
      setReset({ id: u.id, password });
    } catch (e) {
      setError(message(e));
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

      {isAdmin && <AddUserForm onAdded={load} />}

      <section className="card settings-card" aria-labelledby="users-h">
        <h2 id="users-h">Users</h2>
        {!isAdmin && <p className="muted">Only admins can add users and change roles.</p>}
        {reset && (
          <p className="ok-note" role="status">
            New temporary password for <b className="mono">{reset.id}</b>: <b className="mono">{reset.password}</b>.
            They were signed out and choose their own at the next sign-in.
          </p>
        )}
        {error && !editing && <p className="form-error" role="alert">{error}</p>}
        <ul className="user-list">
          {users.map((u) => (
            <li key={u.id}>
              <div className="user-row">
                <div className="avatar" aria-hidden="true">{u.name.split(/[\s._-]+/).map((x) => x[0]?.toUpperCase()).join('').slice(0, 2)}</div>
                <div className="user-main">
                  <b>{u.name}{u.id === me?.id ? ' (you)' : ''}</b>
                  <span className="role-chips">
                    {u.roles.map((r) => <span key={r} className={`role-chip ${r}`}>{roleLabel[r]}</span>)}
                  </span>
                </div>
                {isAdmin && editing !== u.id && (
                  <span className="user-buttons">
                    <button type="button" className="btn" onClick={() => start(u)}>Change roles</button>
                    {u.id !== me?.id && (
                      <button type="button" className="btn" onClick={() => void resetPassword(u)}>Reset password</button>
                    )}
                  </span>
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
                  {draft.length === 0 && <p className="muted">No roles: they can sign in, but do nothing.</p>}
                  <div className="field">
                    <label htmlFor={`reason-${u.id}`}>Why?</label>
                    <input id={`reason-${u.id}`} value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="e.g. on call for releases this month" />
                  </div>
                  {error && <p className="form-error" role="alert">{error}</p>}
                  <div className="settings-actions">
                    <button type="button" className="btn primary" disabled={same(u) || !reason.trim()} onClick={() => save(u)}>Save</button>
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
