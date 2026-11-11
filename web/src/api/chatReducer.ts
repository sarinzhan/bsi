import type { AgentEvent, AgentMessage, Chat } from './types';

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

export function shortTitle(text: string): string {
  return text.length > 40 ? text.slice(0, 40) + '…' : text;
}
