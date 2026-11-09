import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Decision, DecisionKind } from '../api/types';

const kinds: { id: DecisionKind | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'feature', label: 'New functionality' },
  { id: 'change', label: 'Changes' },
  { id: 'infrastructure', label: 'Infrastructure' },
  { id: 'fix', label: 'Fixes' },
];

const kindLabel: Record<DecisionKind, string> = {
  feature: 'New functionality',
  change: 'Change',
  infrastructure: 'Infrastructure',
  fix: 'Fix',
};

function day(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' });
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

/** The system's decision log: every new feature, change and infra decision, why it was made, and which version shipped it. */
export default function HistoryPage() {
  const { systemId = 'superapp' } = useParams();
  const [params, setParams] = useSearchParams();
  const [all, setAll] = useState<Decision[]>([]);
  const [query, setQuery] = useState('');
  const kind = (params.get('kind') ?? 'all') as DecisionKind | 'all';
  const project = params.get('project') ?? '';

  useEffect(() => {
    api.listDecisions(systemId).then(setAll);
  }, [systemId]);

  const projects = useMemo(() => [...new Set(all.flatMap((d) => d.projects))].sort(), [all]);

  const shown = all.filter((d) => {
    if (kind !== 'all' && d.kind !== kind) return false;
    if (project && !d.projects.includes(project)) return false;
    const q = query.trim().toLowerCase();
    return !q || [d.id, d.title, d.decision, d.why, d.version].some((t) => t.toLowerCase().includes(q));
  });

  // Group by day, newest first.
  const groups: { day: string; items: Decision[] }[] = [];
  for (const d of shown) {
    const key = day(d.createdAt);
    const last = groups[groups.length - 1];
    if (last && last.day === key) last.items.push(d);
    else groups.push({ day: key, items: [d] });
  }

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value && value !== 'all') next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>History · {systemId}</h1>
          <p>Every decision for the whole system: what was added or changed, why, what was rejected, and which version shipped it. Stored as files in {systemId}/platform/docs/adr/.</p>
        </div>
        {all[0] && <span className="badge ok mono">current v{all[0].version}</span>}
      </div>

      <div className="history-filters">
        <div className="tabs" role="group" aria-label="Kind">
          {kinds.map((k) => (
            <button key={k.id} className={kind === k.id ? 'tab active' : 'tab'} aria-pressed={kind === k.id} onClick={() => setParam('kind', k.id)}>
              {k.label}
            </button>
          ))}
        </div>
        <label className="sr-only" htmlFor="hproject">Project</label>
        <select id="hproject" className="system-select" style={{ margin: 0 }} value={project} onChange={(e) => setParam('project', e.target.value)}>
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <label className="sr-only" htmlFor="hsearch">Search</label>
        <input id="hsearch" className="history-search" placeholder="Search decisions…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      {groups.length === 0 && <div className="placeholder">No decisions match these filters.</div>}

      {groups.map((g) => (
        <section key={g.day} className="history-day" aria-label={g.day}>
          <h2>{g.day}</h2>
          <ol className="timeline">
            {g.items.map((d) => (
              <li key={d.id} className="card history-item">
                <div className="history-top">
                  <span className="mono version">v{d.version}</span>
                  <span className={`kind-tag ${d.kind}`}>{kindLabel[d.kind]}</span>
                  <span className="mono muted" style={{ fontSize: 12 }}>{d.id}</span>
                  <span className="muted" style={{ marginLeft: 'auto', fontSize: 12 }}>{time(d.createdAt)}</span>
                </div>
                <h3>{d.title}</h3>
                <p><b>Decision:</b> {d.decision}</p>
                <p><b>Why:</b> {d.why}</p>
                <p className="muted"><b>Rejected:</b> {d.rejected}</p>
                <div className="history-meta">
                  {d.projects.map((p) => (
                    <Link key={p} to={`/${systemId}/projects/${p}`} className="project-chip">{p}</Link>
                  ))}
                  {d.chatId && <Link to={`/${systemId}/chats/${d.chatId}`} style={{ fontSize: 12 }}>open chat</Link>}
                  <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>{d.author} · skills: {d.skills.join(', ')}</span>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
