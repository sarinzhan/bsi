import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { can } from '../api/access';
import type { AccessChange, Server, ServerToolInfo, ToolKind } from '../api/types';
import { useCurrentUser } from '../auth';

const groups: { kind: ToolKind; title: string; note: string }[] = [
  { kind: 'read', title: 'Read', note: 'approved once per server per chat' },
  { kind: 'write', title: 'Write', note: 'approved every time, with a reason' },
  { kind: 'full', title: 'Any command', note: 'exact command approved every time · never on prod' },
];

/** Server settings: the list of tools the agent may use on this server. Platform admins only. */
export default function ServerSettingsPage() {
  const { serverName = '' } = useParams();
  const [server, setServer] = useState<Server | null>(null);
  const [tools, setTools] = useState<ServerToolInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState('');
  const [history, setHistory] = useState<AccessChange[]>([]);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [checking, setChecking] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const { user } = useCurrentUser();
  const mayEdit = can(user, 'servers.manage');

  useEffect(() => {
    api.listServers().then((all) => {
      const s = all.find((x) => x.name === serverName) ?? null;
      setServer(s);
      if (s) setSelected(new Set(s.allowedTools));
    }).finally(() => setLoaded(true));
    api.listServerTools().then(setTools);
    api.listAccessChanges(serverName).then(setHistory);
  }, [serverName]);

  const prod = server?.env === 'prod';
  const blocked = (t: ServerToolInfo) => prod && t.kind === 'full';
  const added = useMemo(() => [...selected].filter((t) => !server?.allowedTools.includes(t)).sort(), [selected, server]);
  const removed = useMemo(() => (server?.allowedTools ?? []).filter((t) => !selected.has(t)).sort(), [selected, server]);
  const changed = added.length + removed.length > 0;

  if (!server) {
    return (
      <div className="page">
        {loaded ? <p>Server {serverName} not found. <Link to="/servers">Back to servers</Link></p> : <p className="muted">Loading…</p>}
      </div>
    );
  }

  const testConnection = async () => {
    setChecking(true);
    try {
      setServer(await api.checkServer(server.name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  };
  const gb = (bytes: number) => (bytes / 1024 ** 3).toFixed(1);

  const pick = (names: string[]) => {
    setSelected(new Set(names));
    setSaved(false);
  };
  const toggle = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    pick([...next]);
  };
  const ofKinds = (...kinds: ToolKind[]) => tools.filter((t) => kinds.includes(t.kind) && !blocked(t)).map((t) => t.name);
  const presets = [
    { label: 'None', names: [] as string[] },
    { label: 'Read only', names: ofKinds('read') },
    { label: 'Read + write', names: ofKinds('read', 'write') },
    { label: 'Everything', names: ofKinds('read', 'write', 'full'), hidden: prod },
  ];
  const sameSet = (names: string[]) => names.length === selected.size && names.every((n) => selected.has(n));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      const updated = await api.updateServerAccess(server.name, [...selected].sort(), reason.trim());
      setServer(updated);
      setSelected(new Set(updated.allowedTools));
      setReason('');
      setSaved(true);
      setHistory(await api.listAccessChanges(server.name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="page settings-page">
      <div>
        <Link to="/servers" className="back-link">← Servers</Link>
        <div className="page-head">
          <div>
            <h1 className="mono">{server.name}</h1>
            <p>{server.sshUser}@{server.host}:{server.sshPort} · {server.env} · {server.systems.join(', ')}</p>
          </div>
        </div>
      </div>

      <section className="card settings-card" aria-labelledby="conn-h">
        <h2 id="conn-h">Connection</h2>
        <p className="muted" style={{ margin: 0 }}>
          Host key <span className="mono">{server.hostKeyFingerprint ?? 'none: SSH to this server is refused'}</span>
        </p>
        {server.checkedAt ? (
          server.checkError ? (
            <p className="form-error">Last check {new Date(server.checkedAt).toLocaleString()}: {server.checkError}</p>
          ) : (
            <p style={{ margin: 0 }}>
              Last check {new Date(server.checkedAt).toLocaleString()}: Docker {server.dockerVersion}
              {server.memoryTotalBytes != null && server.memoryUsedBytes != null &&
                ` · memory ${gb(server.memoryUsedBytes)} of ${gb(server.memoryTotalBytes)} GB used`}
            </p>
          )
        ) : (
          <p className="muted" style={{ margin: 0 }}>Not checked yet.</p>
        )}
        <div>
          <button type="button" className="btn" onClick={() => void testConnection()} disabled={!mayEdit || checking}>
            {checking ? 'Connecting…' : 'Test connection'}
          </button>
        </div>
      </section>

      <form className="card settings-card" onSubmit={save}>
        <fieldset disabled={!mayEdit}>
          <legend>Agent tools on this server</legend>
          {!mayEdit && <p className="tool-needs">Only <b>DevOps</b> and <b>admins</b> can change this. You can see it.</p>}
          <p className="muted">
            The agent can call only the tools ticked here. Anything else is rejected before you are even asked.
            Changes apply to the next call, including calls already waiting for approval.
          </p>

          <div className="presets" role="group" aria-label="Presets">
            <span className="muted">Quick set:</span>
            {presets.filter((p) => !p.hidden).map((p) => (
              <button key={p.label} type="button" className={`tab ${sameSet(p.names) ? 'active' : ''}`} aria-pressed={sameSet(p.names)} onClick={() => pick(p.names)}>
                {p.label}
              </button>
            ))}
          </div>

          {groups.map((g) => (
            <div key={g.kind} className="tool-group">
              <div className="tool-group-head">
                <span className={`tool-kind ${g.kind}`}>{g.title}</span>
                <span className="muted">{g.note}</span>
              </div>
              {tools.filter((t) => t.kind === g.kind).map((t) => (
                <label key={t.name} className={`tool-option ${selected.has(t.name) ? 'on' : ''} ${blocked(t) ? 'disabled' : ''}`}>
                  <input type="checkbox" checked={selected.has(t.name)} disabled={blocked(t)} onChange={() => toggle(t.name)} />
                  <span className="mono tool-option-name">{t.name}</span>
                  <span className="muted">{t.summary}</span>
                  {blocked(t) && <span className="access-warn">Not allowed on prod servers.</span>}
                </label>
              ))}
            </div>
          ))}
        </fieldset>

        {changed && (
          <>
            <div className="diff-line" aria-live="polite">
              {added.length > 0 && <span className="plus">+ {added.join(', ')}</span>}
              {removed.length > 0 && <span className="minus">− {removed.join(', ')}</span>}
            </div>
            <div className="field">
              <label htmlFor="reason">Why are you changing it?</label>
              <input
                id="reason"
                value={reason}
                maxLength={200}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. stage is read-only during the release"
              />
            </div>
          </>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="settings-actions">
          <button type="submit" className="btn primary" disabled={!changed || !reason.trim()}>Save</button>
          {saved && !changed && <span className="saved" role="status">Saved</span>}
          <span className="muted" style={{ fontSize: 12 }}>
            {selected.size} of {tools.length} tools · DevOps and admins · every change is logged below
          </span>
        </div>
      </form>

      <section className="card settings-card" aria-labelledby="hist-h">
        <h2 id="hist-h">Access changes</h2>
        {history.length === 0 ? (
          <p className="muted">No changes yet.</p>
        ) : (
          <ul className="access-history">
            {history.map((c) => (
              <li key={c.at + c.added.join() + c.removed.join()}>
                <span className="mono muted">{new Date(c.at).toLocaleString()}</span>
                <b>{c.by}</b>
                {c.added.length > 0 && <span className="plus mono">+ {c.added.join(', ')}</span>}
                {c.removed.length > 0 && <span className="minus mono">− {c.removed.join(', ')}</span>}
                <span className="muted">“{c.reason}”</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
