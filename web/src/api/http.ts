import type { PlatformApi } from './client';
import type {
  AccessChange, AgentEvent, Chat, ChatSummary, HostKey, Role, RoleChange, Server, ServerToolInfo, SystemInfo, ToolAnswer,
  User,
} from './types';

// The real platform-api, same origin: nginx (prod) or the Vite dev server (npm run dev) forwards /api.

const DEV_USER_KEY = 'bsi.devUser';

function devUser(): string {
  try {
    return localStorage.getItem(DEV_USER_KEY) || 'dev';
  } catch {
    return 'dev';
  }
}

/** Dev sign-in: the "Viewing as" switcher sends X-User-Id. Prod will use the company SSO session instead. */
function headers(extra?: Record<string, string>): Record<string, string> {
  return { 'X-User-Id': devUser(), ...extra };
}

/** "/api/..." -> "/bsi/api/..." when the app is served under a base path (BSI_BASE_PATH at build time). */
const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: headers(body === undefined ? undefined : { 'Content-Type': 'application/json' }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const err = await res.json();
      if (typeof err.detail === 'string') detail = err.detail;
      else if (Array.isArray(err.detail)) detail = err.detail.map((d: { msg?: string }) => d.msg).join('; ');
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

interface ServerInfo {
  name: string;
  host: string;
  env: Server['env'];
  allowed_tools: string[];
  systems: string[];
  ssh_user: string;
  ssh_port: number;
  host_key: string | null;
  host_key_fingerprint: string | null;
  checked_at: string | null;
  docker_version: string | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  check_error: string | null;
}

const toServer = (s: ServerInfo): Server => ({
  name: s.name,
  host: s.host,
  env: s.env,
  systems: s.systems,
  sshUser: s.ssh_user,
  sshPort: s.ssh_port,
  hostKey: s.host_key,
  hostKeyFingerprint: s.host_key_fingerprint,
  allowedTools: s.allowed_tools,
  checkedAt: s.checked_at,
  dockerVersion: s.docker_version,
  memoryTotalBytes: s.memory_total_bytes,
  memoryUsedBytes: s.memory_used_bytes,
  checkError: s.check_error,
});

const toUser = (u: { id: string; name: string; roles: string[] }): User => ({ id: u.id, name: u.name, roles: u.roles as Role[] });

const toChange = <T extends AccessChange | RoleChange>(c: T): T => ({ ...c, added: [...c.added], removed: [...c.removed] });

/** Reads a text/event-stream response and hands each `data:` payload to onEvent. */
async function readEvents(res: Response, onEvent: (event: AgentEvent) => void): Promise<void> {
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = frame.split('\n').filter((l) => l.startsWith('data: ')).map((l) => l.slice(6)).join('\n');
      if (data) onEvent(JSON.parse(data) as AgentEvent);
    }
  }
}

export const httpApi: PlatformApi = {
  listSystems: () => call<SystemInfo[]>('GET', '/api/systems'),

  // ---- chat module ----
  listChats: (systemId) => call<ChatSummary[]>('GET', `/api/chats?systemId=${encodeURIComponent(systemId)}`),
  getChat: (chatId) => call<Chat>('GET', `/api/chats/${chatId}`),
  createChat: (systemId) => call<Chat>('POST', '/api/chats', { systemId }),

  /** Sends the message, then streams the chat's events (the user's own message first) until stopped. */
  sendMessage(chatId, text, onEvent) {
    const abort = new AbortController();
    void (async () => {
      try {
        const sent = await call<{ afterSeq: number }>('POST', `/api/chats/${chatId}/messages`, { text });
        const res = await fetch(`${BASE}/api/chats/${chatId}/events?after=${sent.afterSeq}`, {
          headers: headers({ Accept: 'text/event-stream' }),
          signal: abort.signal,
        });
        if (!res.ok || !res.body) throw new Error(`event stream: ${res.status}`);
        await readEvents(res, onEvent);
      } catch (e) {
        if (abort.signal.aborted) return;
        const id = `local-${Date.now()}`;
        onEvent({ type: 'message', message: { id, role: 'agent', text: `Could not send: ${(e as Error).message}` } });
        onEvent({ type: 'status', status: 'failed' });
      }
    })();
    return () => abort.abort();
  },

  // ---- approval module ----
  answerToolCall: (chatId, callId, answer: ToolAnswer) =>
    call<void>('POST', `/api/chats/${chatId}/tool-calls/${callId}/answer`, { answer }),

  // ---- access module ----
  getMe: async () => toUser(await call('GET', '/api/me')),
  async switchDevUser(id) {
    try {
      localStorage.setItem(DEV_USER_KEY, id);
    } catch {
      /* private mode: the switch lasts until reload */
    }
  },
  listUsers: async () =>
    (await call<{ id: string; name: string; roles: string[] }[]>('GET', '/api/users')).map(toUser).sort((a, b) => a.name.localeCompare(b.name)),
  setUserRoles: async (userId, roles, reason) => toUser(await call('PUT', `/api/users/${userId}/roles`, { roles, reason })),
  listRoleChanges: async (userId) => (await call<RoleChange[]>('GET', `/api/users/${userId}/role-history`)).map(toChange),

  // ---- servers module ----
  listServers: async () => (await call<ServerInfo[]>('GET', '/api/servers')).map(toServer),
  platformPublicKey: async () => (await call<{ public_key: string }>('GET', '/api/servers/ssh-public-key')).public_key,
  fetchHostKey: (host, port) => call<HostKey>('POST', '/api/servers/host-key', { host, port }),
  addServer: async (s) =>
    toServer(await call<ServerInfo>('POST', '/api/servers', {
      name: s.name, host: s.host, env: s.env, systems: s.systems, ssh_user: s.sshUser, ssh_port: s.sshPort, host_key: s.hostKey,
    })),
  checkServer: async (name) => toServer(await call<ServerInfo>('POST', `/api/servers/${name}/check`)),
  updateServerAccess: async (name, allowedTools, reason) =>
    toServer(await call<ServerInfo>('PUT', `/api/servers/${name}/allowed-tools`, { tools: allowedTools, reason })),
  listAccessChanges: async (name) => (await call<AccessChange[]>('GET', `/api/servers/${name}/access-history`)).map(toChange),
  listServerTools: () => call<ServerToolInfo[]>('GET', '/api/servers/tools'),
};
