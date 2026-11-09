import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Skill } from '../api/types';

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedId, setSelectedId] = useState<string>('readable-infra');

  useEffect(() => {
    api.listSkills().then(setSkills);
  }, []);

  const current = skills.find((s) => s.id === selectedId) ?? skills[0];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Skills</h1>
          <p>Instructions the agent loads before it writes code, chooses infrastructure or deploys. They live in the platform-skills repo and change only through merge requests.</p>
        </div>
      </div>
      <div className="skills-layout">
        <div className="skill-list" role="listbox" aria-label="Skills">
          {skills.map((s) => (
            <button
              key={s.id}
              role="option"
              aria-selected={s.id === current?.id}
              className={s.id === current?.id ? 'skill-item active' : 'skill-item'}
              onClick={() => setSelectedId(s.id)}
            >
              <span className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{s.id}</span>
              <span className="muted" style={{ fontSize: 12 }}>{s.description}</span>
            </button>
          ))}
        </div>
        {current && (
          <section className="card skill-view" aria-label="Skill content">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid var(--border)' }}>
              <h2 className="mono" style={{ margin: 0, fontSize: 16 }}>{current.id}/SKILL.md</h2>
              <span className="muted" style={{ fontSize: 12 }}>{current.version} · owner: {current.owner}</span>
            </div>
            <pre>{current.body}</pre>
            <div style={{ padding: '12px 18px', borderTop: '1px solid var(--border)', background: 'var(--surface-2)', fontSize: 12.5 }}>{current.usage}</div>
          </section>
        )}
      </div>
    </div>
  );
}
