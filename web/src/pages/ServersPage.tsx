import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { can } from '../api/access';
import type { Server, ServerToolInfo, ToolKind } from '../api/types';
import { useCurrentUser } from '../auth';
import AddServerForm from '../components/AddServerForm';
import ServerCard from '../components/ServerCard';

const groups: { kind: ToolKind; title: string; note: string }[] = [
  { kind: 'read', title: 'Read', note: 'approved once per server per chat' },
  { kind: 'write', title: 'Write', note: 'approved every time, with a reason' },
  { kind: 'full', title: 'Any command', note: 'exact command approved every time · never on prod' },
];

export default function ServersPage() {
  const [servers, setServers] = useState<Server[]>([]);
  const [tools, setTools] = useState<ServerToolInfo[]>([]);
  const [adding, setAdding] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const { user } = useCurrentUser();
  const navigate = useNavigate();
  const mayAdd = can(user, 'servers.manage');

  useEffect(() => {
    api.listServers().then(setServers).finally(() => setLoaded(true));
    api.listServerTools().then(setTools);
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Servers</h1>
          <p>Machines with Docker already installed (v1: no Kubernetes or Swarm). DevOps and admins add them and choose, in each server's settings, which tools the agent may use there.</p>
        </div>
        {!adding && (
          <button type="button" className="btn primary" onClick={() => setAdding(true)} disabled={!mayAdd}
            title={mayAdd ? undefined : 'Only DevOps and admins add servers'}>
            + Add server
          </button>
        )}
      </div>

      {adding && (
        <AddServerForm
          onCancel={() => setAdding(false)}
          onAdded={(s) => {
            setAdding(false);
            setServers((all) => [...all.filter((x) => x.name !== s.name), s].sort((a, b) => a.name.localeCompare(b.name)));
            navigate(`/servers/${s.name}`); // next: choose the tools the agent may use there
          }}
        />
      )}

      {loaded && servers.length === 0 && !adding && (
        <div className="placeholder">
          No servers yet. {mayAdd ? 'Add the first one: chats need a server to work on.' : 'Ask a DevOps engineer or an admin to add one.'}
        </div>
      )}
      <div className="grid-servers">
        {servers.map((s) => (
          <ServerCard key={s.name} server={s} />
        ))}
      </div>

      <section className="tools-section" aria-labelledby="tools-h">
        <h2 id="tools-h">Agent tools</h2>
        <p className="muted">
          The agent never gets the SSH key. It calls these tools; the platform checks the arguments, asks the
          developer in the chat, runs a fixed command, masks secrets and writes the audit log. Paths are limited to
          <span className="mono"> /opt/bsi/&lt;system&gt;/&lt;env&gt;/</span>.
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
