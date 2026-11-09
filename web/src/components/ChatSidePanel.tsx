import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Decision, FileChange, Project, Resource } from '../api/types';
import CodeView from './CodeView';

type Tab = 'files' | 'decisions' | 'running';

/** Files, decisions and running resources of the projects a chat (or a project page) works with. */
export default function ChatSidePanel({
  systemId,
  projects,
  decisions,
}: {
  systemId: string;
  projects: Project[];
  /** Decisions made in this chat. Omit to hide the tab. Full log: the History page. */
  decisions?: Decision[];
}) {
  const [tab, setTab] = useState<Tab>('files');
  const [selected, setSelected] = useState<string | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);

  // Prefix paths with the project name when several projects are shown.
  const many = projects.length > 1;
  const files: FileChange[] = projects.flatMap((p) => p.files.map((f) => (many ? { ...f, path: `${p.name}/${f.path}` } : f)));
  const file = files.find((f) => f.path === selected) ?? files[0];
  const names = projects.map((p) => p.name);

  useEffect(() => {
    api.listResources(systemId).then(setResources);
  }, [systemId, projects.map((p) => p.status).join()]);

  const tabs: [Tab, string][] = [
    ['files', `Files${files.length ? ` (${files.length})` : ''}`],
    ...(decisions ? [['decisions', `Decisions${decisions.length ? ` (${decisions.length})` : ''}`] as [Tab, string]] : []),
    ['running', 'Running'],
  ];

  return (
    <section className="side" aria-label="What the agent produced">
      <div className="tabs" role="tablist">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'tab active' : 'tab'} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'files' &&
        (file ? (
          <div className="files">
            <nav className="card file-list" aria-label="Changed files">
              {files.map((f) => (
                <button key={f.path} className={f === file ? 'file-item active' : 'file-item'} onClick={() => setSelected(f.path)}>
                  <span className="name">{f.path}</span>
                  <span className={`st st-${f.status}`}>{f.status === 'added' ? 'A' : 'M'}</span>
                </button>
              ))}
              <p className="muted" style={{ fontSize: 12, margin: '10px 8px 0' }}>
                Only Docker Compose files. Scripts are rejected.
              </p>
            </nav>
            <CodeView file={file} />
          </div>
        ) : (
          <div className="placeholder">Files the agent writes appear here while it works.</div>
        ))}

      {tab === 'decisions' &&
        (decisions && decisions.length > 0 ? (
          decisions.map((d) => (
            <article key={d.id} className="card adr">
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <span className="mono muted" style={{ fontSize: 12 }}>{d.id}</span>
                <h3>{d.title}</h3>
                <span className="mono muted" style={{ marginLeft: 'auto', fontSize: 12 }}>v{d.version}</span>
              </div>
              <p><b>Decision:</b> {d.decision}</p>
              <p><b>Why:</b> {d.why}</p>
              <p><b>Rejected:</b> {d.rejected}</p>
              <span style={{ fontSize: 12, color: 'var(--skill)' }}>Skills: {d.skills.join(', ')}</span>
            </article>
          ))
        ) : (
          <div className="placeholder">Decisions from this chat appear here. All decisions of the system are on the History page.</div>
        ))}

      {tab === 'running' && (
        <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {resources.filter((r) => names.length === 0 || names.some((n) => r.name.startsWith(n.replace('-service', '')))).map((r) => (
            <div key={r.name + r.server} className="res-row">
              <span className="dot" style={{ background: 'var(--ok)' }} />
              <span className={`kind ${r.kind}`}>{r.kind.toUpperCase()}</span>
              <span className="mono" style={{ fontWeight: 600, minWidth: 170 }}>{r.name}</span>
              <span className="mono muted" style={{ fontSize: 12, flex: '1 1 200px' }}>{r.image}</span>
              <span style={{ fontSize: 12 }}>{r.usage}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
