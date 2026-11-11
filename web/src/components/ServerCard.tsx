import { Link } from 'react-router-dom';
import type { Server } from '../api/types';

const gb = (bytes: number) => (bytes / 1024 ** 3).toFixed(1);

export default function ServerCard({ server: s }: { server: Server }) {
  const anyCommand = s.allowedTools.includes('ssh_exec');
  const n = s.allowedTools.length;
  const access = n === 0 ? 'Agent: no access' : `Agent: ${n} tool${n === 1 ? '' : 's'}${anyCommand ? ' · incl. any command' : ''}`;
  const mem = s.memoryTotalBytes && s.memoryUsedBytes != null ? s.memoryUsedBytes / s.memoryTotalBytes : null;
  return (
    <div className="card server">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="mono" style={{ fontWeight: 600 }}>{s.name}</span>
        {s.dockerVersion && <span className="rt docker">Docker {s.dockerVersion}</span>}
      </div>
      <span className="muted" style={{ fontSize: 12 }}>{s.sshUser}@{s.host}{s.sshPort !== 22 ? `:${s.sshPort}` : ''} · {s.env}</span>
      {mem !== null ? (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
            <span>Memory</span>
            <span className="muted">{gb(s.memoryUsedBytes!)} of {gb(s.memoryTotalBytes!)} GB</span>
          </div>
          <div className="bar"><div style={{ width: `${Math.min(100, mem * 100)}%` }} /></div>
        </>
      ) : (
        <span className="muted" style={{ fontSize: 12 }}>{s.checkedAt ? 'Memory: not reported' : 'Not checked yet'}</span>
      )}
      {s.checkError && <span className="form-error" style={{ fontSize: 12, margin: 0 }}>{s.checkError}</span>}
      <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{s.systems.join(', ')}</span>
      <div className="server-foot">
        <span className={anyCommand ? 'access full' : 'access tools'}>{access}</span>
        <Link to={`/servers/${s.name}`} className="settings-link" aria-label={`Settings of ${s.name}`}>Settings</Link>
      </div>
    </div>
  );
}
