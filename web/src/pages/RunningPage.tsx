import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Resource, ResourceKind, Server } from '../api/types';
import ServerCard from '../components/ServerCard';

type Filter = 'all' | ResourceKind;
const filters: [Filter, string][] = [['all', 'All'], ['app', 'Apps'], ['db', 'Databases'], ['broker', 'Brokers']];

export default function RunningPage() {
  const { systemId = 'superapp' } = useParams();
  const [servers, setServers] = useState<Server[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    api.listServers().then(setServers);
    api.listResources(systemId).then(setResources);
  }, [systemId]);

  const rows = resources.filter((r) => filter === 'all' || r.kind === filter);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Running · {systemId}</h1>
          <p>What the agent created and where it runs. Each item points to the file that defines it and the decision that explains it.</p>
        </div>
        <span className="badge warn">Read-only · ask in a chat to change anything</span>
      </div>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Servers given to the agent</h2>
        <div className="grid-servers">
          {servers.map((s) => (
            <ServerCard key={s.name} server={s} />
          ))}
        </div>
      </section>

      <section className="card" style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>Resources</h2>
          <div className="tabs" style={{ marginLeft: 'auto' }}>
            {filters.map(([id, label]) => (
              <button key={id} className={filter === id ? 'tab active' : 'tab'} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>
            ))}
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ minWidth: 820 }}>
            <thead>
              <tr><th>Name</th><th>Image</th><th>Server</th><th>Usage</th><th>Defined in</th><th>Why</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name + r.server}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className="dot" style={{ background: r.status === 'healthy' ? 'var(--ok)' : 'var(--accent)' }} />
                      <span className={`kind ${r.kind}`}>{r.kind.toUpperCase()}</span>
                      <span className="mono" style={{ fontWeight: 600 }}>{r.name}</span>
                    </div>
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>{r.image}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{r.server}</td>
                  <td>{r.usage}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{r.definedIn}</td>
                  <td style={{ fontSize: 12 }}>{r.adr}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
