import { Link, useParams } from 'react-router-dom';
import type { Server } from '../api/types';

export default function ServerCard({ server: s }: { server: Server }) {
  const { systemId = 'superapp' } = useParams();
  const anyCommand = s.allowedTools.includes('ssh_exec');
  const n = s.allowedTools.length;
  const access = n === 0 ? 'Agent: no access' : `Agent: ${n} tool${n === 1 ? '' : 's'}${anyCommand ? ' · incl. any command' : ''}`;
  return (
    <div className="card server">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="mono" style={{ fontWeight: 600 }}>{s.name}</span>
        <span className="rt docker">{s.runtime} {s.runtimeVersion}</span>
      </div>
      <span className="muted" style={{ fontSize: 12 }}>{s.host} · {s.env}</span>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
        <span>Memory</span>
        <span className="muted">{s.memoryUsedGb} of {s.memoryTotalGb} GB</span>
      </div>
      <div className="bar"><div style={{ width: `${(s.memoryUsedGb / s.memoryTotalGb) * 100}%` }} /></div>
      <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{s.usedFor}</span>
      <div className="server-foot">
        <span className={anyCommand ? 'access full' : 'access tools'}>{access}</span>
        <Link to={`/${systemId}/servers/${s.name}`} className="settings-link" aria-label={`Settings of ${s.name}`}>Settings</Link>
      </div>
    </div>
  );
}
