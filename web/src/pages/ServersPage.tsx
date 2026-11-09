import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Server, ServerToolInfo, ToolKind } from '../api/types';
import ServerCard from '../components/ServerCard';

const groups: { kind: ToolKind; title: string; note: string }[] = [
  { kind: 'read', title: 'Read', note: 'approved once per server per chat' },
  { kind: 'write', title: 'Write', note: 'approved every time, with a reason' },
  { kind: 'full', title: 'Any command', note: 'exact command approved every time · never on prod' },
];

export default function ServersPage() {
  const [servers, setServers] = useState<Server[]>([]);
  const [tools, setTools] = useState<ServerToolInfo[]>([]);

  useEffect(() => {
    api.listServers().then(setServers);
    api.listServerTools().then(setTools);
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Servers</h1>
          <p>Machines with Docker already installed (v1: no Kubernetes or Swarm). Humans add them and choose, in each server's settings, which tools the agent may use there.</p>
        </div>
        <button type="button" className="tab" disabled title="Coming soon">+ Add server</button>
      </div>
      <div className="grid-servers">
        {servers.map((s) => (
          <ServerCard key={s.name} server={s} />
        ))}
      </div>

      <section className="tools-section" aria-labelledby="tools-h">
        <h2 id="tools-h">Agent tools</h2>
        <p className="muted">
          The agent never gets the SSH key. It calls these tools; the server-tools service checks the arguments, asks the
          developer in the chat, runs a fixed command, masks secrets and writes the audit log. Paths are limited to
          <span className="mono"> /opt/superai/&lt;system&gt;/&lt;env&gt;/</span>.
        </p>
        {groups.map((g) => (
          <div key={g.kind} className="tools-group">
            <h3>
              <span className={`tool-kind ${g.kind}`}>{g.title}</span> <span className="muted">{g.note}</span>
            </h3>
            <table className="tools-table">
              <thead>
                <tr><th>Tool</th><th>Input</th><th>What it does</th></tr>
              </thead>
              <tbody>
                {tools.filter((t) => t.kind === g.kind).map((t) => (
                  <tr key={t.name}>
                    <td className="mono">{t.name}</td>
                    <td className="mono muted">{t.params}</td>
                    <td>{t.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </section>
    </div>
  );
}
