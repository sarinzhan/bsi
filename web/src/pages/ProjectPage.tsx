import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { ChatSummary, Project } from '../api/types';
import ChatSidePanel from '../components/ChatSidePanel';
import StatusBadge, { statusColor } from '../components/StatusBadge';

/** A project folder: what exists, which chats changed it, its files. Decisions live in the system History. */
export default function ProjectPage() {
  const { systemId = 'superapp', projectId = '' } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);

  useEffect(() => {
    api.getProject(projectId).then(setProject).catch(() => setProject(null));
    api.listChats(systemId).then(setChats);
  }, [projectId, systemId]);

  if (!project) return <div className="page"><p className="muted">Project not found.</p></div>;

  const projectChats = chats.filter((c) => c.projectIds.includes(project.id));

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <div className="project-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h1>{project.name}</h1>
          <StatusBadge status={project.status} />
        </div>
        <span className="muted">{project.description}</span>
        <span className="mono muted" style={{ fontSize: 12 }}>gitlab: {project.repo}</span>
        <Link to={`/${systemId}/history?project=${project.name}`} style={{ fontSize: 13 }}>Decisions about {project.name} in History →</Link>
      </div>
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <aside className="project-chats" aria-label="Chats that changed this project">
          <div className="nav-label" style={{ padding: '0 0 4px' }}>Chats that changed it</div>
          {projectChats.map((c) => (
            <Link key={c.id} to={`/${systemId}/chats/${c.id}`} className="project-chat">
              <span className="dot" style={{ background: statusColor[c.status] }} />
              <span>{c.title}</span>
            </Link>
          ))}
          {projectChats.length === 0 && <span className="muted" style={{ fontSize: 13 }}>No chats yet.</span>}
          <Link to={`/${systemId}/chats/new`} className="nav-sub add" style={{ paddingLeft: 0 }}>+ New chat</Link>
        </aside>
        <ChatSidePanel systemId={systemId} projects={[project]} />
      </div>
    </div>
  );
}
