import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api/client';
import type { Env, HostKey, Server } from '../api/types';

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Adding a server, in the order it has to happen:
 * 1. the platform's public key goes into ~/.ssh/authorized_keys on the server,
 * 2. the platform reads the server's SSH host key, the person compares its fingerprint with the server's own
 *    (or trusts it without comparing); either way that key is pinned and no other is accepted later,
 * 3. saved (no agent tools yet), then a connection test: Docker version and memory.
 */
export default function AddServerForm({ onAdded, onCancel }: { onAdded: (s: Server) => void; onCancel: () => void }) {
  const [publicKey, setPublicKey] = useState('');
  const [copied, setCopied] = useState(false);
  const [name, setName] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState(22);
  const [user, setUser] = useState('deploy');
  const [env, setEnv] = useState<Env>('dev');
  const [systems, setSystems] = useState('');
  const [hostKey, setHostKey] = useState<HostKey | null>(null);
  // compared: the person checked the fingerprint on the server. unchecked: trusted as is (trust on first use).
  const [trust, setTrust] = useState<'compared' | 'unchecked' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.platformPublicKey().then(setPublicKey).catch((e) => setError(message(e)));
  }, []);

  // Another host or port = another key: fetch and confirm again.
  useEffect(() => {
    setHostKey(null);
    setTrust(null);
  }, [host, port]);

  const systemList = systems.split(/[\s,]+/).map((s) => s.trim().toLowerCase()).filter(Boolean);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(publicKey);
      setCopied(true);
    } catch {
      setCopied(false); // no clipboard (http, old browser): the key is selectable in the box
    }
  };

  const fetchKey = async () => {
    setError('');
    setBusy(true);
    try {
      setHostKey(await api.fetchHostKey(host.trim(), port));
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!hostKey || !trust) return;
    setError('');
    setBusy(true);
    try {
      const added = await api.addServer({
        name: name.trim(), host: host.trim(), env, systems: systemList, sshUser: user.trim(), sshPort: port, hostKey: hostKey.key,
      });
      onAdded(await api.checkServer(added.name).catch(() => added)); // the check result shows on its card
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card settings-card add-server" onSubmit={save} aria-labelledby="add-h">
      <h2 id="add-h">Add a server</h2>

      <div className="step">
        <h3>1. Let the platform log in</h3>
        <p className="muted">
          On the server, add this key to <span className="mono">~{user || 'deploy'}/.ssh/authorized_keys</span>. That user must
          be able to run <span className="mono">docker</span> (member of the <span className="mono">docker</span> group).
        </p>
        <textarea className="mono key-box" readOnly rows={2} value={publicKey} aria-label="Platform public key" onFocus={(e) => e.target.select()} />
        <div>
          <button type="button" className="btn" onClick={() => void copy()} disabled={!publicKey}>{copied ? 'Copied' : 'Copy key'}</button>
        </div>
      </div>

      <div className="step">
        <h3>2. The server</h3>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="s-name">Name</label>
            <input id="s-name" className="mono" value={name} onChange={(e) => setName(e.target.value)} placeholder="dev-docker-01" required />
          </div>
          <div className="field">
            <label htmlFor="s-env">Environment</label>
            <select id="s-env" value={env} onChange={(e) => setEnv(e.target.value as Env)}>
              <option value="dev">dev</option>
              <option value="stage">stage</option>
              <option value="prod">prod</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="s-host">Host or IP</label>
            <input id="s-host" className="mono" value={host} onChange={(e) => setHost(e.target.value)} placeholder="10.20.1.11" required />
          </div>
          <div className="field">
            <label htmlFor="s-port">SSH port</label>
            <input id="s-port" type="number" min={1} max={65535} value={port} onChange={(e) => setPort(Number(e.target.value) || 22)} />
          </div>
          <div className="field">
            <label htmlFor="s-user">SSH user</label>
            <input id="s-user" className="mono" value={user} onChange={(e) => setUser(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="s-systems">Systems on it</label>
            <input id="s-systems" className="mono" value={systems} onChange={(e) => setSystems(e.target.value)} placeholder="superapp, billing" required />
          </div>
        </div>
        <p className="muted" style={{ fontSize: 12.5 }}>
          Systems: what runs on this server. Each one becomes a system in the sidebar, with chats about it.
        </p>
      </div>

      <div className="step">
        <h3>3. Check that it is really that server</h3>
        {!hostKey ? (
          <div>
            <button type="button" className="btn" onClick={() => void fetchKey()} disabled={!host.trim() || busy}>
              {busy ? 'Connecting…' : 'Get its host key'}
            </button>
          </div>
        ) : (
          <>
            <p className="muted">The server answered with this key. On the server, run:</p>
            <pre className="mono cmd">ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</pre>
            <p className="fingerprint mono">{hostKey.fingerprint} <span className="muted">({hostKey.key.split(' ')[0]})</span></p>
            <label className="role-check">
              <input type="radio" name="trust" checked={trust === 'compared'} onChange={() => setTrust('compared')} />
              <span>I compared it: the fingerprint on the server is the same.</span>
            </label>
            <label className="role-check">
              <input type="radio" name="trust" checked={trust === 'unchecked'} onChange={() => setTrust('unchecked')} />
              <span>Trust it without comparing. Only safe if nobody can stand between the platform and this server.</span>
            </label>
            {trust && (
              <p className="muted" style={{ fontSize: 12.5 }}>From now on the platform trusts only this key.</p>
            )}
          </>
        )}
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="settings-actions">
        <button type="submit" className="btn primary" disabled={!hostKey || !trust || !name.trim() || systemList.length === 0 || busy}>
          {busy && hostKey ? 'Adding…' : 'Add server'}
        </button>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        <span className="muted" style={{ fontSize: 12 }}>The agent gets no tools on it until you choose them in its settings.</span>
      </div>
    </form>
  );
}
