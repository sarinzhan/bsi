import type { AgentEvent, AgentMessage, Chat, Project } from './types';

/** Applies a streamed event to the chat itself (messages, steps, status, linked projects). */
export function applyToChat(chat: Chat, event: AgentEvent): Chat {
  switch (event.type) {
    case 'message': {
      const exists = chat.messages.some((m) => m.id === event.message.id);
      const messages = exists
        ? chat.messages.map((m) => (m.id === event.message.id ? event.message : m))
        : [...chat.messages, event.message];
      const title = chat.messages.length === 0 && event.message.role === 'user' ? shortTitle(event.message.text) : chat.title;
      return { ...chat, title, messages };
    }
    case 'step':
      return {
        ...chat,
        messages: chat.messages.map((m) => {
          if (m.id !== event.messageId || m.role !== 'agent') return m;
          const agent = m as AgentMessage;
          return { ...agent, steps: (agent.steps ?? []).map((s) => (s.id === event.step.id ? event.step : s)) };
        }),
      };
    case 'project':
      return chat.projectIds.includes(event.project.id) ? chat : { ...chat, projectIds: [...chat.projectIds, event.project.id] };
    case 'status':
      return { ...chat, status: event.status };
    default:
      return chat;
  }
}

/** Applies a streamed event to the projects the chat works in. */
export function applyToProjects(projects: Record<string, Project>, event: AgentEvent): Record<string, Project> {
  switch (event.type) {
    case 'project':
      return { ...projects, [event.project.id]: event.project };
    case 'file': {
      const p = projects[event.projectId];
      if (!p) return projects;
      return { ...projects, [p.id]: { ...p, files: [...p.files.filter((f) => f.path !== event.file.path), event.file] } };
    }
    default:
      return projects;
  }
}

export function shortTitle(text: string): string {
  return text.length > 40 ? text.slice(0, 40) + '…' : text;
}
